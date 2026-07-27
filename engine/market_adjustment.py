from __future__ import annotations

from dataclasses import dataclass

from engine.market_intelligence import (
    MarketIntelligenceResult,
)


@dataclass(frozen=True, slots=True)
class MarketAdjustmentResult:
    """
    Market Intelligence 결과를 Opportunity Score
    보정값과 설명 가능한 근거로 변환한 결과.

    reasons:
        점수 계산과 테스트에서 사용하는 내부 계산 근거.

    explanations:
        CLI, Dashboard, AI Partner 등에서 사용자에게
        보여주기 위한 자연어 설명.
    """

    adjustment: float

    insights: tuple[str, ...]

    reasons: tuple[str, ...]

    explanations: tuple[str, ...] = ()


def calculate_market_adjustment(
    intelligence: MarketIntelligenceResult | None,
) -> MarketAdjustmentResult:
    """
    시장 분석 결과를 점수 보정값으로 변환한다.

    기존 adjustment 계산식과 reasons 계약은 유지하면서,
    사용자에게 보여줄 수 있는 explanations를 함께 생성한다.
    """

    if intelligence is None:
        return MarketAdjustmentResult(
            adjustment=0.0,
            insights=(),
            reasons=(
                "시장 분석 데이터가 없어 "
                "점수 보정을 적용하지 않았습니다.",
            ),
            explanations=(
                "시장 분석 데이터가 부족하여 "
                "Opportunity Score를 조정하지 않았습니다.",
            ),
        )

    adjustment = 0.0

    insights: list[str] = []
    reasons: list[str] = []
    explanations: list[str] = []

    if intelligence.market_health == "양호":
        adjustment += 3.0

        insights.append(
            "시장 상태가 양호합니다."
        )

        reasons.append(
            "시장 건강도 보정 +3점"
        )

        explanations.append(
            "현재 시장 상태가 양호하여 "
            "Opportunity Score를 3점 높였습니다."
        )

    elif intelligence.market_health == "주의":
        adjustment -= 5.0

        reasons.append(
            "시장 위험 상태 보정 -5점"
        )

        explanations.append(
            "시장 위험 신호가 확인되어 "
            "Opportunity Score를 5점 낮췄습니다."
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

            explanations.append(
                "현재 구매 가능한 재고가 있어 "
                "상품 확보 가능성을 긍정적으로 평가했습니다."
            )

        else:
            adjustment -= 15.0

            reasons.append(
                "구매 불가능 재고 보정 -15점"
            )

            explanations.append(
                "현재 구매 가능한 재고가 없어 "
                "Opportunity Score를 크게 낮췄습니다."
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

            explanations.append(
                "경쟁 판매자가 적어 "
                "시장 진입 환경을 유리하게 평가했습니다."
            )

        elif seller.competition_level == "높음":
            adjustment -= 5.0

            reasons.append(
                "높은 판매자 경쟁 보정 -5점"
            )

            explanations.append(
                "경쟁 판매자가 많아 "
                "판매 속도와 수익성이 낮아질 위험을 반영했습니다."
            )

    return MarketAdjustmentResult(
        adjustment=round(
            adjustment,
            2,
        ),
        insights=tuple(insights),
        reasons=tuple(reasons),
        explanations=tuple(explanations),
    )