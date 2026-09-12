from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.services.invest_types import (
    ACCOUNT_STATUS_MAP,
    ACCOUNT_TYPE_MAP,
    AccountDTO,
    InstrumentDTO,
    InvestClientError,
    InvestPayload,
    OperationDTO,
    PositionDTO,
    enum_name,
    money_to_decimal,
    to_utc,
)

logger = logging.getLogger("portfel.invest")

HISTORY_FROM = datetime(2015, 1, 1, tzinfo=timezone.utc)
MAX_OPERATIONS = 200_000


def _map_account_type(raw: object) -> str:
    return ACCOUNT_TYPE_MAP.get(enum_name(raw), "other")


def _map_account_status(raw: object) -> str:
    return ACCOUNT_STATUS_MAP.get(enum_name(raw), "open")


def _currency_of(value: object | None, fallback: str = "RUB") -> str:
    if value is None:
        return fallback
    currency = getattr(value, "currency", None)
    return str(currency).upper() if currency else fallback


async def ping_token(token: str) -> None:
    """Проверяет токен через GetAccounts, без полной выгрузки."""
    await load_invest_data(token, accounts_only=True)


async def load_invest_data(token: str, *, accounts_only: bool = False) -> InvestPayload:
    try:
        from t_tech.invest import (
            AsyncClient,
            GetOperationsByCursorRequest,
            InstrumentIdType,
            OperationState,
        )
    except ImportError:
        try:
            from tinkoff.invest import (
                AsyncClient,
                GetOperationsByCursorRequest,
                InstrumentIdType,
                OperationState,
            )
        except ImportError as exc:
            raise InvestClientError("Не установлен пакет t-tech-investments") from exc

    payload = InvestPayload()
    try:
        async with AsyncClient(token) as client:
            response = await client.users.get_accounts()
            for account in response.accounts:
                payload.accounts.append(
                    AccountDTO(
                        broker_account_id=account.id,
                        name=account.name or "",
                        type=_map_account_type(account.type),
                        status=_map_account_status(account.status),
                        access_level=enum_name(account.access_level),
                    )
                )
            if accounts_only:
                return payload

            figi_needed: set[str] = set()
            now = datetime.now(timezone.utc)
            for account in payload.accounts:
                await _load_operations(client, GetOperationsByCursorRequest, OperationState, account, payload, now)
                if account.status == "open":
                    await _load_positions(client, account, payload, figi_needed)

            for operation in payload.operations:
                if operation.figi:
                    figi_needed.add(operation.figi)

            payload.instruments = await _load_instruments(client, InstrumentIdType, figi_needed)
    except InvestClientError:
        raise
    except Exception as exc:
        logger.exception("Invest API request failed")
        raise InvestClientError(_public_invest_error(exc)) from exc

    return payload


def _public_invest_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "unauthenticated" in lowered or "401" in lowered or "permission" in lowered:
        return "Invest API не принял токен. Нужен действующий read-only токен."
    if "resource_exhausted" in lowered or "429" in lowered:
        return "Invest API временно ограничил частоту запросов. Повторите синхронизацию позже."
    return "Invest API недоступен или вернул ошибку. Подробности в логе сервера, токен не записывается."


async def _load_operations(client, request_cls, operation_state, account: AccountDTO, payload: InvestPayload, now: datetime) -> None:
    cursor = ""
    fetched = 0
    while True:
        request = request_cls(
            account_id=account.broker_account_id,
            cursor=cursor,
            limit=1000,
            from_=HISTORY_FROM,
            to=now,
            state=operation_state.OPERATION_STATE_EXECUTED,
            without_commissions=False,
            without_trades=True,
        )
        page = await client.operations.get_operations_by_cursor(request)
        items = getattr(page, "items", None) or []
        for item in items:
            payload.operations.append(
                OperationDTO(
                    broker_account_id=account.broker_account_id,
                    broker_operation_id=str(item.id),
                    parent_operation_id=str(getattr(item, "parent_operation_id", "") or ""),
                    figi=str(getattr(item, "figi", "") or ""),
                    instrument_uid=str(getattr(item, "instrument_uid", "") or ""),
                    operation_type=enum_name(getattr(item, "type", None)),
                    name=str(getattr(item, "name", "") or getattr(item, "description", "") or ""),
                    state=enum_name(getattr(item, "state", None)),
                    quantity=_as_decimal(getattr(item, "quantity", 0)),
                    price=money_to_decimal(getattr(item, "price", None)),
                    payment=money_to_decimal(getattr(item, "payment", None)),
                    commission=money_to_decimal(getattr(item, "commission", None)),
                    currency=_currency_of(getattr(item, "payment", None)),
                    occurred_at=to_utc(getattr(item, "date", None)),
                )
            )
            fetched += 1
        if fetched >= MAX_OPERATIONS:
            payload.notes.append(
                f"Счёт {account.name or account.broker_account_id}: достигнут лимит {MAX_OPERATIONS} операций."
            )
            break
        if not getattr(page, "has_next", False):
            break
        cursor = str(getattr(page, "next_cursor", "") or "")
        if not cursor:
            break


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


async def _load_positions(client, account: AccountDTO, payload: InvestPayload, figi_needed: set[str]) -> None:

    portfolio = await client.operations.get_portfolio(account_id=account.broker_account_id)
    seen: set[str] = set()
    for position in portfolio.positions:
        figi = str(getattr(position, "figi", "") or "")
        if not figi:
            continue
        seen.add(figi)
        figi_needed.add(figi)
        average = getattr(position, "average_position_price", None)
        current = getattr(position, "current_price", None)
        payload.positions.append(
            PositionDTO(
                broker_account_id=account.broker_account_id,
                figi=figi,
                instrument_uid=str(getattr(position, "instrument_uid", "") or ""),
                instrument_type=str(getattr(position, "instrument_type", "") or ""),
                quantity=money_to_decimal(getattr(position, "quantity", None)),
                average_price=money_to_decimal(average),
                average_price_currency=_currency_of(average),
                current_price=money_to_decimal(current),
                current_price_currency=_currency_of(current),
                source="portfolio",
            )
        )

    try:
        raw_positions = await client.operations.get_positions(account_id=account.broker_account_id)
    except Exception:
        logger.exception("GetPositions failed for %s", account.broker_account_id)
        payload.notes.append(
            f"Счёт {account.name or account.broker_account_id}: GetPositions недоступен, взяли только GetPortfolio."
        )
        return

    for money in getattr(raw_positions, "money", None) or []:
        amount_source = getattr(money, "available_value", None) or money
        currency = _currency_of(amount_source, str(getattr(money, "currency", "") or "").upper())
        figi = _currency_figi(currency)
        if not figi or figi in seen:
            continue
        amount = money_to_decimal(amount_source)
        if amount == Decimal("0"):
            continue
        payload.positions.append(
            PositionDTO(
                broker_account_id=account.broker_account_id,
                figi=figi,
                instrument_uid="",
                instrument_type="currency",
                quantity=amount,
                average_price=Decimal("1"),
                average_price_currency=currency or "RUB",
                current_price=Decimal("1"),
                current_price_currency=currency or "RUB",
                source="positions",
            )
        )
        figi_needed.add(figi)


def _currency_figi(currency: str) -> str:
    mapping = {
        "RUB": "RUB000UTSTOM",
        "USD": "BBG0013HGFT4",
        "EUR": "BBG0013HJJ31",
        "CNY": "BBG0013HRTL0",
        "GBP": "BBG0013HQ5F0",
    }
    return mapping.get(currency, "")


async def _load_instruments(client, instrument_id_type, figis: set[str]) -> list[InstrumentDTO]:
    result: list[InstrumentDTO] = []
    for figi in sorted(figis):
        if not figi:
            continue
        try:
            response = await client.instruments.get_instrument_by(
                id_type=instrument_id_type.INSTRUMENT_ID_TYPE_FIGI,
                id=figi,
            )
            instrument = response.instrument
            result.append(
                InstrumentDTO(
                    figi=figi,
                    ticker=str(getattr(instrument, "ticker", "") or ""),
                    isin=str(getattr(instrument, "isin", "") or ""),
                    name=str(getattr(instrument, "name", "") or ""),
                    instrument_type=str(
                        getattr(instrument, "instrument_type", "")
                        or enum_name(getattr(instrument, "instrument_kind", None))
                    ),
                    currency=str(getattr(instrument, "currency", "") or "RUB").upper(),
                    lot=int(getattr(instrument, "lot", 1) or 1),
                    uid=str(getattr(instrument, "uid", "") or ""),
                )
            )
        except Exception:
            logger.warning("Instrument not found for figi=%s", figi)
            result.append(InstrumentDTO(figi=figi, name=figi))
    return result
