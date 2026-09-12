from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import User
from app.models.history import PortfolioSnapshot
from app.schemas.history import HistoryOut
from app.services.history import load_history, rebuild_history, should_rebuild_in_request
from app.services.sync import get_connection
from app.services.xirr import moscow_today

router = APIRouter()


@router.get("", response_model=HistoryOut)
async def get_history(
    background: BackgroundTasks,
    refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HistoryOut:
    connection = await get_connection(session, user.id)
    if connection is None:
        return HistoryOut(building=False, points=[], xirr_percent=None, xirr_from=None)
    if refresh:
        await rebuild_history(connection.id, force=True)
        session.expire_all()
    elif should_rebuild_in_request():
        last = await session.scalar(
            select(func.max(PortfolioSnapshot.day)).where(
                PortfolioSnapshot.connection_id == connection.id
            )
        )
        if last is None or last < moscow_today() - timedelta(days=1):
            background.add_task(rebuild_history, connection.id)
    return await load_history(session, connection)
