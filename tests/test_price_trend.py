from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.price_trend import (
    analyze_price_trend,
)
from storage.price_history import (
    PriceHistoryRecord,
)


def make_record(
    *,
    record_id: int,
    price: float,
    observed_at: datetime,
    marketplace: str = "ebay",
    item_id: str = "ITEM-001",
    currency: str = "USD",
) -> PriceHistoryRecord:
    return PriceHistoryRecord(
        id=record_id,
        marketplace=marketplace,
        item_id=item_id,
        title="Test Product",
        price=price,
        currency=currency,
        condition="New",
        url="https://example.com/item",
        observed_at=observed_at.isoformat(),
    )


def test_detects_falling_price_trend() -> None:
    records = [
        make_record(
            record_id=1,
            price=120.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=2,
            price=110.0,
            observed_at=datetime(
                2026,
                7,
                5,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=3,
            price=100.0,
            observed_at=datetime(
                2026,
                7,
                10,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    trend = analyze_price_trend(records)

    assert trend.sample_size == 3
    assert trend.oldest_price == 120.0
    assert trend.current_price == 100.0
    assert trend.absolute_change == -20.0
    assert trend.percentage_change == -16.67
    assert trend.trend_direction == "하락"
    assert trend.price_position == "기간 최저가"
    assert trend.recommendation == "매입 검토"


def test_detects_rising_price_trend() -> None:
    records = [
        make_record(
            record_id=1,
            price=100.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=2,
            price=120.0,
            observed_at=datetime(
                2026,
                7,
                10,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    trend = analyze_price_trend(records)

    assert trend.percentage_change == 20.0
    assert trend.trend_direction == "상승"
    assert trend.price_position == "기간 최고가"
    assert trend.recommendation == "주의"


def test_detects_flat_price_trend() -> None:
    records = [
        make_record(
            record_id=1,
            price=100.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=2,
            price=100.5,
            observed_at=datetime(
                2026,
                7,
                2,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    trend = analyze_price_trend(records)

    assert trend.percentage_change == 0.5
    assert trend.trend_direction == "보합"
    assert trend.recommendation == "관찰"


def test_single_record_requires_more_data() -> None:
    records = [
        make_record(
            record_id=1,
            price=100.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        )
    ]

    trend = analyze_price_trend(records)

    assert trend.sample_size == 1
    assert trend.has_sufficient_history is False
    assert trend.trend_direction == "데이터 부족"
    assert trend.recommendation == "데이터 수집 필요"


def test_records_are_sorted_by_observed_time() -> None:
    newest = make_record(
        record_id=2,
        price=80.0,
        observed_at=datetime(
            2026,
            7,
            10,
            tzinfo=timezone.utc,
        ),
    )

    oldest = make_record(
        record_id=1,
        price=100.0,
        observed_at=datetime(
            2026,
            7,
            1,
            tzinfo=timezone.utc,
        ),
    )

    trend = analyze_price_trend(
        [newest, oldest]
    )

    assert trend.oldest_price == 100.0
    assert trend.current_price == 80.0
    assert trend.period_days == 9.0


def test_zero_oldest_price_returns_no_percentage() -> None:
    records = [
        make_record(
            record_id=1,
            price=0.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=2,
            price=10.0,
            observed_at=datetime(
                2026,
                7,
                2,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    trend = analyze_price_trend(records)

    assert trend.absolute_change == 10.0
    assert trend.percentage_change is None
    assert trend.trend_direction == "판단 불가"


def test_rejects_different_products() -> None:
    records = [
        make_record(
            record_id=1,
            item_id="ITEM-001",
            price=100.0,
            observed_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        make_record(
            record_id=2,
            item_id="ITEM-002",
            price=90.0,
            observed_at=datetime(
                2026,
                7,
                2,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    with pytest.raises(ValueError):
        analyze_price_trend(records)


def test_rejects_empty_records() -> None:
    with pytest.raises(ValueError):
        analyze_price_trend([])