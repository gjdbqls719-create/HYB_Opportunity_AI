from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from app.domain.discovery import (
    PRODUCTION_RECOMMENDATION_POLICY_V1,
    PRODUCTION_SAFETY_POLICY_V1,
    PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1,
    PRODUCTION_SCREENING_RANKING_POLICY_V1,
    PRODUCTION_SCREENING_SCORE_POLICY_V1,
    ScreeningReasonCategory,
    ScreeningReasonPolarity,
    ScreeningRecommendationSemantics,
    ScreeningRecommendationValue,
    StructuredScreeningReason,
)
from app.domain.opportunity import (
    ProductionSafetyAssessment,
    ProductionSafetyStatus,
)
from app.infrastructure.discovery.orchestrator_gateway import (
    opportunity_result_to_discovery_result,
)
from app.models import Product, ProductDataSource
from engine import orchestrator
from engine.explainable_score import build_explainable_score
from engine.market_adjustment import MarketAdjustmentResult
from engine.opportunity import calculate_opportunity
from engine.production_safety import apply_production_safety_gate
from engine.recommendation import (
    RecommendationResult,
    build_screening_recommendation_semantics,
    generate_recommendation,
)


def recommendation(*, score: int = 85, grade: str = "STRONG_BUY") -> RecommendationResult:
    return RecommendationResult(
        score=score,
        stars=5,
        star_display="★★★★★",
        grade=grade,
        action="강력 매입 추천" if grade == "STRONG_BUY" else "추가 검토",
        success_probability=80,
        reasons=("human reason",),
        warnings=(),
        summary="human summary",
    )


def opportunity(
    item_id: str,
    *,
    policies=PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1,
) -> orchestrator.OpportunityResult:
    raw = recommendation(score=50, grade="WATCH")
    effective = replace(
        raw,
        safety_status="READY",
        original_grade="WATCH",
        effective_grade="WATCH",
    )
    semantics = build_screening_recommendation_semantics(raw, effective)
    return orchestrator.OpportunityResult(
        product=Product(
            marketplace="ebay",
            item_id=item_id,
            title=item_id,
            price=10,
            currency="USD",
        ),
        analysis={"net_profit": 5.0},
        matched_product_count=1,
        price_intelligence=object(),
        final_opportunity_score=50.0,
        ai_recommendation=effective,
        finalized_group_id=f"group-{item_id}",
        screening_policy_descriptors=policies,
        screening_recommendation=semantics,
    )


def test_production_policy_descriptors_have_exact_v1_identity_and_rules() -> None:
    assert (
        PRODUCTION_SCREENING_SCORE_POLICY_V1.policy_name,
        PRODUCTION_SCREENING_SCORE_POLICY_V1.policy_version,
    ) == ("production-discovery-screening-score", "1.0.0")
    assert (
        PRODUCTION_RECOMMENDATION_POLICY_V1.policy_name,
        PRODUCTION_RECOMMENDATION_POLICY_V1.policy_version,
    ) == ("production-discovery-recommendation", "1.0.0")
    assert (
        PRODUCTION_SAFETY_POLICY_V1.policy_name,
        PRODUCTION_SAFETY_POLICY_V1.policy_version,
    ) == ("production-discovery-safety-gate", "1.0.0")
    assert (
        PRODUCTION_SCREENING_RANKING_POLICY_V1.policy_name,
        PRODUCTION_SCREENING_RANKING_POLICY_V1.policy_version,
    ) == ("production-discovery-screening-ranking", "1.0.0")
    assert PRODUCTION_SCREENING_RANKING_POLICY_V1.ordered_sort_keys == (
        "effective_recommendation_score:desc",
        "final_opportunity_score:desc",
        "per_unit_net_profit:desc",
    )
    assert (
        PRODUCTION_SCREENING_RANKING_POLICY_V1.equal_key_tie_behavior
        == "stable_input_order"
    )
    assert all(
        "grouping_ordinal" not in key
        for key in PRODUCTION_SCREENING_RANKING_POLICY_V1.ordered_sort_keys
    )
    assert {"estimated_monthly_sales", "competitor_count", "risk_level"} <= set(
        PRODUCTION_SCREENING_SCORE_POLICY_V1.policy_assumption_inputs
    )


def test_policy_descriptors_are_immutable_and_reject_invalid_versions() -> None:
    with pytest.raises(FrozenInstanceError):
        PRODUCTION_SCREENING_SCORE_POLICY_V1.policy_version = "2.0.0"  # type: ignore[misc]

    for invalid in ("", " ", "v1", "1.0"):
        with pytest.raises((TypeError, ValueError), match="policy_version"):
            replace(PRODUCTION_SCREENING_SCORE_POLICY_V1, policy_version=invalid)


def test_current_score_and_human_reason_outputs_are_preserved() -> None:
    result = calculate_opportunity(
        {
            "marketplace": "ebay",
            "purchase_price": 100,
            "selling_price": 200,
            "shipping_cost": 10,
            "tax_rate": 0,
            "other_cost": 0,
            "estimated_monthly_sales": 240,
            "competitor_count": 12,
            "risk_level": "low",
        }
    )

    assert result["opportunity_score"] == 86
    assert result["reasons"][:3] == [
        "ROI가 매우 높음",
        "예상 판매량이 높음",
        "경쟁이 보통",
    ]
    assert "structured_screening_reasons" not in result


def test_structured_reasons_keep_codes_text_order_and_polarity() -> None:
    first = build_explainable_score(
        base_score=30,
        roi=-1,
        net_profit=-1,
        competitor_count=80,
        risk_level="high",
        confidence=None,
        price_trend=None,
    )
    second = build_explainable_score(
        base_score=30,
        roi=-1,
        net_profit=-1,
        competitor_count=80,
        risk_level="high",
        confidence=None,
        price_trend=None,
    )

    reasons = first.structured_reasons + first.structured_warnings
    assert reasons == second.structured_reasons + second.structured_warnings
    assert all(
        reason.reason_code.startswith("discovery.screening.reason.v1.")
        for reason in reasons
    )
    assert all(reason.message in first.reasons + first.warnings for reason in reasons)
    assert all(reason.polarity is ScreeningReasonPolarity.BLOCKING for reason in reasons)
    assert {reason.category for reason in reasons} >= {
        ScreeningReasonCategory.PROFITABILITY,
        ScreeningReasonCategory.CONFIDENCE,
        ScreeningReasonCategory.PRICE_TREND,
    }


def test_unknown_free_text_does_not_create_a_reason_code() -> None:
    text = "legacy arbitrary human text"
    adjustment = MarketAdjustmentResult(
        adjustment=1.0,
        insights=(),
        reasons=(text,),
    )
    score = build_explainable_score(
        base_score=50,
        roi=20,
        net_profit=10,
        competitor_count=20,
        risk_level="medium",
        confidence=None,
        price_trend=None,
        market_adjustment=adjustment,
    )
    contribution = next(
        value for value in score.contributions if value.key == "market_adjustment"
    )

    assert text in contribution.reasons
    assert contribution.structured_reasons == ()

    raw = recommendation()
    effective = replace(
        raw,
        safety_status="READY",
        original_grade=raw.grade,
        effective_grade=raw.grade,
    )
    semantics = build_screening_recommendation_semantics(raw, effective)
    assert semantics.structured_reasons == ()


def test_structured_reason_duplicates_are_first_occurrence_stable_and_conflicts_fail() -> None:
    reason = StructuredScreeningReason(
        reason_code="discovery.screening.reason.v1.test.duplicate",
        category=ScreeningReasonCategory.RECOMMENDATION,
        polarity=ScreeningReasonPolarity.SUPPORTING,
        source_component="test",
        message="same",
    )
    value = ScreeningRecommendationValue("WATCH", "검토", "summary")
    semantics = ScreeningRecommendationSemantics(
        raw_recommendation=value,
        effective_recommendation=value,
        recommendation_score=50,
        safety_intervention_occurred=False,
        safety_status="READY",
        structured_reasons=(reason, reason),
        safety_reasons=(),
        safety_policy=PRODUCTION_SAFETY_POLICY_V1,
    )
    assert semantics.structured_reasons == (reason,)

    with pytest.raises(ValueError, match="conflicting semantics"):
        replace(
            semantics,
            structured_reasons=(reason, replace(reason, message="different")),
        )


def test_raw_and_effective_recommendation_are_equal_without_intervention() -> None:
    raw = recommendation()
    effective = apply_production_safety_gate(
        raw,
        ProductionSafetyAssessment(status=ProductionSafetyStatus.READY),
    )
    semantics = build_screening_recommendation_semantics(raw, effective)

    assert semantics.raw_recommendation == semantics.effective_recommendation
    assert semantics.raw_grade == semantics.effective_grade == "STRONG_BUY"
    assert semantics.recommendation_score == raw.score == effective.score
    assert semantics.safety_intervention_occurred is False
    assert semantics.safety_reasons == ()


def test_buy_family_safety_downgrade_is_explicit_and_preserves_score() -> None:
    raw = recommendation()
    effective = apply_production_safety_gate(
        raw,
        ProductionSafetyAssessment(
            status=ProductionSafetyStatus.INSUFFICIENT_DATA,
            missing_fields=("shipping_cost",),
        ),
    )
    semantics = build_screening_recommendation_semantics(raw, effective)

    assert semantics.raw_grade == "STRONG_BUY"
    assert semantics.effective_grade == "WATCH"
    assert semantics.recommendation_score == raw.score == effective.score == 85
    assert semantics.safety_intervention_occurred is True
    assert [reason.reason_code for reason in semantics.safety_reasons] == [
        "discovery.screening.reason.v1.production_safety.missing.shipping_cost"
    ]
    assert [reason.message for reason in semantics.safety_reasons] == list(
        effective.safety_reasons
    )


def test_non_buy_safety_findings_do_not_count_as_recommendation_intervention() -> None:
    raw = recommendation(score=45, grade="WATCH")
    effective = apply_production_safety_gate(
        raw,
        ProductionSafetyAssessment(
            status=ProductionSafetyStatus.INSUFFICIENT_DATA,
            missing_fields=("production_source",),
        ),
    )
    semantics = build_screening_recommendation_semantics(raw, effective)

    assert semantics.raw_recommendation == semantics.effective_recommendation
    assert semantics.safety_intervention_occurred is False
    assert semantics.safety_reasons


def test_ranking_policy_fields_and_correlation_are_not_sort_keys() -> None:
    changed_ranking = replace(
        PRODUCTION_SCREENING_RANKING_POLICY_V1,
        policy_name="test-only-ranking-identity",
    )
    first = opportunity("first")
    second = opportunity(
        "second",
        policies=replace(
            PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1,
            ranking=changed_ranking,
        ),
    )
    values = [first, second]

    orchestrator._sort_opportunity_results(values)

    assert values == [first, second]
    assert [value.finalized_group_id for value in values] == [
        "group-first",
        "group-second",
    ]


def test_authoritative_orchestrator_and_discovery_conversion_expose_exact_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = Product(
        marketplace="ebay",
        item_id="production-item",
        title="Production Item",
        price=Decimal("10"),
        currency="USD",
        condition="New",
        url="https://example.com/production-item",
        shipping_cost=Decimal("1"),
        data_source=ProductDataSource.PRODUCTION,
    )
    monkeypatch.setattr(orchestrator, "search_products", lambda query, limit: [product])

    result = orchestrator.find_best_opportunities(
        "item",
        grouping_phase_complete_callback=lambda descriptor: ("group-1",),
    )[0]
    converted = opportunity_result_to_discovery_result(result)

    assert (
        result.screening_policy_descriptors
        is PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1
    )
    assert result.screening_recommendation is not None
    assert converted.screening_policy_descriptors is result.screening_policy_descriptors
    assert converted.screening_recommendation is result.screening_recommendation
    assert converted.finalized_group_id == "group-1"
