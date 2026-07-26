from __future__ import annotations

from dataclasses import dataclass

from engine.inventory_analysis import (
    InventoryAnalysisResult,
)
from engine.seller_analysis import (
    SellerAnalysisResult,
)
from engine.price_trend import PriceTrend


@dataclass(frozen=True, slots=True)
class MarketIntelligenceResult:
    """
    가격, 재고, 판매자 분석 결과를
    하나의 시장 판단 결과로 통합한다.
    """

    price_trend: PriceTrend | None

    inventory_analysis: (
        InventoryAnalysisResult | None
    )

    seller_analysis: (
        SellerAnalysisResult | None
    )

    market_health: str

    insights: tuple[str, ...]

    risks: tuple[str, ...]

    summary: str


def build_market_intelligence(
    *,
    price_trend: PriceTrend | None = None,
    inventory_analysis: (
        InventoryAnalysisResult | None
    ) = None,
    seller_analysis: (
        SellerAnalysisResult | None
    ) = None,
) -> MarketIntelligenceResult:
    """
    개별 Intelligence 결과를 하나의
    Market Intelligence 결과로 통합한다.
    """

    insights: list[str] = []
    risks: list[str] = []

    if inventory_analysis is not None:
        insights.extend(
            inventory_analysis.insights
        )
        risks.extend(
            inventory_analysis.risks
        )

    if seller_analysis is not None:
        insights.extend(
            seller_analysis.insights
        )
        risks.extend(
            seller_analysis.risks
        )

    if price_trend is not None:
        if price_trend.price_position == "기간 최저가":
            insights.append(
                "현재 가격이 최근 기록 중 최저 수준입니다."
            )

        if price_trend.trend_direction == "상승":
            risks.append(
                "가격이 상승 추세입니다."
            )

    market_health = _determine_market_health(
        risks=risks,
    )

    summary = (
        f"현재 시장 상태는 {market_health}입니다."
    )

    return MarketIntelligenceResult(
        price_trend=price_trend,
        inventory_analysis=inventory_analysis,
        seller_analysis=seller_analysis,
        market_health=market_health,
        insights=tuple(insights),
        risks=tuple(risks),
        summary=summary,
    )


def _determine_market_health(
    *,
    risks: list[str],
) -> str:
    if len(risks) >= 3:
        return "주의"

    if len(risks) >= 1:
        return "보통"

    return "양호"