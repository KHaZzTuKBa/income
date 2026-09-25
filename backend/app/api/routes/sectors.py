from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.sector import SectorsOut
from app.services.sectors import build_sectors

router = APIRouter()


@router.get("", response_model=SectorsOut)
async def get_sectors(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SectorsOut:
    return await build_sectors(session, user)
