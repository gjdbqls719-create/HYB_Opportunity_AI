from __future__ import annotations

from engine.explainable_score import (
    build_explainable_score,
)
from engine.market_adjustment import (
    MarketAdjustmentResult,
)


def create_market_adjustment():
    return MarketAdjustmentResult(
        adjustment=13.0,
        insights=(
            "시장 상태가 양호합니다.",
        ),
        reasons=(
            "시장 건강도 보정 +3점",
            "구매 가능한 재고 보정 +5점",
            "낮은 판매자 경쟁 보정 +5점",
        ),
    )


def test_market_adjustment_is_added_to_score():

    result = build_explainable_score(
        base_score=50,
        roi=40,
        net_profit=100,
        competitor_count=3,
        risk_level="low",
        confidence=None,
        price_trend=None,
        market_adjustment=(
            create_market_adjustment()
        ),
    )

    contribution = next(
        item
        for item in result.contributions
        if item.key == "market_adjustment"
    )

    assert contribution.adjustment == 13.0
    assert (
        "시장 건강도 보정 +3점"
        in contribution.reasons
    )


def test_market_adjustment_none_keeps_compatibility():

    result = build_explainable_score(
        base_score=50,
        roi=40,
        net_profit=100,
        competitor_count=3,
        risk_level="low",
        confidence=None,
        price_trend=None,
    )

    contribution = next(
        item
        for item in result.contributions
        if item.key == "market_adjustment"
    )

    assert contribution.adjustment == 0.0


def test_final_score_includes_market_adjustment():

    without_adjustment = (
        build_explainable_score(
            base_score=50,
            roi=40,
            net_profit=100,
            competitor_count=3,
            risk_level="low",
            confidence=None,
            price_trend=None,
        )
    )

    with_adjustment = (
        build_explainable_score(
            base_score=50,
            roi=40,
            net_profit=100,
            competitor_count=3,
            risk_level="low",
            confidence=None,
            price_trend=None,
            market_adjustment=(
                create_market_adjustment()
            ),
        )
    )

    assert (
        with_adjustment.final_score
        >
        without_adjustment.final_score
    )