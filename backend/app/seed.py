from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.security import hash_password, verify_password


async def seed_user(session: AsyncSession) -> None:
    result = await session.execute(select(User).order_by(User.id).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        session.add(
            User(
                username=settings.app_username,
                password_hash=hash_password(settings.app_password),
            )
        )
        await session.commit()
        return

    changed = False
    if user.username != settings.app_username:
        user.username = settings.app_username
        changed = True
    if not verify_password(settings.app_password, user.password_hash):
        user.password_hash = hash_password(settings.app_password)
        changed = True
    if changed:
        await session.commit()
