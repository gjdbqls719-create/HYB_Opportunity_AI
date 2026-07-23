from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from engine.orchestrator import OpportunityResult
from presentation.models import (
    DashboardAIPartner,
    DashboardCard,
    DashboardMemory,
    DashboardMetrics,
    DashboardProduct,
    DashboardRecommendation,
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


def _analysis_float(
    analysis: dict[str, Any],
    *keys: str,
) -> float:
    for key in keys:
        if key not in analysis:
            continue

        value = analysis[key]

        if value is not None:
            return _to_float(value)

    return 0.0


def _first_text_attribute(
    target: object,
    *attribute_names: str,
) -> str:
    for attribute_name in attribute_names:
        value = _to_text(
            getattr(target, attribute_name, "")
        )

        if value:
            return value

    return ""


def _to_text(
    value: object,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_float(
    value: object,
) -> float:
    if value is None:
        return 0.0

    if isinstance(value, str):
        cleaned = (
            value.strip()
            .replace(",", "")
            .replace("%", "")
        )

        if not cleaned:
            return 0.0

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_text_tuple(
    values: object,
) -> tuple[str, ...]:
    if values is None:
        return ()

    if isinstance(values, str):
        cleaned = values.strip()

        if not cleaned:
            return ()

        return (cleaned,)

    try:
        items = tuple(values)
    except TypeError:
        cleaned = _to_text(values)

        if not cleaned:
            return ()

        return (cleaned,)

    cleaned_items: list[str] = []

    for item in items:
        cleaned = _to_text(item)

        if (
            cleaned
            and cleaned not in cleaned_items
        ):
            cleaned_items.append(cleaned)

    return tuple(cleaned_items)