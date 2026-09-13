from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.calendar import CalendarOut, PaymentHistoryOut
from app.services.calendar import build_calendar, load_payment_history

router = APIRouter()


@router.get("/payments", response_model=PaymentHistoryOut)
async def get_calendar_payments(
    period: str = Query(default="all"),
    year: int | None = Query(default=None),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PaymentHistoryOut:
    return await load_payment_history(
        session,
        user,
        period=period,
        year=year,
        from_day=from_day,
        to_day=to_day,
    )


@router.get("", response_model=CalendarOut)
async def get_calendar(
    refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CalendarOut:
    return await build_calendar(session, user, force_refresh=refresh)
