from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.trend import (
    PriceVolatility,
    TrendDirection,
)
from app.engine.trend_analysis import (
    TrendAnalysisEngine,
    TrendAnalysisPolicy,
    analyze_price_history,
)
from storage.price_history import PriceHistoryRecord


def record(
    *,
    record_id: int,
    price: float,
    observed_at: str,
) -> PriceHistoryRecord:
    return PriceHistoryRecord(
        id=record_id,
        marketplace="ebay",
        item_id="item-1",
        title="Test Product",
        price=price,
        currency="USD",
        condition="new",
        url="https://example.com/item-1",
        observed_at=observed_at,
    )


def analyze_prices(*prices: float):
    records = [
        record(
            record_id=index,
            price=price,
            observed_at=(
                f"2026-07-27T{10 + index:02d}:00:00+00:00"
            ),
        )
        for index, price in enumerate(prices, start=1)
    ]
    return analyze_price_history(records)


def test_rejects_empty_history() -> None:
    with pytest.raises(ValueError):
        TrendAnalysisEngine().analyze([])


def test_rejects_non_record_item() -> None:
    with pytest.raises(TypeError):
        TrendAnalysisEngine().analyze([object()])


def test_single_record_statistics_and_flags() -> None:
    analysis = analyze_prices(100.0)

    assert analysis.current_price == Decimal("100.0")
    assert analysis.highest_price == Decimal("100.0")
    assert analysis.lowest_price == Decimal("100.0")
    assert analysis.average_price == Decimal("100.0")
    assert analysis.median_price == Decimal("100.0")
    assert analysis.price_range == Decimal("0.0")
    assert analysis.change_rate == Decimal("0.0")
    assert analysis.direction is TrendDirection.STABLE
    assert analysis.volatility is PriceVolatility.LOW
    assert analysis.near_lowest is True
    assert analysis.near_highest is True
    assert analysis.sample_count == 1


def test_calculates_highest_lowest_and_range() -> None:
    analysis = analyze_prices(80.0, 120.0, 100.0)

    assert analysis.highest_price == Decimal("120.0")
    assert analysis.lowest_price == Decimal("80.0")
    assert analysis.price_range == Decimal("40.0")


def test_calculates_average_price_with_decimal_precision() -> None:
    analysis = analyze_prices(0.1, 0.2)

    assert analysis.average_price == Decimal("0.15")


def test_calculates_odd_sample_median() -> None:
    analysis = analyze_prices(30.0, 10.0, 20.0)

    assert analysis.median_price == Decimal("20.0")


def test_calculates_even_sample_median() -> None:
    analysis = analyze_prices(10.0, 20.0, 30.0, 40.0)

    assert analysis.median_price == Decimal("25.0")


def test_current_price_uses_latest_observation() -> None:
    analysis = TrendAnalysisEngine().analyze(
        [
            record(
                record_id=3,
                price=90.0,
                observed_at="2026-07-27T12:00:00+00:00",
            ),
            record(
                record_id=1,
                price=100.0,
                observed_at="2026-07-27T10:00:00+00:00",
            ),
            record(
                record_id=2,
                price=95.0,
                observed_at="2026-07-27T11:00:00+00:00",
            ),
        ]
    )

    assert analysis.current_price == Decimal("90.0")
    assert analysis.change_rate == Decimal("-10.0")
    assert analysis.direction is TrendDirection.DOWN


def test_record_id_breaks_equal_timestamp_tie() -> None:
    analysis = TrendAnalysisEngine().analyze(
        [
            record(
                record_id=1,
                price=100.0,
                observed_at="2026-07-27T10:00:00+00:00",
            ),
            record(
                record_id=2,
                price=90.0,
                observed_at="2026-07-27T10:00:00+00:00",
            ),
        ]
    )

    assert analysis.current_price == Decimal("90.0")
    assert analysis.change_rate == Decimal("-10.0")
    assert analysis.direction is TrendDirection.DOWN


def test_up_direction_above_stable_threshold() -> None:
    analysis = analyze_prices(100.0, 110.0)

    assert analysis.change_rate == Decimal("10.0")
    assert analysis.direction is TrendDirection.UP


def test_down_direction_below_stable_threshold() -> None:
    analysis = analyze_prices(100.0, 85.0)

    assert analysis.change_rate == Decimal("-15.0")
    assert analysis.direction is TrendDirection.DOWN


@pytest.mark.parametrize(
    ("current_price", "expected_rate"),
    [
        (101.0, Decimal("1.0")),
        (100.5, Decimal("0.5")),
        (99.5, Decimal("-0.5")),
        (99.0, Decimal("-1.0")),
    ],
)
def test_stable_direction_within_inclusive_threshold(
    current_price: float,
    expected_rate: Decimal,
) -> None:
    analysis = analyze_prices(100.0, current_price)

    assert analysis.change_rate == expected_rate
    assert analysis.direction is TrendDirection.STABLE


def test_change_rate_rounds_half_up_to_one_decimal_place() -> None:
    analysis = analyze_prices(80.0, 81.0)

    assert analysis.change_rate == Decimal("1.3")
    assert analysis.direction is TrendDirection.UP


def test_zero_baseline_and_zero_current_are_stable() -> None:
    analysis = analyze_prices(0.0, 0.0)

    assert analysis.change_rate == Decimal("0.0")
    assert analysis.direction is TrendDirection.STABLE


def test_zero_baseline_and_positive_current_use_bounded_up_policy() -> None:
    analysis = analyze_prices(0.0, 25.0)

    assert analysis.change_rate == Decimal("100.0")
    assert analysis.direction is TrendDirection.UP


def test_low_volatility_at_five_percent_boundary() -> None:
    analysis = analyze_prices(97.5, 102.5, 100.0)

    assert analysis.volatility is PriceVolatility.LOW


def test_medium_volatility_above_five_percent() -> None:
    analysis = analyze_prices(95.0, 105.0, 100.0)

    assert analysis.volatility is PriceVolatility.MEDIUM


def test_medium_volatility_at_fifteen_percent_boundary() -> None:
    analysis = analyze_prices(92.5, 107.5, 100.0)

    assert analysis.volatility is PriceVolatility.MEDIUM


def test_high_volatility_above_fifteen_percent() -> None:
    analysis = analyze_prices(90.0, 110.0, 100.0)

    assert analysis.volatility is PriceVolatility.HIGH


def test_all_zero_prices_have_low_volatility() -> None:
    analysis = analyze_prices(0.0, 0.0, 0.0)

    assert analysis.volatility is PriceVolatility.LOW


def test_current_price_inside_lowest_five_percent_band() -> None:
    analysis = analyze_prices(120.0, 80.0, 82.0)

    assert analysis.near_lowest is True
    assert analysis.near_highest is False


def test_current_price_outside_lowest_five_percent_band() -> None:
    analysis = analyze_prices(120.0, 80.0, 83.0)

    assert analysis.near_lowest is False
    assert analysis.near_highest is False


def test_current_price_inside_highest_five_percent_band() -> None:
    analysis = analyze_prices(80.0, 120.0, 118.0)

    assert analysis.near_lowest is False
    assert analysis.near_highest is True


def test_current_price_outside_highest_five_percent_band() -> None:
    analysis = analyze_prices(80.0, 120.0, 117.0)

    assert analysis.near_lowest is False
    assert analysis.near_highest is False


def test_custom_policy_changes_direction_threshold() -> None:
    engine = TrendAnalysisEngine(
        TrendAnalysisPolicy(
            stable_change_rate_threshold=Decimal("5.0"),
        )
    )

    analysis = engine.analyze(
        [
            record(
                record_id=1,
                price=100.0,
                observed_at="2026-07-27T10:00:00+00:00",
            ),
            record(
                record_id=2,
                price=104.0,
                observed_at="2026-07-27T11:00:00+00:00",
            ),
        ]
    )

    assert analysis.direction is TrendDirection.STABLE


def test_custom_policy_changes_proximity_band() -> None:
    engine = TrendAnalysisEngine(
        TrendAnalysisPolicy(
            proximity_band_rate=Decimal("10.0"),
        )
    )

    analysis = engine.analyze(
        [
            record(
                record_id=1,
                price=80.0,
                observed_at="2026-07-27T10:00:00+00:00",
            ),
            record(
                record_id=2,
                price=120.0,
                observed_at="2026-07-27T11:00:00+00:00",
            ),
            record(
                record_id=3,
                price=84.0,
                observed_at="2026-07-27T12:00:00+00:00",
            ),
        ]
    )

    assert analysis.near_lowest is True


def test_policy_rejects_inverted_volatility_thresholds() -> None:
    with pytest.raises(ValueError):
        TrendAnalysisPolicy(
            low_volatility_max_rate=Decimal("20.0"),
            medium_volatility_max_rate=Decimal("10.0"),
        )


def test_policy_rejects_non_decimal_value() -> None:
    with pytest.raises(TypeError):
        TrendAnalysisPolicy(
            proximity_band_rate=5.0,
        )


def test_policy_rejects_proximity_band_above_fifty_percent() -> None:
    with pytest.raises(ValueError):
        TrendAnalysisPolicy(
            proximity_band_rate=Decimal("50.1"),
        )
