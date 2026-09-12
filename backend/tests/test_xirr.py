from datetime import date
from decimal import Decimal

from app.services.xirr import xirr


def test_xirr_ten_percent() -> None:
    rate = xirr(
        [
            (date(2021, 1, 1), Decimal("-1000")),
            (date(2022, 1, 1), Decimal("1100")),
        ]
    )
    assert rate is not None
    assert abs(rate - Decimal("0.1")) < Decimal("0.0001")


def test_xirr_needs_two_dates() -> None:
    assert xirr([(date(2021, 1, 1), Decimal("-1000"))]) is None


def test_xirr_same_sign() -> None:
    assert (
        xirr(
            [
                (date(2021, 1, 1), Decimal("-1000")),
                (date(2022, 1, 1), Decimal("-200")),
            ]
        )
        is None
    )
