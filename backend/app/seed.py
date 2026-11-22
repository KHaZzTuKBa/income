import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.models.user import USER_ACTIVE
from app.security import hash_password, verify_password

logger = logging.getLogger("portfel.seed")


async def seed_user(session: AsyncSession) -> None:
    result = await session.execute(
        select(User).where(User.is_admin.is_(True)).order_by(User.id).limit(1)
    )
    admin = result.scalar_one_or_none()
    username = settings.app_username.strip()
    if admin is None:
        session.add(
            User(
                username=username,
                password_hash=hash_password(settings.app_password),
                status=USER_ACTIVE,
                is_admin=True,
            )
        )
        await session.commit()
        return

    changed = False
    if admin.username != username:
        clash = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(func.lower(User.username) == username.lower(), User.id != admin.id)
        )
        if clash:
            logger.error("APP_USERNAME=%s уже занят обычным пользователем, логин админа не меняем", username)
        else:
            admin.username = username
            changed = True
    if not verify_password(settings.app_password, admin.password_hash):
        admin.password_hash = hash_password(settings.app_password)
        changed = True
    if admin.status != USER_ACTIVE:
        admin.status = USER_ACTIVE
        changed = True
    if changed:
        await session.commit()
