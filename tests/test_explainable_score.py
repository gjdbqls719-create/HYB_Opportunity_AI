from __future__ import annotations

from engine.confidence import (
    calculate_price_confidence,
)
from engine.explainable_score import (
    build_explainable_score,
)
from engine.price_trend import PriceTrend


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


def test_builds_positive_score_contributions() -> None:
    confidence = calculate_price_confidence(6)

    result = build_explainable_score(
        base_score=65.0,
        roi=55.0,
        net_profit=100.0,
        competitor_count=4,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    contribution_map = {
        contribution.key: contribution.adjustment
        for contribution in result.contributions
    }

    assert contribution_map["base_score"] == 65.0
    assert contribution_map["profit"] == 18.0
    assert contribution_map["confidence"] == 10.0
    assert contribution_map["trend"] == 11.0
    assert contribution_map["competition"] == 8.0
    assert contribution_map["risk"] == 5.0

    assert result.raw_total == 117.0
    assert result.final_score == 100


def test_builds_negative_score_contributions() -> None:
    confidence = calculate_price_confidence(
        1,
        used_fallback_price=True,
    )

    result = build_explainable_score(
        base_score=30.0,
        roi=-15.0,
        net_profit=-10.0,
        competitor_count=80,
        risk_level="high",
        confidence=confidence,
        price_trend=make_trend(
            current_price=120.0,
            price_position="기간 최고가",
            trend_direction="상승",
        ),
    )

    contribution_map = {
        contribution.key: contribution.adjustment
        for contribution in result.contributions
    }

    assert contribution_map["base_score"] == 30.0
    assert contribution_map["profit"] == -25.0
    assert contribution_map["confidence"] == -10.0
    assert contribution_map["trend"] == -13.0
    assert contribution_map["competition"] == -10.0
    assert contribution_map["risk"] == -10.0

    assert result.raw_total == -38.0
    assert result.final_score == 0


def test_missing_market_data_is_explained() -> None:
    result = build_explainable_score(
        base_score=50.0,
        roi=20.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=None,
        price_trend=None,
    )

    contribution_map = {
        contribution.key: contribution
        for contribution in result.contributions
    }

    assert contribution_map["confidence"].adjustment == -5.0
    assert contribution_map["trend"].adjustment == 0.0

    assert (
        "가격 신뢰도 정보가 없습니다."
        in contribution_map["confidence"].description
    )

    assert (
        "가격 추세 데이터가 없습니다."
        in contribution_map["trend"].description
    )


def test_final_score_matches_expected_recommendation_score() -> None:
    confidence = calculate_price_confidence(6)

    result = build_explainable_score(
        base_score=50.0,
        roi=25.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=confidence,
        price_trend=None,
    )

    assert result.raw_total == 66.0
    assert result.final_score == 66


def test_contribution_order_is_stable() -> None:
    result = build_explainable_score(
        base_score=50.0,
        roi=20.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=None,
        price_trend=None,
    )

    assert tuple(
        contribution.key
        for contribution in result.contributions
    ) == (
        "base_score",
        "profit",
        "confidence",
        "trend",
        "competition",
        "risk",
    )