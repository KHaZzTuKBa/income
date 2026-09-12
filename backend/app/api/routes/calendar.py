from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.calendar import CalendarOut
from app.services.calendar import build_calendar

router = APIRouter()


@router.get("", response_model=CalendarOut)
async def get_calendar(
    refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CalendarOut:
    return await build_calendar(session, user, force_refresh=refresh)
