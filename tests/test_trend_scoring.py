from __future__ import annotations

from engine.price_trend import PriceTrend
from engine.trend_scoring import (
    calculate_trend_score,
)


def make_trend(
    *,
    sample_size: int = 3,
    lowest_price: float = 80.0,
    highest_price: float = 120.0,
    current_price: float = 80.0,
    average_price: float = 100.0,
    trend_direction: str = "하락",
    price_position: str = "기간 최저가",
    has_sufficient_history: bool = True,
) -> PriceTrend:
    return PriceTrend(
        marketplace="ebay",
        item_id="ITEM-001",
        title="Test Product",
        currency="USD",
        sample_size=sample_size,
        period_days=7.0,
        oldest_price=120.0,
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        absolute_change=current_price - 120.0,
        percentage_change=-33.33,
        trend_direction=trend_direction,
        price_position=price_position,
        recommendation="매입 검토",
        reason="테스트 가격 추세",
        has_sufficient_history=has_sufficient_history,
    )


def test_lowest_and_falling_price_gets_bonus() -> None:
    trend = make_trend(
        price_position="기간 최저가",
        trend_direction="하락",
    )

    result = calculate_trend_score(trend)

    assert result.adjustment == 15.0
    assert len(result.reasons) == 2


def test_cheaper_than_average_gets_bonus() -> None:
    trend = make_trend(
        current_price=90.0,
        price_position="평균보다 저렴",
        trend_direction="보합",
    )

    result = calculate_trend_score(trend)

    assert result.adjustment == 8.0


def test_highest_and_rising_price_gets_penalty() -> None:
    trend = make_trend(
        current_price=120.0,
        price_position="기간 최고가",
        trend_direction="상승",
    )

    result = calculate_trend_score(trend)

    assert result.adjustment == -18.0
    assert len(result.reasons) == 2


def test_unchanged_price_has_no_adjustment() -> None:
    trend = make_trend(
        lowest_price=100.0,
        highest_price=100.0,
        current_price=100.0,
        average_price=100.0,
        price_position="기간 최저가",
        trend_direction="보합",
    )

    result = calculate_trend_score(trend)

    assert result.adjustment == 0.0
    assert len(result.reasons) == 1


def test_insufficient_history_has_no_adjustment() -> None:
    trend = make_trend(
        sample_size=1,
        has_sufficient_history=False,
        trend_direction="데이터 부족",
    )

    result = calculate_trend_score(trend)

    assert result.adjustment == 0.0


def test_missing_trend_has_no_adjustment() -> None:
    result = calculate_trend_score(None)

    assert result.adjustment == 0.0
    assert len(result.reasons) == 1