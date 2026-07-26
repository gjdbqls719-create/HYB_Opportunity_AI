from __future__ import annotations

from engine.inventory_analysis import (
    InventoryAnalysisResult,
)
from engine.market_adjustment import (
    calculate_market_adjustment,
)
from engine.market_intelligence import (
    MarketIntelligenceResult,
)
from engine.seller_analysis import (
    SellerAnalysisResult,
)


def create_intelligence(
    *,
    market_health="양호",
    can_purchase=True,
    competition_level="낮음",
):
    return MarketIntelligenceResult(
        price_trend=None,
        inventory_analysis=InventoryAnalysisResult(
            availability="재고 있음",
            stock_level="충분",
            risk_level="낮음",
            can_purchase=can_purchase,
            insights=(),
            risks=(),
            summary="",
        ),
        seller_analysis=SellerAnalysisResult(
            competition_level=competition_level,
            seller_quality="양호",
            risk_level="낮음",
            insights=(),
            risks=(),
            summary="",
        ),
        market_health=market_health,
        insights=(),
        risks=(),
        summary="",
    )


def test_applies_positive_market_adjustment():
    result = calculate_market_adjustment(
        create_intelligence()
    )

    assert result.adjustment == 13.0


def test_applies_negative_inventory_adjustment():
    result = calculate_market_adjustment(
        create_intelligence(
            can_purchase=False,
        )
    )

    assert result.adjustment == -7.0


def test_applies_competition_penalty():
    result = calculate_market_adjustment(
        create_intelligence(
            competition_level="높음",
        )
    )

    assert result.adjustment == 3.0


def test_handles_missing_intelligence():

    result = calculate_market_adjustment(
        None
    )

    assert result.adjustment == 0.0
    assert len(result.reasons) == 1