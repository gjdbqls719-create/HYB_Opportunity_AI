from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.domain.trend import (
    PriceTrendAnalysis,
    PriceVolatility,
    TrendDirection,
)


def make_analysis(
    **overrides: object,
) -> PriceTrendAnalysis:
    values: dict[str, object] = {
        "current_price": Decimal("80.00"),
        "highest_price": Decimal("100.00"),
        "lowest_price": Decimal("80.00"),
        "average_price": Decimal("90.00"),
        "median_price": Decimal("90.00"),
        "price_range": Decimal("20.00"),
        "change_rate": Decimal("-20.00"),
        "direction": TrendDirection.DOWN,
        "volatility": PriceVolatility.MEDIUM,
        "near_lowest": True,
        "near_highest": False,
        "sample_count": 3,
    }
    values.update(overrides)

    return PriceTrendAnalysis(**values)


def test_trend_enums_use_stable_string_values() -> None:
    assert TrendDirection.UP.value == "up"
    assert TrendDirection.DOWN.value == "down"
    assert TrendDirection.STABLE.value == "stable"

    assert PriceVolatility.LOW.value == "low"
    assert PriceVolatility.MEDIUM.value == "medium"
    assert PriceVolatility.HIGH.value == "high"


def test_price_trend_analysis_creation() -> None:
    analysis = make_analysis()

    assert analysis.current_price == Decimal("80.00")
    assert analysis.highest_price == Decimal("100.00")
    assert analysis.lowest_price == Decimal("80.00")
    assert analysis.average_price == Decimal("90.00")
    assert analysis.median_price == Decimal("90.00")
    assert analysis.price_range == Decimal("20.00")
    assert analysis.change_rate == Decimal("-20.00")
    assert analysis.direction is TrendDirection.DOWN
    assert analysis.volatility is PriceVolatility.MEDIUM
    assert analysis.near_lowest is True
    assert analysis.near_highest is False
    assert analysis.sample_count == 3


def test_price_trend_analysis_is_immutable() -> None:
    analysis = make_analysis()

    with pytest.raises(FrozenInstanceError):
        analysis.current_price = Decimal("70.00")


@pytest.mark.parametrize(
    "field_name",
    [
        "current_price",
        "highest_price",
        "lowest_price",
        "average_price",
        "median_price",
        "price_range",
        "change_rate",
    ],
)
def test_decimal_fields_reject_non_decimal_values(
    field_name: str,
) -> None:
    with pytest.raises(TypeError):
        make_analysis(**{field_name: 1.0})


@pytest.mark.parametrize(
    "field_name",
    [
        "current_price",
        "highest_price",
        "lowest_price",
        "average_price",
        "median_price",
        "price_range",
    ],
)
def test_non_negative_price_fields_reject_negative_values(
    field_name: str,
) -> None:
    with pytest.raises(ValueError):
        make_analysis(
            **{field_name: Decimal("-0.01")}
        )


def test_change_rate_accepts_negative_value() -> None:
    analysis = make_analysis(
        change_rate=Decimal("-25.50"),
    )

    assert analysis.change_rate == Decimal("-25.50")


def test_rejects_invalid_direction_type() -> None:
    with pytest.raises(TypeError):
        make_analysis(direction="down")


def test_rejects_invalid_volatility_type() -> None:
    with pytest.raises(TypeError):
        make_analysis(volatility="medium")


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("near_lowest", 1),
        ("near_highest", 0),
    ],
)
def test_boolean_fields_require_bool(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(TypeError):
        make_analysis(**{field_name: value})


def test_sample_count_requires_integer() -> None:
    with pytest.raises(TypeError):
        make_analysis(sample_count=3.0)


def test_sample_count_must_be_positive() -> None:
    with pytest.raises(ValueError):
        make_analysis(sample_count=0)


def test_lowest_price_cannot_exceed_highest_price() -> None:
    with pytest.raises(ValueError):
        make_analysis(
            lowest_price=Decimal("110.00"),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("current_price", Decimal("110.00")),
        ("average_price", Decimal("110.00")),
        ("median_price", Decimal("70.00")),
    ],
)
def test_representative_prices_must_stay_inside_range(
    field_name: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        make_analysis(**{field_name: value})


def test_price_range_must_match_high_minus_low() -> None:
    with pytest.raises(ValueError):
        make_analysis(
            price_range=Decimal("19.99"),
        )


def test_single_sample_analysis_is_valid() -> None:
    analysis = make_analysis(
        current_price=Decimal("100.00"),
        highest_price=Decimal("100.00"),
        lowest_price=Decimal("100.00"),
        average_price=Decimal("100.00"),
        median_price=Decimal("100.00"),
        price_range=Decimal("0"),
        change_rate=Decimal("0"),
        direction=TrendDirection.STABLE,
        volatility=PriceVolatility.LOW,
        near_lowest=True,
        near_highest=True,
        sample_count=1,
    )

    assert analysis.sample_count == 1
    assert analysis.direction is TrendDirection.STABLE


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("highest_price", Decimal("110.00")),
        ("price_range", Decimal("1.00")),
        ("change_rate", Decimal("1.00")),
        ("direction", TrendDirection.UP),
    ],
)
def test_single_sample_requires_stable_consistent_values(
    field_name: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "current_price": Decimal("100.00"),
        "highest_price": Decimal("100.00"),
        "lowest_price": Decimal("100.00"),
        "average_price": Decimal("100.00"),
        "median_price": Decimal("100.00"),
        "price_range": Decimal("0"),
        "change_rate": Decimal("0"),
        "direction": TrendDirection.STABLE,
        "volatility": PriceVolatility.LOW,
        "near_lowest": True,
        "near_highest": True,
        "sample_count": 1,
    }
    values[field_name] = value

    with pytest.raises(ValueError):
        make_analysis(**values)
