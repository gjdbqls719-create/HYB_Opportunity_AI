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
    market_health: str = "양호",
    can_purchase: bool = True,
    competition_level: str = "낮음",
) -> MarketIntelligenceResult:
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


def test_applies_positive_market_adjustment() -> None:
    result = calculate_market_adjustment(
        create_intelligence()
    )

    assert result.adjustment == 13.0


def test_applies_negative_inventory_adjustment() -> None:
    result = calculate_market_adjustment(
        create_intelligence(
            can_purchase=False,
        )
    )

    assert result.adjustment == -7.0


def test_applies_competition_penalty() -> None:
    result = calculate_market_adjustment(
        create_intelligence(
            competition_level="높음",
        )
    )

    assert result.adjustment == 3.0


def test_handles_missing_intelligence() -> None:
    result = calculate_market_adjustment(
        None
    )

    assert result.adjustment == 0.0
    assert len(result.reasons) == 1


def test_builds_positive_user_explanations() -> None:
    result = calculate_market_adjustment(
        create_intelligence()
    )

    assert result.explanations == (
        "현재 시장 상태가 양호하여 "
        "Opportunity Score를 3점 높였습니다.",
        "현재 구매 가능한 재고가 있어 "
        "상품 확보 가능성을 긍정적으로 평가했습니다.",
        "경쟁 판매자가 적어 "
        "시장 진입 환경을 유리하게 평가했습니다.",
    )


def test_explains_unavailable_inventory() -> None:
    result = calculate_market_adjustment(
        create_intelligence(
            can_purchase=False,
        )
    )

    assert (
        "현재 구매 가능한 재고가 없어 "
        "Opportunity Score를 크게 낮췄습니다."
        in result.explanations
    )


def test_explains_high_seller_competition() -> None:
    result = calculate_market_adjustment(
        create_intelligence(
            competition_level="높음",
        )
    )

    assert (
        "경쟁 판매자가 많아 "
        "판매 속도와 수익성이 낮아질 위험을 반영했습니다."
        in result.explanations
    )


def test_explains_missing_market_intelligence() -> None:
    result = calculate_market_adjustment(
        None
    )

    assert result.explanations == (
        "시장 분석 데이터가 부족하여 "
        "Opportunity Score를 조정하지 않았습니다.",
    )