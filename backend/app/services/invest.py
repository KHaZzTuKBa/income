from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.invest_types import (
    ACCOUNT_STATUS_MAP,
    ACCOUNT_TYPE_MAP,
    CURRENCY_FIGI,
    AccountDTO,
    ForecastDTO,
    InstrumentDTO,
    InvestClientError,
    InvestPayload,
    OperationDTO,
    PositionDTO,
    canonical_cash_figi,
    currency_code_of,
    enum_name,
    money_to_decimal,
    to_utc,
)

logger = logging.getLogger("portfel.invest")
MOSCOW = ZoneInfo("Europe/Moscow")

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


async def fetch_instrument_nominals(token: str, figis: list[str]) -> dict[str, tuple[Decimal, str]]:
    try:
        from t_tech.invest import AsyncClient, InstrumentIdType
    except ImportError:
        try:
            from tinkoff.invest import AsyncClient, InstrumentIdType
        except ImportError as exc:
            raise InvestClientError("Не установлен пакет t-tech-investments") from exc

    result: dict[str, tuple[Decimal, str]] = {}
    unique = [figi for figi in dict.fromkeys(figis) if figi]
    if not unique:
        return result
    async with AsyncClient(token) as client:
        for figi in unique:
            try:
                amount, currency = await _bond_nominal(client, InstrumentIdType, figi)
                if amount > 0:
                    result[figi] = (amount, currency)
            except Exception:
                logger.warning("Nominal not found for figi=%s", figi)
    return result


async def fetch_income_forecasts(
    token: str,
    instruments: list[tuple[str, str]],
    start: datetime,
    end: datetime,
) -> list[ForecastDTO]:
    try:
        from t_tech.invest import AsyncClient
    except ImportError:
        try:
            from tinkoff.invest import AsyncClient
        except ImportError as exc:
            raise InvestClientError("Не установлен пакет t-tech-investments") from exc

    result: list[ForecastDTO] = []
    async with AsyncClient(token) as client:
        for figi, instrument_type in instruments:
            if not figi:
                continue
            kind = "coupon" if (instrument_type or "").lower() in {"bond", "bonds"} else "dividend"
            try:
                if kind == "coupon":
                    result.extend(await _load_coupons(client, figi, start, end))
                else:
                    result.extend(await _load_dividends(client, figi, start, end))
            except Exception:
                logger.warning("Income forecast failed for figi=%s", figi)
    return result


async def _load_dividends(client, figi: str, start: datetime, end: datetime) -> list[ForecastDTO]:
    response = await _call_income(client.instruments.get_dividends, figi, start, end)
    items = getattr(response, "dividends", None) or []
    result: list[ForecastDTO] = []
    for item in items:
        event_date = _event_date(
            getattr(item, "payment_date", None),
            getattr(item, "record_date", None),
            getattr(item, "last_buy_date", None),
        )
        if event_date is None:
            continue
        money = getattr(item, "dividend_net", None)
        result.append(
            ForecastDTO(
                figi=figi,
                kind="dividend",
                status="declared",
                event_date=event_date,
                amount_per_unit=money_to_decimal(money),
                currency=_currency_of(money, "RUB"),
            )
        )
    return result


async def _load_coupons(client, figi: str, start: datetime, end: datetime) -> list[ForecastDTO]:
    response = await _call_income(client.instruments.get_bond_coupons, figi, start, end)
    items = getattr(response, "events", None) or getattr(response, "coupons", None) or []
    result: list[ForecastDTO] = []
    for item in items:
        event_date = _event_date(getattr(item, "coupon_date", None), getattr(item, "fix_date", None))
        if event_date is None:
            continue
        money = getattr(item, "pay_one_bond", None)
        result.append(
            ForecastDTO(
                figi=figi,
                kind="coupon",
                status="forecast",
                event_date=event_date,
                amount_per_unit=money_to_decimal(money),
                currency=_currency_of(money, "RUB"),
            )
        )
    return result


async def _call_income(method, figi: str, start: datetime, end: datetime):
    try:
        return await method(figi=figi, from_=start, to=end)
    except TypeError:
        return await method(instrument_id=figi, from_=start, to=end)


def _event_date(*values: object) -> date | None:
    for value in values:
        if value is None:
            continue
        try:
            return to_utc(value).astimezone(MOSCOW).date()
        except Exception:
            continue
    return None


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
    seen_currencies: set[str] = set()
    for position in portfolio.positions:
        figi = str(getattr(position, "figi", "") or "")
        if not figi:
            continue
        instrument_type = str(getattr(position, "instrument_type", "") or "")
        average = getattr(position, "average_position_price", None)
        current = getattr(position, "current_price", None)
        if instrument_type.lower() in {"currency", "currencies"}:
            currency = currency_code_of(
                figi=figi,
                fallback=_currency_of(current) or _currency_of(average),
            )
            if currency:
                figi = canonical_cash_figi(figi, currency)
                if currency in seen_currencies:
                    continue
                seen_currencies.add(currency)
        if figi in seen:
            continue
        seen.add(figi)
        figi_needed.add(figi)
        payload.positions.append(
            PositionDTO(
                broker_account_id=account.broker_account_id,
                figi=figi,
                instrument_uid=str(getattr(position, "instrument_uid", "") or ""),
                instrument_type=instrument_type,
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
        if not currency or currency in seen_currencies:
            continue
        figi = _currency_figi(currency)
        if not figi or figi in seen:
            continue
        amount = money_to_decimal(amount_source)
        if amount == Decimal("0"):
            continue
        seen.add(figi)
        seen_currencies.add(currency)
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
    return CURRENCY_FIGI.get((currency or "").upper(), "")


def _nominal_from(instrument) -> tuple[Decimal, str]:
    nominal = getattr(instrument, "nominal", None) or getattr(instrument, "initial_nominal", None)
    amount = money_to_decimal(nominal)
    currency = _currency_of(nominal, str(getattr(instrument, "currency", "") or "").upper())
    return amount, currency


SHARE_TYPES = {"share", "shares", "stock"}
BOND_TYPES = {"bond", "bonds"}
ETF_TYPES = {"etf", "etfs"}
TYPE_ALIASES = {
    "shares": "share",
    "stock": "share",
    "bonds": "bond",
    "etfs": "etf",
    "currencies": "currency",
    "futures": "future",
    "options": "option",
}
CATALOG_METHODS = (
    ("shares", "share"),
    ("bonds", "bond"),
    ("etfs", "etf"),
    ("currencies", "currency"),
)
INSTRUMENT_FETCH_SLEEP = 0.05
RESOURCE_RETRIES = 3


def normalize_instrument_type(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    prefix = "instrument_type_"
    if value.startswith(prefix):
        value = value[len(prefix) :]
    return TYPE_ALIASES.get(value, value)


def _sector_of(instrument) -> str:
    return str(getattr(instrument, "sector", "") or "").strip()[:64]


def _is_resource_exhausted(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "resource_exhausted" in text or "429" in text


async def _retry_resource(factory, *, attempts: int = RESOURCE_RETRIES):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await factory()
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= attempts or not _is_resource_exhausted(exc):
                raise
            await asyncio.sleep(0.4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _instrument_status_all():
    try:
        from t_tech.invest import InstrumentStatus
    except ImportError:
        try:
            from tinkoff.invest import InstrumentStatus
        except ImportError:
            return None
    return getattr(InstrumentStatus, "INSTRUMENT_STATUS_ALL", None)


def _instrument_dto_from(instrument, default_type: str = "") -> InstrumentDTO:
    figi = str(getattr(instrument, "figi", "") or "")
    raw_type = str(getattr(instrument, "instrument_type", "") or "") or enum_name(
        getattr(instrument, "instrument_kind", None)
    )
    instrument_type = normalize_instrument_type(raw_type) or default_type
    nominal_amount, nominal_currency = _nominal_from(instrument)
    try:
        lot = int(getattr(instrument, "lot", 1) or 1)
    except (TypeError, ValueError):
        lot = 1
    return InstrumentDTO(
        figi=figi,
        ticker=str(getattr(instrument, "ticker", "") or ""),
        isin=str(getattr(instrument, "isin", "") or ""),
        name=str(getattr(instrument, "name", "") or ""),
        instrument_type=instrument_type,
        currency=str(getattr(instrument, "currency", "") or "RUB").upper(),
        lot=lot,
        uid=str(getattr(instrument, "uid", "") or ""),
        nominal=nominal_amount,
        nominal_currency=nominal_currency,
        sector=_sector_of(instrument),
    )


async def _call_catalog(method, status):
    async def _invoke():
        if status is None:
            return await method()
        try:
            return await method(instrument_status=status)
        except TypeError:
            return await method()

    return await _retry_resource(_invoke)


async def _load_instrument_catalog(client) -> dict[str, InstrumentDTO]:
    catalog: dict[str, InstrumentDTO] = {}
    status = _instrument_status_all()
    for method_name, kind in CATALOG_METHODS:
        method = getattr(client.instruments, method_name, None)
        if method is None:
            continue
        try:
            response = await _call_catalog(method, status)
        except Exception:
            logger.warning("Instrument catalog %s failed", method_name, exc_info=True)
            continue
        for item in getattr(response, "instruments", None) or []:
            figi = str(getattr(item, "figi", "") or "")
            if not figi:
                continue
            catalog[figi] = _instrument_dto_from(item, default_type=kind)
    return catalog


async def _instrument_by_figi(client, instrument_id_type, method_name: str, figi: str):
    method = getattr(client.instruments, method_name)
    return await _retry_resource(
        lambda: method(
            id_type=instrument_id_type.INSTRUMENT_ID_TYPE_FIGI,
            id=figi,
        )
    )


async def _bond_nominal(client, instrument_id_type, figi: str) -> tuple[Decimal, str]:
    response = await _instrument_by_figi(client, instrument_id_type, "bond_by", figi)
    return _nominal_from(response.instrument)


async def _typed_sector_and_nominal(
    client,
    instrument_id_type,
    figi: str,
    instrument_type: str,
    nominal_amount: Decimal,
    nominal_currency: str,
) -> tuple[str, Decimal, str]:
    kind = normalize_instrument_type(instrument_type)
    sector = ""
    if kind in BOND_TYPES:
        method_name = "bond_by"
    elif kind in SHARE_TYPES:
        method_name = "share_by"
    elif kind in ETF_TYPES:
        method_name = "etf_by"
    else:
        return sector, nominal_amount, nominal_currency
    try:
        response = await _instrument_by_figi(client, instrument_id_type, method_name, figi)
        typed = response.instrument
        sector = _sector_of(typed)
        if kind in BOND_TYPES and nominal_amount <= 0:
            nominal_amount, nominal_currency = _nominal_from(typed)
    except Exception:
        logger.warning("Typed instrument not found for figi=%s type=%s", figi, instrument_type)
    return sector, nominal_amount, nominal_currency


async def _fetch_instrument_by_figi(client, instrument_id_type, figi: str) -> InstrumentDTO | None:
    try:
        response = await _retry_resource(
            lambda: client.instruments.get_instrument_by(
                id_type=instrument_id_type.INSTRUMENT_ID_TYPE_FIGI,
                id=figi,
            )
        )
    except Exception:
        logger.warning("Instrument not found for figi=%s", figi)
        return None
    instrument = response.instrument
    dto = _instrument_dto_from(instrument)
    if not dto.figi:
        dto.figi = figi
    if dto.instrument_type in SHARE_TYPES | BOND_TYPES | ETF_TYPES:
        sector, nominal_amount, nominal_currency = await _typed_sector_and_nominal(
            client,
            instrument_id_type,
            figi,
            dto.instrument_type,
            dto.nominal,
            dto.nominal_currency,
        )
        if sector:
            dto.sector = sector
        if nominal_amount > 0:
            dto.nominal = nominal_amount
            dto.nominal_currency = nominal_currency or dto.nominal_currency
    return dto


async def _load_instruments(client, instrument_id_type, figis: set[str]) -> list[InstrumentDTO]:
    needed = [figi for figi in sorted(figis) if figi]
    if not needed:
        return []
    catalog = await _load_instrument_catalog(client)
    result: list[InstrumentDTO] = []
    missing: list[str] = []
    for figi in needed:
        dto = catalog.get(figi)
        if dto is not None:
            result.append(dto)
        else:
            missing.append(figi)
    for index, figi in enumerate(missing):
        dto = await _fetch_instrument_by_figi(client, instrument_id_type, figi)
        if dto is not None:
            result.append(dto)
        else:
            result.append(InstrumentDTO(figi=figi, name=figi))
        if index < len(missing) - 1:
            await asyncio.sleep(INSTRUMENT_FETCH_SLEEP)
    return result
