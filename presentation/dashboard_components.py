from __future__ import annotations

from engine.orchestrator import OpportunityResult
from presentation.dashboard_utils import (
    _analysis_float,
    _to_float,
    _to_text,
    _to_text_tuple,
)
from presentation.models import (
    DashboardAIPartner,
    DashboardMemory,
    DashboardMetrics,
    DashboardProduct,
    DashboardRecommendation,
)


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
        safety_status=_to_text(
            getattr(recommendation, "safety_status", "NOT_EVALUATED")
        ),
        safety_reasons=_to_text_tuple(
            getattr(recommendation, "safety_reasons", ())
        ),
        original_grade=_to_text(
            getattr(recommendation, "original_grade", "")
        ),
        effective_grade=_to_text(
            getattr(recommendation, "effective_grade", "")
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
