from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models import BrokerConnection, User
from app.schemas.invest import ConnectionOut, TokenIn
from app.services.crypto import encrypt_secret, token_hint
from app.services.invest import ping_token
from app.services.invest_types import InvestClientError
from app.services.sync import connection_stats, get_connection

router = APIRouter()


def _hint_display(hint: str | None) -> str | None:
    if not hint:
        return None
    return f"••••{hint}"


@router.get("/connection", response_model=ConnectionOut)
async def get_connection_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConnectionOut:
    connection = await get_connection(session, user.id)
    if connection is None:
        return ConnectionOut(configured=False)
    accounts, operations, positions = await connection_stats(session, connection.id)
    return ConnectionOut(
        configured=True,
        token_hint=_hint_display(connection.token_hint),
        status=connection.status,
        last_sync_at=connection.last_sync_at,
        last_error=connection.last_error,
        history_from=connection.history_from,
        accounts_count=accounts,
        operations_count=operations,
        positions_count=positions,
    )


@router.put("/connection", response_model=ConnectionOut)
async def save_connection(
    body: TokenIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConnectionOut:
    token = body.token.strip()
    try:
        await ping_token(token)
    except InvestClientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    connection = await get_connection(session, user.id)
    now = datetime.now(timezone.utc)
    if connection is None:
        connection = BrokerConnection(user_id=user.id, token_encrypted="", token_hint="")
        session.add(connection)
    connection.token_encrypted = encrypt_secret(token)
    connection.token_hint = token_hint(token)
    connection.status = "idle"
    connection.last_error = None
    connection.updated_at = now
    await session.commit()
    await session.refresh(connection)

    accounts, operations, positions = await connection_stats(session, connection.id)
    return ConnectionOut(
        configured=True,
        token_hint=_hint_display(connection.token_hint),
        status=connection.status,
        last_sync_at=connection.last_sync_at,
        last_error=connection.last_error,
        history_from=connection.history_from,
        accounts_count=accounts,
        operations_count=operations,
        positions_count=positions,
    )
