from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.models.history import PortfolioSnapshot
from app.schemas.history import HistoryOut
from app.services.history import (
    account_snapshots_exist,
    load_history,
    rebuild_history,
    should_rebuild_in_request,
)
from app.services.sync import get_connection
from app.services.xirr import moscow_today

router = APIRouter()


@router.get("", response_model=HistoryOut)
async def get_history(
    background: BackgroundTasks,
    refresh: bool = Query(default=False),
    period: str = Query(default="all"),
    year: int | None = Query(default=None),
    from_day: date | None = Query(default=None, alias="from"),
    to_day: date | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HistoryOut:
    user_id = user.id
    connection = await get_connection(session, user_id)
    if connection is None:
        return HistoryOut(building=False, period=period, points=[], series=[])
    connection_id = connection.id
    missing_accounts = not await account_snapshots_exist(session, connection_id)
    if refresh or missing_accounts:
        if refresh or should_rebuild_in_request():
            await rebuild_history(connection_id, force=True)
            session.expire_all()
            connection = await get_connection(session, user_id)
    elif should_rebuild_in_request():
        last = await session.scalar(
            select(func.max(PortfolioSnapshot.day)).where(
                PortfolioSnapshot.connection_id == connection_id
            )
        )
        if last is None or last < moscow_today() - timedelta(days=1):
            background.add_task(rebuild_history, connection_id)
    return await load_history(
        session,
        connection,
        period=period,
        year=year,
        from_day=from_day,
        to_day=to_day,
    )
