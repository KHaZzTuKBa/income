from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, BrokerConnection, Category, HoldingCategory, User
from app.models.user import USER_ACTIVE, USER_FROZEN, USER_PENDING, USER_REJECTED
from app.schemas.users import (
    AdminUserOut,
    AdminUsersOut,
    BulkActionOut,
    LegacyPortfolioOut,
    RegisterIn,
)
from app.security import hash_password, verify_password

USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LETTER_RE = re.compile(r"[^\W\d_]")
DIGIT_RE = re.compile(r"\d")
NON_DIGIT_RE = re.compile(r"\D")

STATUS_ERRORS = {
    USER_PENDING: "Заявка на рассмотрении. Войти можно после одобрения администратором.",
    USER_REJECTED: "Заявка отклонена",
    USER_FROZEN: "Аккаунт заморожен",
}

TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "approve": ({USER_PENDING, USER_REJECTED}, USER_ACTIVE),
    "reject": ({USER_PENDING}, USER_REJECTED),
    "freeze": ({USER_ACTIVE}, USER_FROZEN),
    "unfreeze": ({USER_FROZEN}, USER_ACTIVE),
}

ALL_STATUSES = (USER_PENDING, USER_ACTIVE, USER_FROZEN, USER_REJECTED)


class UserError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_username(value: str) -> str:
    username = value.strip()
    if not 3 <= len(username) <= 32:
        raise UserError("Логин: от 3 до 32 символов", 422)
    if not USERNAME_RE.match(username):
        raise UserError(
            "Логин: латинские буквы, цифры, точка, дефис и подчёркивание; начинается с буквы",
            422,
        )
    return username.lower()


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        raise UserError("Некорректная почта", 422)
    return email


def normalize_phone(value: str) -> str:
    digits = NON_DIGIT_RE.sub("", value)
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    elif not (len(digits) == 10 and digits[0] == "9"):
        raise UserError("Телефон в формате +7 999 123-45-67", 422)
    return f"+7{digits}"


def validate_password(password: str, username: str) -> None:
    if not 8 <= len(password) <= 128:
        raise UserError("Пароль: от 8 до 128 символов", 422)
    if not LETTER_RE.search(password) or not DIGIT_RE.search(password):
        raise UserError("Пароль должен содержать хотя бы одну букву и одну цифру", 422)
    if password.lower() == username.lower():
        raise UserError("Пароль не должен совпадать с логином", 422)


async def find_by_login(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User).where(func.lower(User.username) == username.strip().lower()).order_by(User.id).limit(1)
    )
    return result.scalar_one_or_none()


async def register_user(session: AsyncSession, body: RegisterIn) -> User:
    username = normalize_username(body.username)
    email = normalize_email(body.email)
    phone = normalize_phone(body.phone)
    validate_password(body.password, username)

    if username == settings.app_username.strip().lower() or await find_by_login(session, username):
        raise UserError("Логин уже занят", 409)
    if await _exists(session, User, User.email == email):
        raise UserError("Эта почта уже используется", 409)
    if await _exists(session, User, User.phone == phone):
        raise UserError("Этот телефон уже используется", 409)

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        email=email,
        phone=phone,
        status=USER_PENDING,
        is_admin=False,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UserError("Логин, почта или телефон уже заняты", 409) from exc
    return user


async def change_password(session: AsyncSession, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise UserError("Текущий пароль указан неверно", 400)
    validate_password(new, user.username)
    if current == new:
        raise UserError("Новый пароль совпадает с текущим", 422)
    user.password_hash = hash_password(new)
    await session.commit()


async def list_users(session: AsyncSession, statuses: list[str], query: str) -> AdminUsersOut:
    stmt = select(User).where(User.is_admin.is_(False))
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))
    needle = query.strip().lower()
    if needle:
        pattern = _like_pattern(needle)
        conditions = [
            func.lower(User.username).like(pattern, escape="\\"),
            func.lower(User.email).like(pattern, escape="\\"),
        ]
        digits = NON_DIGIT_RE.sub("", needle)
        if digits:
            conditions.append(User.phone.like(f"%{digits}%"))
            if digits.startswith("8"):
                conditions.append(User.phone.like(f"%7{digits[1:]}%"))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
    users = list((await session.execute(stmt)).scalars())

    connected: set[int] = set()
    if users:
        connected_rows = await session.execute(
            select(BrokerConnection.user_id).where(BrokerConnection.user_id.in_([item.id for item in users]))
        )
        connected = set(connected_rows.scalars())

    counts = {item: 0 for item in ALL_STATUSES}
    count_rows = await session.execute(
        select(User.status, func.count()).where(User.is_admin.is_(False)).group_by(User.status)
    )
    for status_value, amount in count_rows.all():
        counts[status_value] = int(amount)

    items = [
        AdminUserOut(
            id=item.id,
            username=item.username,
            email=item.email,
            phone=item.phone,
            status=item.status,
            created_at=item.created_at,
            reviewed_at=item.reviewed_at,
            has_portfolio=item.id in connected,
        )
        for item in users
    ]
    return AdminUsersOut(items=items, counts=counts)


async def apply_action(session: AsyncSession, admin: User, ids: list[int], action: str) -> BulkActionOut:
    requested = set(ids)
    result = await session.execute(
        select(User).where(User.id.in_(requested), User.is_admin.is_(False), User.id != admin.id)
    )
    targets = list(result.scalars())

    if action == "delete":
        target_ids = [item.id for item in targets]
        if target_ids:
            await session.execute(delete(User).where(User.id.in_(target_ids)))
            await session.commit()
        return BulkActionOut(updated=len(target_ids), skipped=len(requested) - len(target_ids))

    allowed_from, new_status = TRANSITIONS[action]
    now = datetime.now(timezone.utc)
    updated = 0
    for item in targets:
        if item.status not in allowed_from:
            continue
        item.status = new_status
        if action in ("approve", "reject"):
            item.reviewed_at = now
        updated += 1
    await session.commit()
    return BulkActionOut(updated=updated, skipped=len(requested) - updated)


async def legacy_portfolio(session: AsyncSession, admin: User) -> LegacyPortfolioOut:
    connection = (
        await session.execute(select(BrokerConnection).where(BrokerConnection.user_id == admin.id))
    ).scalar_one_or_none()
    categories_count = int(
        await session.scalar(select(func.count()).select_from(Category).where(Category.user_id == admin.id))
        or 0
    )
    accounts_count = 0
    if connection is not None:
        accounts_count = int(
            await session.scalar(
                select(func.count()).select_from(Account).where(Account.connection_id == connection.id)
            )
            or 0
        )
    return LegacyPortfolioOut(
        has_portfolio=connection is not None or categories_count > 0,
        token_hint=connection.token_hint if connection is not None else None,
        accounts_count=accounts_count,
        categories_count=categories_count,
    )


async def transfer_legacy_portfolio(session: AsyncSession, admin: User, target_id: int) -> None:
    target = await session.get(User, target_id)
    if target is None or target.is_admin:
        raise UserError("Пользователь не найден", 404)
    if target.status != USER_ACTIVE:
        raise UserError("Передать портфель можно только активному пользователю", 409)
    if await _exists(session, BrokerConnection, BrokerConnection.user_id == target.id):
        raise UserError("У пользователя уже подключён Т‑Банк", 409)
    if await _exists(session, Category, Category.user_id == target.id):
        raise UserError("У пользователя уже есть свои категории", 409)
    legacy = await legacy_portfolio(session, admin)
    if not legacy.has_portfolio:
        raise UserError("У администратора нет портфеля для передачи", 409)

    await session.execute(
        update(BrokerConnection).where(BrokerConnection.user_id == admin.id).values(user_id=target.id)
    )
    await session.execute(update(Category).where(Category.user_id == admin.id).values(user_id=target.id))
    await session.execute(
        update(HoldingCategory).where(HoldingCategory.user_id == admin.id).values(user_id=target.id)
    )
    await session.commit()


async def _exists(session: AsyncSession, model, condition) -> bool:
    found = await session.scalar(select(func.count()).select_from(model).where(condition))
    return bool(found)


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
