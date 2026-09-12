from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import SyncRun, User
from app.schemas.invest import SyncRunOut
from app.services.sync import (
    SyncConflict,
    SyncNotConfigured,
    begin_manual_sync,
    get_connection,
    run_sync_job,
)

router = APIRouter()


@router.post("", response_model=SyncRunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_sync(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncRun:
    try:
        run = await begin_manual_sync(session, user.id)
    except SyncNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SyncConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background.add_task(run_sync_job, run.connection_id, run.id)
    return run


@router.get("/runs", response_model=list[SyncRunOut])
async def list_sync_runs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SyncRun]:
    connection = await get_connection(session, user.id)
    if connection is None:
        return []
    result = await session.execute(
        select(SyncRun)
        .where(SyncRun.connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
        .limit(20)
    )
    return list(result.scalars())
