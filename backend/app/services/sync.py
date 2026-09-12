from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db as db_module
from app.models import Account, BrokerConnection, Instrument, Operation, Position, SyncRun
from app.services.crypto import CryptoError, decrypt_secret
from app.services.invest import load_invest_data
from app.services.invest_types import (
    BUY_TYPES,
    SELL_TYPES,
    InvestClientError,
    InvestPayload,
    OperationDTO,
)

logger = logging.getLogger("portfel.sync")

STALE_AFTER = timedelta(minutes=45)


class SyncConflict(Exception):
    pass


class SyncNotConfigured(Exception):
    pass


async def get_connection(session: AsyncSession, user_id: int) -> BrokerConnection | None:
    result = await session.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def begin_manual_sync(session: AsyncSession, user_id: int) -> SyncRun:
    connection = await get_connection(session, user_id)
    if connection is None:
        raise SyncNotConfigured("Сначала сохраните токен Т‑Инвестиций")
    _ensure_not_running(connection)
    return await _create_run(session, connection, trigger="manual")


async def run_sync_job(connection_id: int, run_id: int) -> None:
    async with db_module.SessionLocal() as session:
        connection = await session.get(BrokerConnection, connection_id)
        run = await session.get(SyncRun, run_id)
        if connection is None or run is None:
            return
        try:
            token = decrypt_secret(connection.token_encrypted)
            payload = await load_invest_data(token)
            await persist_payload(session, connection, run, payload)
            run.status = "ok"
            run.finished_at = datetime.now(timezone.utc)
            connection.status = "ok"
            connection.last_error = None
            connection.last_sync_at = run.finished_at
            connection.updated_at = run.finished_at
            await session.commit()
        except (InvestClientError, CryptoError) as exc:
            await session.rollback()
            await _fail_run(connection_id, run_id, str(exc))
            return
        except Exception:
            logger.exception("Sync failed")
            await session.rollback()
            await _fail_run(connection_id, run_id, "Синхронизация оборвалась. Подробности в логе сервера.")
            return
    try:
        from app.services.history import rebuild_history

        await rebuild_history(connection_id, force=True)
    except Exception:
        logger.exception("History rebuild failed id=%s", connection_id)


async def run_scheduled_sync() -> None:
    async with db_module.SessionLocal() as session:
        result = await session.execute(select(BrokerConnection))
        connections = list(result.scalars())

    for connection in connections:
        async with db_module.SessionLocal() as session:
            conn = await session.get(BrokerConnection, connection.id)
            if conn is None:
                continue
            try:
                _ensure_not_running(conn)
            except SyncConflict:
                logger.info("Skip scheduled sync, already running id=%s", conn.id)
                continue
            run = await _create_run(session, conn, trigger="schedule")
            run_id = run.id
            conn_id = conn.id
        await run_sync_job(conn_id, run_id)


def _ensure_not_running(connection: BrokerConnection) -> None:
    if connection.status != "running":
        return
    if connection.updated_at and datetime.now(timezone.utc) - _aware(connection.updated_at) > STALE_AFTER:
        return
    raise SyncConflict("Синхронизация уже выполняется")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _create_run(session: AsyncSession, connection: BrokerConnection, trigger: str) -> SyncRun:
    now = datetime.now(timezone.utc)
    run = SyncRun(connection_id=connection.id, trigger=trigger, status="running", started_at=now)
    connection.status = "running"
    connection.last_error = None
    connection.updated_at = now
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _fail_run(connection_id: int, run_id: int, message: str) -> None:
    async with db_module.SessionLocal() as session:
        connection = await session.get(BrokerConnection, connection_id)
        run = await session.get(SyncRun, run_id)
        now = datetime.now(timezone.utc)
        if run is not None:
            run.status = "error"
            run.finished_at = now
            run.error_message = message
        if connection is not None:
            connection.status = "error"
            connection.last_error = message
            connection.updated_at = now
        await session.commit()


async def persist_payload(
    session: AsyncSession,
    connection: BrokerConnection,
    run: SyncRun,
    payload: InvestPayload,
) -> None:
    account_map = await _upsert_accounts(session, connection.id, payload)
    instruments_count = await _upsert_instruments(session, payload)
    operations_count = await _upsert_operations(session, account_map, payload.operations)
    positions_count = await _replace_positions(session, account_map, payload)
    notes = list(payload.notes)
    notes.extend(_position_discrepancies(payload))
    history_from = None
    if payload.operations:
        history_from = min(item.occurred_at for item in payload.operations).date()

    run.accounts_count = len(payload.accounts)
    run.operations_count = operations_count
    run.instruments_count = instruments_count
    run.positions_count = positions_count
    run.notes = "\n".join(notes) if notes else None
    connection.history_from = history_from
    if history_from is not None:
        extra = f"История операций с {history_from.isoformat()}."
        run.notes = f"{run.notes}\n{extra}" if run.notes else extra


async def _upsert_accounts(
    session: AsyncSession,
    connection_id: int,
    payload: InvestPayload,
) -> dict[str, Account]:
    result = await session.execute(select(Account).where(Account.connection_id == connection_id))
    existing = {item.broker_account_id: item for item in result.scalars()}
    mapping: dict[str, Account] = {}
    for dto in payload.accounts:
        account = existing.get(dto.broker_account_id)
        if account is None:
            account = Account(
                connection_id=connection_id,
                broker_account_id=dto.broker_account_id,
            )
            session.add(account)
        account.name = dto.name
        account.type = dto.type
        account.status = dto.status
        account.access_level = dto.access_level
        mapping[dto.broker_account_id] = account
    await session.flush()
    return mapping


async def _upsert_instruments(session: AsyncSession, payload: InvestPayload) -> int:
    if not payload.instruments:
        return 0
    figis = [item.figi for item in payload.instruments if item.figi]
    if not figis:
        return 0
    result = await session.execute(select(Instrument).where(Instrument.figi.in_(figis)))
    existing = {item.figi: item for item in result.scalars()}
    for dto in payload.instruments:
        if not dto.figi:
            continue
        instrument = existing.get(dto.figi)
        if instrument is None:
            instrument = Instrument(figi=dto.figi)
            session.add(instrument)
        instrument.ticker = dto.ticker
        instrument.isin = dto.isin
        instrument.name = dto.name
        instrument.instrument_type = dto.instrument_type
        instrument.currency = dto.currency
        instrument.lot = dto.lot
        instrument.uid = dto.uid
        instrument.nominal = dto.nominal
        instrument.nominal_currency = dto.nominal_currency
    await session.flush()
    return len(figis)


async def _upsert_operations(
    session: AsyncSession,
    account_map: dict[str, Account],
    operations: list[OperationDTO],
) -> int:
    if not operations:
        return 0
    grouped: dict[int, list[OperationDTO]] = defaultdict(list)
    for item in operations:
        account = account_map.get(item.broker_account_id)
        if account is None or not item.broker_operation_id:
            continue
        grouped[account.id].append(item)

    total = 0
    for account_id, items in grouped.items():
        chunk_size = 400
        for offset in range(0, len(items), chunk_size):
            chunk = items[offset : offset + chunk_size]
            ids = [item.broker_operation_id for item in chunk]
            result = await session.execute(
                select(Operation).where(
                    Operation.account_id == account_id,
                    Operation.broker_operation_id.in_(ids),
                )
            )
            existing = {row.broker_operation_id: row for row in result.scalars()}
            for dto in chunk:
                row = existing.get(dto.broker_operation_id)
                if row is None:
                    row = Operation(
                        account_id=account_id,
                        broker_operation_id=dto.broker_operation_id,
                    )
                    session.add(row)
                row.parent_operation_id = dto.parent_operation_id
                row.figi = dto.figi
                row.instrument_uid = dto.instrument_uid
                row.operation_type = dto.operation_type
                row.name = dto.name
                row.state = dto.state
                row.quantity = dto.quantity
                row.price = dto.price
                row.payment = dto.payment
                row.commission = dto.commission
                row.currency = dto.currency
                row.occurred_at = dto.occurred_at
                total += 1
            await session.flush()
    return total


async def _replace_positions(
    session: AsyncSession,
    account_map: dict[str, Account],
    payload: InvestPayload,
) -> int:
    account_ids = [account.id for account in account_map.values()]
    if account_ids:
        await session.execute(delete(Position).where(Position.account_id.in_(account_ids)))
        await session.flush()

    count = 0
    seen: set[tuple[int, str]] = set()
    for dto in payload.positions:
        account = account_map.get(dto.broker_account_id)
        if account is None or not dto.figi:
            continue
        key = (account.id, dto.figi)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            Position(
                account_id=account.id,
                figi=dto.figi,
                instrument_uid=dto.instrument_uid,
                instrument_type=dto.instrument_type,
                quantity=dto.quantity,
                average_price=dto.average_price,
                average_price_currency=dto.average_price_currency,
                current_price=dto.current_price,
                current_price_currency=dto.current_price_currency,
            )
        )
        count += 1
    await session.flush()
    return count


def _position_discrepancies(payload: InvestPayload) -> list[str]:
    reconstructed: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for operation in payload.operations:
        if not operation.figi:
            continue
        key = (operation.broker_account_id, operation.figi)
        if operation.operation_type in BUY_TYPES:
            reconstructed[key] += operation.quantity
        elif operation.operation_type in SELL_TYPES:
            reconstructed[key] -= operation.quantity

    notes: list[str] = []
    for position in payload.positions:
        if position.instrument_type == "currency":
            continue
        key = (position.broker_account_id, position.figi)
        expected = reconstructed.get(key)
        if expected is None:
            continue
        if abs(expected - position.quantity) > Decimal("0.0001"):
            notes.append(
                f"Расхождение {position.figi}: GetPortfolio={position.quantity}, из операций={expected}. Журнал не затирали."
            )
    return notes


async def connection_stats(session: AsyncSession, connection_id: int) -> tuple[int, int, int]:
    accounts = await session.scalar(
        select(func.count()).select_from(Account).where(Account.connection_id == connection_id)
    )
    account_ids = select(Account.id).where(Account.connection_id == connection_id)
    operations = await session.scalar(
        select(func.count()).select_from(Operation).where(Operation.account_id.in_(account_ids))
    )
    positions = await session.scalar(
        select(func.count()).select_from(Position).where(Position.account_id.in_(account_ids))
    )
    return int(accounts or 0), int(operations or 0), int(positions or 0)
