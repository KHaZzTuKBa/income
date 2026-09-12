from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from app.services.invest_types import InvestClientError, money_to_decimal, to_utc

logger = logging.getLogger("portfel.quotes")

CHUNK = 100
CANDLE_WINDOW = timedelta(days=360)
MOSCOW = ZoneInfo("Europe/Moscow")
IMOEX_URL = "https://iss.moex.com/iss/history/engines/stock/markets/index/boards/SNDX/securities/IMOEX.json"
MOEX_HEADERS = {"User-Agent": "portfel/1.0"}


async def fetch_last_prices(token: str, figis: Sequence[str]) -> dict[str, Decimal]:
    try:
        from t_tech.invest import AsyncClient
    except ImportError:
        try:
            from tinkoff.invest import AsyncClient
        except ImportError as exc:
            raise InvestClientError("Не установлен пакет t-tech-investments") from exc

    unique: list[str] = []
    seen: set[str] = set()
    for figi in figis:
        if figi and figi not in seen:
            seen.add(figi)
            unique.append(figi)

    result: dict[str, Decimal] = {}
    if not unique:
        return result

    async with AsyncClient(token) as client:
        for offset in range(0, len(unique), CHUNK):
            chunk = unique[offset : offset + CHUNK]
            response = await _get_last_prices(client, chunk)
            for item in getattr(response, "last_prices", None) or []:
                figi = str(getattr(item, "figi", "") or "")
                if not figi:
                    continue
                result[figi] = money_to_decimal(getattr(item, "price", None))
    return result


async def _get_last_prices(client, chunk: list[str]):
    try:
        return await client.market_data.get_last_prices(figi=chunk)
    except TypeError:
        return await client.market_data.get_last_prices(instrument_id=chunk)


async def fetch_daily_candles(
    token: str,
    figi: str,
    start: date,
    end: date,
) -> list[tuple[date, Decimal]]:
    if not figi or start > end:
        return []
    try:
        from t_tech.invest import AsyncClient, CandleInterval
    except ImportError:
        try:
            from tinkoff.invest import AsyncClient, CandleInterval
        except ImportError as exc:
            raise InvestClientError("Не установлен пакет t-tech-investments") from exc

    interval = getattr(CandleInterval, "CANDLE_INTERVAL_DAY", None) or getattr(
        CandleInterval, "DAY", 5
    )
    result: dict[date, Decimal] = {}
    cursor = datetime.combine(start, datetime.min.time(), tzinfo=MOSCOW).astimezone(timezone.utc)
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=MOSCOW).astimezone(
        timezone.utc
    )
    async with AsyncClient(token) as client:
        while cursor < finish:
            chunk_end = min(cursor + CANDLE_WINDOW, finish)
            try:
                response = await _get_candles(client, figi, cursor, chunk_end, interval)
            except Exception:
                logger.warning("Daily candles failed figi=%s from=%s", figi, cursor.date())
                cursor = chunk_end
                continue
            for candle in getattr(response, "candles", None) or []:
                day = to_utc(getattr(candle, "time", None)).astimezone(MOSCOW).date()
                close = money_to_decimal(getattr(candle, "close", None))
                if close > 0:
                    result[day] = close
            cursor = chunk_end
    return sorted(result.items())


async def _get_candles(client, figi: str, start: datetime, end: datetime, interval) -> object:
    try:
        return await client.market_data.get_candles(
            figi=figi, from_=start, to=end, interval=interval
        )
    except TypeError:
        return await client.market_data.get_candles(
            instrument_id=figi, from_=start, to=end, interval=interval
        )


async def fetch_imoex(start: date, end: date) -> dict[date, Decimal]:
    if start > end:
        return {}
    result: dict[date, Decimal] = {}
    offset = 0
    try:
        async with httpx.AsyncClient(timeout=20, headers=MOEX_HEADERS) as client:
            while True:
                response = await client.get(
                    IMOEX_URL,
                    params={
                        "from": start.isoformat(),
                        "till": end.isoformat(),
                        "start": offset,
                        "iss.meta": "off",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                history = payload.get("history") or {}
                columns = [str(item) for item in history.get("columns") or []]
                rows = history.get("data") or []
                if not rows:
                    break
                date_idx = columns.index("TRADEDATE") if "TRADEDATE" in columns else 1
                close_idx = columns.index("CLOSE") if "CLOSE" in columns else 3
                for row in rows:
                    try:
                        day = date.fromisoformat(str(row[date_idx])[:10])
                        close = Decimal(str(row[close_idx]))
                    except Exception:
                        continue
                    if close > 0:
                        result[day] = close
                offset += len(rows)
                if len(rows) < 100:
                    break
    except Exception:
        logger.warning("IMOEX history unavailable", exc_info=True)
    return result
