from __future__ import annotations

import pytest

from engine.confidence import (
    calculate_price_confidence,
)
from engine.price_trend import PriceTrend
from engine.recommendation import (
    generate_recommendation,
)


def make_trend(
    *,
    current_price: float = 80.0,
    lowest_price: float = 80.0,
    highest_price: float = 120.0,
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
        sample_size=3,
        period_days=7.0,
        oldest_price=120.0,
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        absolute_change=(
            current_price - 120.0
        ),
        percentage_change=-33.33,
        trend_direction=trend_direction,
        price_position=price_position,
        recommendation="매입 검토",
        reason="테스트 가격 추세",
        has_sufficient_history=(
            has_sufficient_history
        ),
    )


def test_generates_strong_buy_recommendation() -> None:
    confidence = calculate_price_confidence(6)

    result = generate_recommendation(
        final_opportunity_score=65.0,
        roi=55.0,
        net_profit=100.0,
        competitor_count=4,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    assert result.score >= 80
    assert result.stars == 5
    assert result.grade == "STRONG_BUY"
    assert result.action == "강력 매입 추천"


def test_loss_product_is_not_recommended() -> None:
    confidence = calculate_price_confidence(4)

    result = generate_recommendation(
        final_opportunity_score=30.0,
        roi=-15.0,
        net_profit=-10.0,
        competitor_count=20,
        risk_level="medium",
        confidence=confidence,
        price_trend=None,
    )

    assert result.score < 25
    assert result.grade == "AVOID"
    assert result.action == "매입 비추천"
    assert result.warnings


def test_low_confidence_reduces_score() -> None:
    high_confidence = calculate_price_confidence(6)

    low_confidence = calculate_price_confidence(
        1,
        used_fallback_price=True,
    )

    high_result = generate_recommendation(
        final_opportunity_score=50.0,
        roi=25.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=high_confidence,
        price_trend=None,
    )

    low_result = generate_recommendation(
        final_opportunity_score=50.0,
        roi=25.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=low_confidence,
        price_trend=None,
    )

    assert high_result.score > low_result.score


def test_highest_and_rising_price_reduces_score() -> None:
    confidence = calculate_price_confidence(4)

    favorable_result = generate_recommendation(
        final_opportunity_score=50.0,
        roi=25.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=confidence,
        price_trend=make_trend(),
    )

    unfavorable_result = generate_recommendation(
        final_opportunity_score=50.0,
        roi=25.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=confidence,
        price_trend=make_trend(
            current_price=120.0,
            price_position="기간 최고가",
            trend_direction="상승",
        ),
    )

    assert (
        favorable_result.score
        > unfavorable_result.score
    )


def test_score_is_limited_to_100() -> None:
    confidence = calculate_price_confidence(10)

    result = generate_recommendation(
        final_opportunity_score=100.0,
        roi=100.0,
        net_profit=500.0,
        competitor_count=0,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    assert result.score == 100


def test_success_probability_is_limited() -> None:
    confidence = calculate_price_confidence(10)

    result = generate_recommendation(
        final_opportunity_score=100.0,
        roi=100.0,
        net_profit=500.0,
        competitor_count=0,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    assert 1 <= result.success_probability <= 95


def test_rejects_invalid_risk_level() -> None:
    with pytest.raises(ValueError):
        generate_recommendation(
            final_opportunity_score=50.0,
            roi=20.0,
            net_profit=10.0,
            competitor_count=10,
            risk_level="unknown",
            confidence=None,
            price_trend=None,
        )