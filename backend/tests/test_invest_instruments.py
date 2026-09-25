from types import SimpleNamespace

from app.services.invest import (
    _load_instruments,
    normalize_instrument_type,
)


class _IdType:
    INSTRUMENT_ID_TYPE_FIGI = "figi"


class _Catalog:
    def __init__(self, shares=None, bonds=None, etfs=None, currencies=None, by_figi=None, share_by=None):
        self.shares_list = shares or []
        self.bonds_list = bonds or []
        self.etfs_list = etfs or []
        self.currencies_list = currencies or []
        self.by_figi = by_figi
        self.share_by_payload = share_by
        self.get_instrument_by_calls = 0
        self.share_by_calls = 0

    async def shares(self, **_kwargs):
        return SimpleNamespace(instruments=self.shares_list)

    async def bonds(self, **_kwargs):
        return SimpleNamespace(instruments=self.bonds_list)

    async def etfs(self, **_kwargs):
        return SimpleNamespace(instruments=self.etfs_list)

    async def currencies(self, **_kwargs):
        return SimpleNamespace(instruments=self.currencies_list)

    async def get_instrument_by(self, **_kwargs):
        self.get_instrument_by_calls += 1
        if self.by_figi is None:
            raise RuntimeError("not found")
        return SimpleNamespace(instrument=self.by_figi)

    async def share_by(self, **_kwargs):
        self.share_by_calls += 1
        if self.share_by_payload is None:
            raise RuntimeError("typed not found")
        return SimpleNamespace(instrument=self.share_by_payload)


def test_normalize_instrument_type() -> None:
    assert normalize_instrument_type("INSTRUMENT_TYPE_SHARE") == "share"
    assert normalize_instrument_type("shares") == "share"
    assert normalize_instrument_type("bond") == "bond"
    assert normalize_instrument_type("") == ""


async def test_load_instruments_from_shares_catalog() -> None:
    share = SimpleNamespace(
        figi="BBG004730N88",
        ticker="SBER",
        isin="RU0009029540",
        name="Сбербанк",
        currency="rub",
        lot=1,
        uid="uid-sber",
        sector="financial",
        nominal=None,
    )
    instruments = _Catalog(shares=[share])
    client = SimpleNamespace(instruments=instruments)

    rows = await _load_instruments(client, _IdType, {"BBG004730N88"})

    assert instruments.get_instrument_by_calls == 0
    assert len(rows) == 1
    assert rows[0].ticker == "SBER"
    assert rows[0].name == "Сбербанк"
    assert rows[0].sector == "financial"
    assert rows[0].instrument_type == "share"


async def test_load_instruments_stub_when_lookup_fails() -> None:
    instruments = _Catalog()
    client = SimpleNamespace(instruments=instruments)

    rows = await _load_instruments(client, _IdType, {"BBG004730N88"})

    assert instruments.get_instrument_by_calls == 1
    assert len(rows) == 1
    assert rows[0].figi == "BBG004730N88"
    assert rows[0].name == "BBG004730N88"
    assert rows[0].ticker == ""
    assert rows[0].sector == ""


async def test_load_instruments_share_kind_enum_uses_share_by() -> None:
    generic = SimpleNamespace(
        figi="BBG004730N88",
        ticker="SBER",
        isin="RU0009029540",
        name="Сбербанк",
        instrument_type="",
        instrument_kind=SimpleNamespace(name="INSTRUMENT_TYPE_SHARE"),
        currency="RUB",
        lot=1,
        uid="uid-sber",
        sector="",
        nominal=None,
    )
    typed = SimpleNamespace(
        figi="BBG004730N88",
        ticker="SBER",
        name="Сбербанк",
        sector="financial",
        currency="RUB",
        lot=1,
        uid="uid-sber",
        isin="RU0009029540",
        nominal=None,
    )
    instruments = _Catalog(by_figi=generic, share_by=typed)
    client = SimpleNamespace(instruments=instruments)

    rows = await _load_instruments(client, _IdType, {"BBG004730N88"})

    assert instruments.get_instrument_by_calls == 1
    assert instruments.share_by_calls == 1
    assert rows[0].ticker == "SBER"
    assert rows[0].instrument_type == "share"
    assert rows[0].sector == "financial"
