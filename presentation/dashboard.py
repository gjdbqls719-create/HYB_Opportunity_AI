from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from engine.orchestrator import OpportunityResult
from presentation.models import (
    DashboardAIPartner,
    DashboardCard,
    DashboardDecisionStep,
    DashboardEvidence,
    DashboardMemory,
    DashboardMetrics,
    DashboardProduct,
    DashboardRecommendation,
)

from presentation.dashboard_utils import (
    _analysis_float,
    _first_text_attribute,
    _to_float,
    _to_text,
    _to_text_tuple,
)


def build_dashboard_card(
    result: OpportunityResult,
) -> DashboardCard:
    """
    OpportunityResult를 화면 독립적인 DashboardCard로 변환한다.

    엔진 객체를 CLI, Web, API에 직접 전달하지 않고,
    Presentation 계층에서 사용할 데이터만 추출한다.
    """
    return DashboardCard(
        product=_build_product(result),
        metrics=_build_metrics(result),
        recommendation=_build_recommendation(result),
        ai_partner=_build_ai_partner(result),
        memory=_build_memory(result),
        confidence_level=_extract_confidence_level(result),
        trend_direction=_extract_trend_direction(result),
        decision=_extract_decision(result),
        decision_timeline=_build_decision_timeline(
            result
        ),
    )


def build_dashboard_cards(
    results: Iterable[OpportunityResult],
) -> list[DashboardCard]:
    """
    여러 OpportunityResult를 DashboardCard 목록으로 변환한다.

    입력 순서를 그대로 유지한다.
    """
    return [
        build_dashboard_card(result)
        for result in results
    ]


def _build_product(
    result: OpportunityResult,
) -> DashboardProduct:
    product = result.product

    return DashboardProduct(
        marketplace=_to_text(
            getattr(product, "marketplace", "")
        ),
        item_id=_to_text(
            getattr(product, "item_id", "")
        ),
        title=_to_text(
            getattr(product, "title", "")
        ),
        price=_to_float(
            getattr(product, "price", 0.0)
        ),
        shipping_cost=_to_float(
            getattr(product, "shipping_cost", 0.0)
        ),
        total_cost=_to_float(
            getattr(product, "total_cost", 0.0)
        ),
        currency=_to_text(
            getattr(product, "currency", "")
        ),
        condition=_to_text(
            getattr(product, "condition", "")
        ),
        url=_to_text(
            getattr(product, "url", "")
        ),
        image_url=_to_text(
            getattr(product, "image_url", "")
        ),
        seller=_to_text(
            getattr(product, "seller", "")
        ),
        in_stock=bool(
            getattr(product, "in_stock", True)
        ),
    )


def _build_metrics(
    result: OpportunityResult,
) -> DashboardMetrics:
    analysis = result.analysis

    return DashboardMetrics(
        expected_selling_price=_analysis_float(
            analysis,
            "expected_selling_price",
            "expected_sale_price",
            "selling_price",
            "target_price",
        ),
        landed_cost=_analysis_float(
            analysis,
            "landed_cost",
        ),
        selling_cost=_analysis_float(
            analysis,
            "selling_cost",
        ),
        total_cost=_analysis_float(
            analysis,
            "total_cost",
        ),
        net_profit=_analysis_float(
            analysis,
            "net_profit",
            "expected_profit",
            "profit",
        ),
        margin_rate=_analysis_float(
            analysis,
            "margin_rate",
        ),
        roi=_analysis_float(
            analysis,
            "roi",
            "roi_percent",
            "return_on_investment",
        ),
        landed_cost_roi=_analysis_float(
            analysis,
            "landed_cost_roi",
        ),
        opportunity_score=_analysis_float(
            analysis,
            "opportunity_score",
            "score",
        ),
        adjusted_opportunity_score=_to_float(
            result.adjusted_opportunity_score
        ),
        final_opportunity_score=_to_float(
            result.final_opportunity_score
        ),
        matched_product_count=int(
            result.matched_product_count
        ),
    )


def _build_recommendation(
    result: OpportunityResult,
) -> DashboardRecommendation | None:
    recommendation = result.ai_recommendation

    if recommendation is None:
        return None

    return DashboardRecommendation(
        grade=_to_text(
            getattr(recommendation, "grade", "")
        ),
        action=_to_text(
            getattr(recommendation, "action", "")
        ),
        score=_to_float(
            getattr(recommendation, "score", 0.0)
        ),
        success_probability=_to_float(
            getattr(
                recommendation,
                "success_probability",
                0.0,
            )
        ),
        summary=_to_text(
            getattr(recommendation, "summary", "")
        ),
        reasons=_to_text_tuple(
            getattr(recommendation, "reasons", ())
        ),
        warnings=_to_text_tuple(
            getattr(recommendation, "warnings", ())
        ),
    )


def _build_ai_partner(
    result: OpportunityResult,
) -> DashboardAIPartner | None:
    report = result.ai_partner_report

    if report is None:
        return None

    return DashboardAIPartner(
        title=_to_text(
            getattr(report, "title", "")
        ),
        summary=_to_text(
            getattr(report, "summary", "")
        ),
        recommendation=_to_text(
            getattr(report, "recommendation", "")
        ),
        next_action=_to_text(
            getattr(report, "next_action", "")
        ),
        memory_summary=_to_text(
            getattr(report, "memory_summary", "")
        ),
    )


def _build_memory(
    result: OpportunityResult,
) -> DashboardMemory | None:
    memory = result.memory_insight

    if memory is None:
        return None

    return DashboardMemory(
        sample_size=int(
            _to_float(
                getattr(memory, "sample_size", 0)
            )
        ),
        rank_label=_to_text(
            getattr(memory, "rank_label", "")
        ),
        overall_percentile=_to_float(
            getattr(memory, "overall_percentile", 0.0)
        ),
        summary=_to_text(
            getattr(memory, "summary", "")
        ),
    )


def _build_decision_timeline(
    result: OpportunityResult,
) -> tuple[DashboardDecisionStep, ...]:
    """
    엔진이 이미 계산한 결과를 의사결정 순서대로 정리한다.

    새로운 판단이나 점수 계산은 수행하지 않는다.
    각 분석 객체가 제공하는 기존 결과를 Summary와
    구조화된 Evidence로 변환한다.
    """
    steps: list[DashboardDecisionStep] = []

    confidence_level = _extract_confidence_level(
        result
    )

    if confidence_level:
        steps.append(
            DashboardDecisionStep(
                stage="confidence",
                title="Data Confidence",
                summary=confidence_level,
                evidence=_build_confidence_evidence(
                    result
                ),
            )
        )

    trend_direction = _extract_trend_direction(
        result
    )

    if trend_direction:
        steps.append(
            DashboardDecisionStep(
                stage="price_trend",
                title="Price Trend",
                summary=trend_direction,
                evidence=_build_price_trend_evidence(
                    result
                ),
            )
        )

    inventory_analysis = (
        result.inventory_analysis
    )

    if inventory_analysis is not None:
        inventory_summary = _first_text_attribute(
            inventory_analysis,
            "summary",
            "insight",
            "status",
            "condition",
        )

        if inventory_summary:
            steps.append(
                DashboardDecisionStep(
                    stage="inventory",
                    title="Inventory",
                    summary=inventory_summary,
                    evidence=_build_object_evidence(
                        inventory_analysis,
                        (
                            ("Insight", "insight"),
                            ("Reason", "reason"),
                            ("Warning", "warning"),
                        ),
                        excluded_values=(
                            inventory_summary,
                        ),
                    ),
                )
            )

    seller_analysis = result.seller_analysis

    if seller_analysis is not None:
        seller_summary = _first_text_attribute(
            seller_analysis,
            "summary",
            "insight",
            "status",
            "condition",
        )

        if seller_summary:
            steps.append(
                DashboardDecisionStep(
                    stage="seller",
                    title="Seller Competition",
                    summary=seller_summary,
                    evidence=_build_object_evidence(
                        seller_analysis,
                        (
                            ("Insight", "insight"),
                            ("Reason", "reason"),
                            ("Warning", "warning"),
                        ),
                        excluded_values=(
                            seller_summary,
                        ),
                    ),
                )
            )

    market_explanations = (
        _extract_market_explanations(result)
    )

    market_evidence = _build_market_evidence(
        result
    )

    for index, explanation in enumerate(
        market_explanations
    ):
        steps.append(
            DashboardDecisionStep(
                stage="market",
                title="Market Analysis",
                summary=explanation,
                evidence=(
                    market_evidence
                    if index == 0
                    else ()
                ),
            )
        )

    recommendation = result.ai_recommendation

    if recommendation is not None:
        recommendation_summary = _to_text(
            getattr(
                recommendation,
                "summary",
                "",
            )
        )

        recommendation_grade = _to_text(
            getattr(
                recommendation,
                "grade",
                "",
            )
        )

        summary = (
            recommendation_summary
            or recommendation_grade
        )

        if summary:
            steps.append(
                DashboardDecisionStep(
                    stage="recommendation",
                    title="Recommendation",
                    summary=summary,
                    evidence=(
                        _build_recommendation_evidence(
                            recommendation
                        )
                    ),
                )
            )

    ai_partner = result.ai_partner_report

    if ai_partner is not None:
        next_action = _to_text(
            getattr(
                ai_partner,
                "next_action",
                "",
            )
        )

        if next_action:
            steps.append(
                DashboardDecisionStep(
                    stage="ai_partner",
                    title="AI Partner",
                    summary=next_action,
                    evidence=_build_ai_partner_evidence(
                        ai_partner
                    ),
                )
            )

    return tuple(steps)


def _build_confidence_evidence(
    result: OpportunityResult,
) -> tuple[DashboardEvidence, ...]:
    confidence = result.confidence

    if confidence is None:
        return ()

    return _build_object_evidence(
        confidence,
        (
            ("Score", "score"),
            ("Reason", "reason"),
            ("Summary", "summary"),
        ),
        excluded_values=(
            _extract_confidence_level(result),
        ),
    )


def _build_price_trend_evidence(
    result: OpportunityResult,
) -> tuple[DashboardEvidence, ...]:
    price_trend = result.price_trend

    if price_trend is None:
        return ()

    return _build_object_evidence(
        price_trend,
        (
            ("Position", "price_position"),
            ("Lowest Price", "lowest_price"),
            ("Highest Price", "highest_price"),
            ("Average Price", "average_price"),
            (
                "History Available",
                "has_sufficient_history",
            ),
        ),
        excluded_values=(
            _extract_trend_direction(result),
        ),
    )


def _build_market_evidence(
    result: OpportunityResult,
) -> tuple[DashboardEvidence, ...]:
    market_adjustment = result.market_adjustment

    if market_adjustment is None:
        return ()

    evidence: list[DashboardEvidence] = []

    evidence.extend(
        _build_evidence_items(
            label="Reason",
            values=getattr(
                market_adjustment,
                "reasons",
                (),
            ),
        )
    )

    evidence.extend(
        _build_evidence_items(
            label="Insight",
            values=getattr(
                market_adjustment,
                "insights",
                (),
            ),
        )
    )

    adjustment = getattr(
        market_adjustment,
        "adjustment",
        None,
    )

    adjustment_text = _to_text(adjustment)

    if (
        adjustment is not None
        and adjustment_text
    ):
        evidence.append(
            DashboardEvidence(
                label="Adjustment",
                value=adjustment_text,
            )
        )

    return _deduplicate_evidence(evidence)


def _build_recommendation_evidence(
    recommendation: object,
) -> tuple[DashboardEvidence, ...]:
    evidence: list[DashboardEvidence] = []

    evidence.extend(
        _build_evidence_items(
            label="Reason",
            values=getattr(
                recommendation,
                "reasons",
                (),
            ),
        )
    )

    evidence.extend(
        _build_evidence_items(
            label="Warning",
            values=getattr(
                recommendation,
                "warnings",
                (),
            ),
        )
    )

    grade = _to_text(
        getattr(
            recommendation,
            "grade",
            "",
        )
    )

    action = _to_text(
        getattr(
            recommendation,
            "action",
            "",
        )
    )

    if grade:
        evidence.append(
            DashboardEvidence(
                label="Grade",
                value=grade,
            )
        )

    if action and action != grade:
        evidence.append(
            DashboardEvidence(
                label="Action",
                value=action,
            )
        )

    return _deduplicate_evidence(evidence)


def _build_ai_partner_evidence(
    ai_partner: object,
) -> tuple[DashboardEvidence, ...]:
    evidence: list[DashboardEvidence] = []

    recommendation = _to_text(
        getattr(
            ai_partner,
            "recommendation",
            "",
        )
    )

    summary = _to_text(
        getattr(
            ai_partner,
            "summary",
            "",
        )
    )

    memory_summary = _to_text(
        getattr(
            ai_partner,
            "memory_summary",
            "",
        )
    )

    if recommendation:
        evidence.append(
            DashboardEvidence(
                label="Recommendation",
                value=recommendation,
            )
        )

    if summary:
        evidence.append(
            DashboardEvidence(
                label="Summary",
                value=summary,
            )
        )

    if memory_summary:
        evidence.append(
            DashboardEvidence(
                label="Memory",
                value=memory_summary,
            )
        )

    return _deduplicate_evidence(evidence)


def _build_object_evidence(
    target: object,
    fields: tuple[tuple[str, str], ...],
    *,
    excluded_values: tuple[str, ...] = (),
) -> tuple[DashboardEvidence, ...]:
    excluded = {
        value.strip()
        for value in excluded_values
        if value and value.strip()
    }

    evidence: list[DashboardEvidence] = []

    for label, attribute_name in fields:
        raw_value = getattr(
            target,
            attribute_name,
            None,
        )

        values = _to_text_tuple(raw_value)

        for value in values:
            if value in excluded:
                continue

            evidence.append(
                DashboardEvidence(
                    label=label,
                    value=value,
                )
            )

    return _deduplicate_evidence(evidence)


def _build_evidence_items(
    *,
    label: str,
    values: object,
) -> tuple[DashboardEvidence, ...]:
    return tuple(
        DashboardEvidence(
            label=label,
            value=value,
        )
        for value in _to_text_tuple(values)
    )


def _deduplicate_evidence(
    evidence: list[DashboardEvidence],
) -> tuple[DashboardEvidence, ...]:
    unique_items: list[DashboardEvidence] = []
    seen: set[tuple[str, str]] = set()

    for item in evidence:
        key = (
            item.label.strip(),
            item.value.strip(),
        )

        if not key[0] or not key[1]:
            continue

        if key in seen:
            continue

        seen.add(key)

        unique_items.append(
            DashboardEvidence(
                label=key[0],
                value=key[1],
            )
        )

    return tuple(unique_items)


def _extract_market_explanations(
    result: OpportunityResult,
) -> tuple[str, ...]:
    """
    DecisionReport를 우선적인 설명 원천으로 사용하고,
    없으면 MarketAdjustment의 설명을 사용한다.

    이를 통해 기존 객체나 일부 테스트 객체도
    안전하게 처리할 수 있다.
    """
    decision_report = result.decision_report

    if decision_report is not None:
        explanations = _to_text_tuple(
            getattr(
                decision_report,
                "market_explanations",
                (),
            )
        )

        if explanations:
            return explanations

    market_adjustment = result.market_adjustment

    if market_adjustment is None:
        return ()

    return _to_text_tuple(
        getattr(
            market_adjustment,
            "explanations",
            (),
        )
    )


def _extract_confidence_level(
    result: OpportunityResult,
) -> str:
    confidence = result.confidence

    if confidence is None:
        return ""

    return _first_text_attribute(
        confidence,
        "level",
        "confidence_level",
        "grade",
        "label",
    )


def _extract_trend_direction(
    result: OpportunityResult,
) -> str:
    price_trend = result.price_trend

    if price_trend is not None:
        direction = _first_text_attribute(
            price_trend,
            "direction",
            "trend_direction",
            "trend",
            "label",
        )

        if direction:
            return direction

    trend_score = result.trend_score

    if trend_score is not None:
        return _first_text_attribute(
            trend_score,
            "direction",
            "trend_direction",
            "trend",
            "label",
        )

    return ""


def _extract_decision(
    result: OpportunityResult,
) -> str:
    recommendation = result.ai_recommendation

    if recommendation is not None:
        action = _to_text(
            getattr(recommendation, "action", "")
        )

        if action:
            return action

        grade = _to_text(
            getattr(recommendation, "grade", "")
        )

        if grade:
            return grade

    decision_report = result.decision_report

    if decision_report is not None:
        return _first_text_attribute(
            decision_report,
            "decision",
            "action",
            "recommendation",
            "grade",
        )

    return ""