from __future__ import annotations

from dataclasses import dataclass

from engine.confidence import ConfidenceResult
from engine.market_adjustment import (
    MarketAdjustmentResult,
)
from engine.price_trend import PriceTrend
from engine.recommendation import RecommendationResult


@dataclass(slots=True, frozen=True)
class DecisionReport:
    """
    Recommendation 결과를 사람이 읽기 쉬운
    AI 분석 리포트 형태로 정리한다.

    Market Adjustment의 설명도 함께 보존하여
    AI Partner, Dashboard, CLI, API가 동일한
    시장 판단 근거를 재사용할 수 있도록 한다.
    """

    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]

    market_summary: str
    buy_timing: str
    ai_comment: str

    market_explanations: tuple[str, ...] = ()


def build_decision_report(
    *,
    recommendation: RecommendationResult,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
    market_adjustment: (
        MarketAdjustmentResult | None
    ) = None,
) -> DecisionReport:
    """
    Recommendation 결과를 기반으로
    AI 분석 리포트를 생성한다.

    market_adjustment가 제공되면 이미 계산된
    인간 친화적 시장 설명을 그대로 보존한다.

    market_adjustment를 전달하지 않아도
    기존 호출 방식과 동일하게 동작한다.
    """

    strengths: list[str] = list(
        recommendation.reasons
    )

    weaknesses: list[str] = list(
        recommendation.warnings
    )

    decision_label = getattr(
        recommendation,
        "decision_label",
        recommendation.grade,
    )

    market_summary = _build_market_summary(
        recommendation=recommendation,
        decision_label=decision_label,
        price_trend=price_trend,
    )

    buy_timing = _build_buy_timing(
        recommendation=recommendation,
        price_trend=price_trend,
        confidence=confidence,
    )

    ai_comment = _build_ai_comment(
        recommendation=recommendation,
        confidence=confidence,
        price_trend=price_trend,
    )

    market_explanations = (
        _extract_market_explanations(
            market_adjustment=market_adjustment,
        )
    )

    return DecisionReport(
        strengths=tuple(strengths),
        weaknesses=tuple(weaknesses),
        market_summary=market_summary,
        buy_timing=buy_timing,
        ai_comment=ai_comment,
        market_explanations=market_explanations,
    )


def _extract_market_explanations(
    *,
    market_adjustment: (
        MarketAdjustmentResult | None
    ),
) -> tuple[str, ...]:
    """
    Market Adjustment가 생성한 설명을
    중복과 빈 문자열 없이 안전하게 정리한다.

    설명의 긍정·부정을 문자열로 추측해 분류하지 않고,
    계산 계층에서 생성한 원본 의미를 그대로 보존한다.
    """
    if market_adjustment is None:
        return ()

    explanations = getattr(
        market_adjustment,
        "explanations",
        (),
    )

    if explanations is None:
        return ()

    if isinstance(explanations, str):
        cleaned_explanation = explanations.strip()

        if not cleaned_explanation:
            return ()

        return (cleaned_explanation,)

    try:
        items = tuple(explanations)
    except TypeError:
        cleaned_explanation = str(
            explanations
        ).strip()

        if not cleaned_explanation:
            return ()

        return (cleaned_explanation,)

    cleaned_items: list[str] = []

    for item in items:
        cleaned_item = str(item).strip()

        if (
            cleaned_item
            and cleaned_item not in cleaned_items
        ):
            cleaned_items.append(cleaned_item)

    return tuple(cleaned_items)


def _build_market_summary(
    *,
    recommendation: RecommendationResult,
    decision_label: str,
    price_trend: PriceTrend | None,
) -> str:
    if price_trend is None:
        return (
            f"[{decision_label}] "
            "시장 가격 이력이 충분하지 않아 "
            "현재 시장 흐름을 명확하게 판단하기 어렵습니다."
        )

    if not price_trend.has_sufficient_history:
        return (
            f"[{decision_label}] "
            "가격 이력이 부족하여 "
            "시장 분석의 정확도가 제한됩니다."
        )

    if (
        price_trend.lowest_price
        == price_trend.highest_price
    ):
        return (
            f"[{decision_label}] "
            "가격이 안정적으로 유지되고 있는 "
            "시장입니다."
        )

    if (
        price_trend.price_position
        == "기간 최저가"
    ):
        return (
            f"[{decision_label}] "
            "현재 가격은 최근 저장 기간 중 "
            "가장 낮은 수준입니다."
        )

    if (
        price_trend.price_position
        == "기간 최고가"
    ):
        return (
            f"[{decision_label}] "
            "현재 가격은 최근 저장 기간 중 "
            "가장 높은 수준입니다."
        )

    return (
        f"[{decision_label}] "
        "현재 가격은 평균적인 시장 가격 "
        "범위에 위치하고 있습니다."
    )


def _build_buy_timing(
    *,
    recommendation: RecommendationResult,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> str:

    if recommendation.grade == "STRONG_BUY":
        return "지금 적극적으로 매입을 검토할 시점입니다."

    if recommendation.grade == "BUY":
        return "현재 매입을 고려할 만한 시점입니다."

    if recommendation.grade == "WATCH":
        return "시장 가격을 조금 더 관찰하는 것이 좋습니다."

    if recommendation.grade == "CAUTION":
        return "당장 매입하기보다는 추가 확인을 권장합니다."

    return "현재는 매입을 권장하지 않습니다."


def _build_ai_comment(
    *,
    recommendation: RecommendationResult,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> str:

    if recommendation.grade == "STRONG_BUY":
        return (
            "현재 조건에서는 매우 우수한 "
            "매입 기회로 판단됩니다."
        )

    if recommendation.grade == "BUY":
        return (
            "전반적으로 안정적인 투자 "
            "후보로 판단됩니다."
        )

    if recommendation.grade == "WATCH":
        return (
            "추가 시장 데이터를 확인하면 "
            "더 정확한 판단이 가능합니다."
        )

    if recommendation.grade == "CAUTION":
        return (
            "일부 위험 요소가 존재하므로 "
            "신중한 검토가 필요합니다."
        )

    return (
        "현재 조건에서는 다른 상품을 "
        "우선 검토하는 것이 좋습니다."
    )