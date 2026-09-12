from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db import get_session
from app.models import Account, Instrument, Operation, Position, User
from app.schemas.invest import AccountOut, OperationOut, PositionOut
from app.services.sync import get_connection

router = APIRouter()


def _dec(value: Decimal | None) -> str:
    if value is None:
        return "0"
    return format(value, "f")


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Account]:
    connection = await get_connection(session, user.id)
    if connection is None:
        return []
    result = await session.execute(
        select(Account).where(Account.connection_id == connection.id).order_by(Account.id)
    )
    return list(result.scalars())


@router.get("/positions", response_model=list[PositionOut])
async def list_positions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PositionOut]:
    connection = await get_connection(session, user.id)
    if connection is None:
        return []
    result = await session.execute(
        select(Position)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .options(selectinload(Position.account))
        .order_by(Position.id)
    )
    positions = list(result.scalars())
    figis = [item.figi for item in positions if item.figi]
    instruments = await _instruments_by_figi(session, figis)
    rows: list[PositionOut] = []
    for item in positions:
        instrument = instruments.get(item.figi)
        rows.append(
            PositionOut(
                account_id=item.account_id,
                account_name=item.account.name or item.account.broker_account_id,
                figi=item.figi,
                ticker=instrument.ticker if instrument else "",
                name=instrument.name if instrument else item.figi,
                instrument_type=item.instrument_type,
                quantity=_dec(item.quantity),
                average_price=_dec(item.average_price),
                average_price_currency=item.average_price_currency,
                current_price=_dec(item.current_price),
                current_price_currency=item.current_price_currency,
            )
        )
    return rows


@router.get("/operations", response_model=list[OperationOut])
async def list_operations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[OperationOut]:
    connection = await get_connection(session, user.id)
    if connection is None:
        return []
    result = await session.execute(
        select(Operation)
        .join(Account)
        .where(Account.connection_id == connection.id)
        .options(selectinload(Operation.account))
        .order_by(Operation.occurred_at.desc())
        .limit(100)
    )
    operations = list(result.scalars())
    figis = [item.figi for item in operations if item.figi]
    instruments = await _instruments_by_figi(session, figis)
    rows: list[OperationOut] = []
    for item in operations:
        instrument = instruments.get(item.figi)
        rows.append(
            OperationOut(
                id=item.id,
                account_name=item.account.name or item.account.broker_account_id,
                broker_operation_id=item.broker_operation_id,
                operation_type=item.operation_type,
                name=item.name,
                figi=item.figi,
                ticker=instrument.ticker if instrument else "",
                quantity=_dec(item.quantity),
                payment=_dec(item.payment),
                currency=item.currency,
                occurred_at=item.occurred_at,
            )
        )
    return rows


async def _instruments_by_figi(session: AsyncSession, figis: list[str]) -> dict[str, Instrument]:
    unique = list({item for item in figis if item})
    if not unique:
        return {}
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(unique)))
    return {item.figi: item for item in result.scalars()}
