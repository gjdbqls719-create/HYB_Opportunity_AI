from __future__ import annotations

from dataclasses import dataclass

from engine.market_intelligence import (
    MarketIntelligenceResult,
)


@dataclass(frozen=True, slots=True)
class MarketAdjustmentResult:
    """
    Market Intelligence 결과를
    Opportunity Score 보정값으로 변환한 결과.
    """

    adjustment: float

    insights: tuple[str, ...]

    reasons: tuple[str, ...]


def calculate_market_adjustment(
    intelligence: MarketIntelligenceResult | None,
) -> MarketAdjustmentResult:
    """
    시장 분석 결과를 점수 보정값으로 변환한다.

    현재는 독립 계층이며,
    Opportunity Score에는 아직 직접 연결하지 않는다.
    """

    if intelligence is None:
        return MarketAdjustmentResult(
            adjustment=0.0,
            insights=(),
            reasons=(
                "시장 분석 데이터가 없어 "
                "점수 보정을 적용하지 않았습니다.",
            ),
        )

    adjustment = 0.0

    insights: list[str] = []
    reasons: list[str] = []

    if intelligence.market_health == "양호":
        adjustment += 3.0
        insights.append(
            "시장 상태가 양호합니다."
        )
        reasons.append(
            "시장 건강도 보정 +3점"
        )

    elif intelligence.market_health == "주의":
        adjustment -= 5.0
        reasons.append(
            "시장 위험 상태 보정 -5점"
        )

    if intelligence.inventory_analysis:
        inventory = (
            intelligence.inventory_analysis
        )

        if inventory.can_purchase:
            adjustment += 5.0
            reasons.append(
                "구매 가능한 재고 보정 +5점"
            )

        else:
            adjustment -= 15.0
            reasons.append(
                "구매 불가능 재고 보정 -15점"
            )

    if intelligence.seller_analysis:
        seller = (
            intelligence.seller_analysis
        )

        if seller.competition_level == "낮음":
            adjustment += 5.0
            reasons.append(
                "낮은 판매자 경쟁 보정 +5점"
            )

        elif seller.competition_level == "높음":
            adjustment -= 5.0
            reasons.append(
                "높은 판매자 경쟁 보정 -5점"
            )

    return MarketAdjustmentResult(
        adjustment=round(
            adjustment,
            2,
        ),
        insights=tuple(insights),
        reasons=tuple(reasons),
    )