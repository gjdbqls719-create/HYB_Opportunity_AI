from __future__ import annotations

from datetime import datetime, timezone

from engine.inventory_analysis import (
    InventoryAnalysisResult,
)
from engine.market_intelligence import (
    build_market_intelligence,
)
from engine.seller_analysis import (
    SellerAnalysisResult,
)


def test_builds_market_intelligence():

    inventory = InventoryAnalysisResult(
        availability="재고 있음",
        stock_level="충분",
        risk_level="낮음",
        can_purchase=True,
        insights=(
            "재고가 충분합니다.",
        ),
        risks=(),
        summary="재고 상태 양호",
    )

    seller = SellerAnalysisResult(
        competition_level="낮음",
        seller_quality="양호",
        risk_level="낮음",
        insights=(
            "경쟁 판매자가 적습니다.",
        ),
        risks=(),
        summary="판매자 상태 양호",
    )

    result = build_market_intelligence(
        inventory_analysis=inventory,
        seller_analysis=seller,
    )

    assert result.market_health == "양호"
    assert len(result.insights) == 2
    assert result.summary == (
        "현재 시장 상태는 양호입니다."
    )


def test_market_intelligence_detects_risk():

    inventory = InventoryAnalysisResult(
        availability="품절",
        stock_level="없음",
        risk_level="높음",
        can_purchase=False,
        insights=(),
        risks=(
            "재고가 없습니다.",
            "구매할 수 없습니다.",
        ),
        summary="위험",
    )

    result = build_market_intelligence(
        inventory_analysis=inventory,
    )

    assert result.market_health == "보통"
    assert len(result.risks) == 2


def test_empty_market_intelligence():

    result = build_market_intelligence()

    assert result.market_health == "양호"
    assert result.insights == ()
    assert result.risks == ()