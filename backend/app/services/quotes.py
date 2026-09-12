from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.services.invest_types import InvestClientError, money_to_decimal

CHUNK = 100


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
