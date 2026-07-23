from __future__ import annotations

from dataclasses import dataclass

from engine.ai_memory import AIMemoryInsight
from engine.decision_report import DecisionReport
from engine.recommendation import RecommendationResult


@dataclass(slots=True, frozen=True)
class AIPartnerReport:
    """
    HYB AI Partner가 사용자에게 전달하는
    최종 의사결정 보고서.

    직접 점수를 계산하지 않고,
    Recommendation, DecisionReport, AI Memory의 결과를 종합해
    사람이 이해하기 쉬운 형태로 해석한다.
    """

    title: str
    summary: str
    recommendation: str
    next_action: str
    memory_summary: str = ""


def build_ai_partner_report(
    *,
    recommendation: RecommendationResult,
    decision_report: DecisionReport,
    memory_insight: AIMemoryInsight | None = None,
) -> AIPartnerReport:
    """
    추천 결과와 의사결정 보고서, AI Memory 결과를 종합해
    HYB AI Partner의 최종 의견을 생성한다.

    memory_insight를 전달하지 않으면
    기존 AI Partner와 동일하게 동작한다.
    """
    title = _build_title(
        recommendation=recommendation,
    )

    summary = _build_summary(
        recommendation=recommendation,
        decision_report=decision_report,
    )

    memory_summary = _build_memory_summary(
        memory_insight=memory_insight,
    )

    recommendation_text = _build_recommendation_text(
        recommendation=recommendation,
        decision_report=decision_report,
    )

    next_action = _build_next_action(
        recommendation=recommendation,
        decision_report=decision_report,
    )

    return AIPartnerReport(
        title=title,
        summary=summary,
        recommendation=recommendation_text,
        next_action=next_action,
        memory_summary=memory_summary,
    )


def _build_title(
    *,
    recommendation: RecommendationResult,
) -> str:
    """
    추천 등급을 포함한 보고서 제목을 만든다.
    """
    grade = str(
        getattr(
            recommendation,
            "grade",
            "",
        )
    ).strip()

    if grade:
        return (
            "HYB AI Partner Report "
            f"- {grade}"
        )

    return "HYB AI Partner Report"


def _build_summary(
    *,
    recommendation: RecommendationResult,
    decision_report: DecisionReport,
) -> str:
    """
    시장 상황과 추천 결과를 결합해
    한 문단의 핵심 요약을 만든다.
    """
    parts: list[str] = []

    recommendation_summary = str(
        getattr(
            recommendation,
            "summary",
            "",
        )
    ).strip()

    market_summary = str(
        getattr(
            decision_report,
            "market_summary",
            "",
        )
    ).strip()

    if recommendation_summary:
        parts.append(recommendation_summary)

    if (
        market_summary
        and market_summary
        not in recommendation_summary
    ):
        parts.append(market_summary)

    if not parts:
        return (
            "현재 분석 결과만으로는 "
            "명확한 종합 요약을 생성하기 어렵습니다."
        )

    return " ".join(parts)


def _build_memory_summary(
    *,
    memory_insight: AIMemoryInsight | None,
) -> str:
    """
    AI Memory 비교 결과를 사용자에게 전달할
    자연어 요약으로 변환한다.

    비교 결과가 없으면 빈 문자열을 반환해
    기존 출력과 저장 동작에 영향을 주지 않는다.
    """
    if memory_insight is None:
        return ""

    summary = str(
        getattr(
            memory_insight,
            "summary",
            "",
        )
    ).strip()

    if summary:
        return summary

    sample_size = int(
        getattr(
            memory_insight,
            "sample_size",
            0,
        )
    )

    if sample_size < 1:
        return (
            "아직 비교할 과거 분석 기록이 없어 "
            "상대적인 순위를 계산할 수 없습니다."
        )

    overall_percentile = float(
        getattr(
            memory_insight,
            "overall_percentile",
            0.0,
        )
    )

    rank_label = str(
        getattr(
            memory_insight,
            "rank_label",
            "",
        )
    ).strip()

    if rank_label:
        return (
            f"최근 {sample_size}건의 분석 기록과 비교한 결과 "
            f"종합 {rank_label}에 해당하며, "
            f"백분위 점수는 {overall_percentile:.1f}입니다."
        )

    return (
        f"최근 {sample_size}건의 분석 기록과 "
        "비교했습니다."
    )


def _build_recommendation_text(
    *,
    recommendation: RecommendationResult,
    decision_report: DecisionReport,
) -> str:
    """
    강점, 약점, 경고, AI 의견을 종합해
    구체적인 판단 문장을 만든다.
    """
    parts: list[str] = []

    ai_comment = str(
        getattr(
            decision_report,
            "ai_comment",
            "",
        )
    ).strip()

    strengths = _clean_text_items(
        getattr(
            decision_report,
            "strengths",
            (),
        )
    )

    weaknesses = _clean_text_items(
        getattr(
            decision_report,
            "weaknesses",
            (),
        )
    )

    reasons = _clean_text_items(
        getattr(
            recommendation,
            "reasons",
            (),
        )
    )

    warnings = _clean_text_items(
        getattr(
            recommendation,
            "warnings",
            (),
        )
    )

    if ai_comment:
        parts.append(ai_comment)

    primary_strength = _first_unique_item(
        strengths,
        reasons,
    )

    if primary_strength:
        parts.append(
            "가장 중요한 긍정 요인은 "
            f"{primary_strength}"
        )

    primary_risk = _first_unique_item(
        weaknesses,
        warnings,
    )

    if primary_risk:
        parts.append(
            "다만 확인해야 할 위험 요인은 "
            f"{primary_risk}"
        )

    if not parts:
        action = str(
            getattr(
                recommendation,
                "action",
                "",
            )
        ).strip()

        if action:
            return (
                "현재 분석 결과에 따른 권장 판단은 "
                f"'{action}'입니다."
            )

        return (
            "현재 데이터만으로는 명확한 매입 판단을 "
            "내리기 어려우므로 추가 확인이 필요합니다."
        )

    return " ".join(parts)


def _build_next_action(
    *,
    recommendation: RecommendationResult,
    decision_report: DecisionReport,
) -> str:
    """
    추천 등급과 매입 시점 분석을 바탕으로
    사용자가 실행할 다음 행동을 제시한다.
    """
    grade = str(
        getattr(
            recommendation,
            "grade",
            "",
        )
    ).strip().upper()

    action = str(
        getattr(
            recommendation,
            "action",
            "",
        )
    ).strip()

    buy_timing = str(
        getattr(
            decision_report,
            "buy_timing",
            "",
        )
    ).strip()

    normalized_action = action.lower()

    if (
        grade == "STRONG_BUY"
        or "strong buy" in normalized_action
        or "적극 매입" in action
        or "즉시 매입" in action
    ):
        base_action = (
            "우선순위가 높은 후보로 분류하고, "
            "매입가·배송비·수수료를 마지막으로 확인한 뒤 "
            "소량 매입을 검토하세요."
        )

    elif (
        grade == "BUY"
        or normalized_action == "buy"
        or "매입 추천" in action
        or "구매 추천" in action
    ):
        base_action = (
            "현재 가격 경쟁력이 유지되는지 확인한 뒤 "
            "테스트 수량으로 매입을 검토하세요."
        )

    elif (
        grade == "WATCH"
        or "watch" in normalized_action
        or "관찰" in action
        or "대기" in action
    ):
        base_action = (
            "바로 매입하지 말고 가격과 표본 수의 변화를 "
            "추가로 수집한 뒤 다시 분석하세요."
        )

    elif (
        grade == "CAUTION"
        or "caution" in normalized_action
        or "주의" in action
        or "신중" in action
    ):
        base_action = (
            "수익성보다 위험 요인을 먼저 검증하고, "
            "조건이 개선될 때까지 매입을 보류하세요."
        )

    elif (
        grade in {"AVOID", "REJECT"}
        or "avoid" in normalized_action
        or "reject" in normalized_action
        or "매입 비추천" in action
        or "제외" in action
    ):
        base_action = (
            "현재 후보는 우선순위에서 제외하고 "
            "더 높은 수익성과 신뢰도를 가진 상품을 찾으세요."
        )

    else:
        base_action = (
            "추천 결과의 근거와 위험 요인을 다시 확인한 뒤 "
            "소량 테스트 여부를 결정하세요."
        )

    if buy_timing:
        return (
            f"{base_action} "
            f"매입 시점 판단: {buy_timing}"
        )

    return base_action


def _clean_text_items(
    values: object,
) -> tuple[str, ...]:
    """
    문자열 또는 문자열 목록을 안전하게 정리한다.
    """
    if values is None:
        return ()

    if isinstance(values, str):
        cleaned_value = values.strip()

        if not cleaned_value:
            return ()

        return (cleaned_value,)

    try:
        items = tuple(values)
    except TypeError:
        cleaned_value = str(values).strip()

        if not cleaned_value:
            return ()

        return (cleaned_value,)

    cleaned_items: list[str] = []

    for item in items:
        cleaned_item = str(item).strip()

        if (
            cleaned_item
            and cleaned_item
            not in cleaned_items
        ):
            cleaned_items.append(cleaned_item)

    return tuple(cleaned_items)


def _first_unique_item(
    primary_items: tuple[str, ...],
    secondary_items: tuple[str, ...],
) -> str:
    """
    두 근거 목록에서 가장 먼저 확인되는
    유효한 항목 하나를 선택한다.
    """
    for item in (
        *primary_items,
        *secondary_items,
    ):
        cleaned_item = item.strip()

        if cleaned_item:
            return cleaned_item

    return ""