from dataclasses import replace
from decimal import Decimal

from app.application.decision_engine import (
    CompetitionEvaluator,
    DecisionEvaluationService,
    DemandEvaluator,
    EconomicsEvaluator,
    EvaluateDecisionDimensionsRequest,
    ExternalEvaluator,
    SafetyEvaluator,
)
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionEvidenceMetadata,
    DecisionFreshness,
    DecisionReasonCode,
)
from app.domain.market_intelligence import (
    CompetitionAssessment,
    CompetitionLevel,
    DemandAssessment,
    DemandAssessmentAvailability,
    DemandLevel,
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketEvidence,
    MarketEvidenceStatus,
    PopularityLevel,
    PricePressure,
    ReviewQuality,
    RocketCompetitionLevel,
)
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from test_decision_engine_domain import NOW, decision_input, identity


def with_metadata(
    decision_input_value,
    dimension: DecisionDimension,
    *,
    availability: DecisionEvidenceAvailability,
    confidence: Decimal | None,
    freshness: DecisionFreshness,
    **changes: object,
):
    values = tuple(
        DecisionEvidenceMetadata(
            dimension=value.dimension,
            availability=availability,
            confidence=confidence,
            freshness=freshness,
        )
        if value.dimension is dimension
        else value
        for value in decision_input_value.evidence_metadata
    )
    return replace(decision_input_value, evidence_metadata=values, **changes)


def competition(level: CompetitionLevel) -> CompetitionAssessment:
    return CompetitionAssessment(
        competition_level=level,
        price_pressure=PricePressure.MEDIUM,
        rocket_competition=RocketCompetitionLevel.LOW,
        market_concentration=Decimal("0.2"),
        confidence=Decimal("0.8"),
        summary="Competition assessment.",
        generated_at=NOW,
        schema_version="competition-assessment-v1",
    )


def demand(
    level: DemandLevel,
    availability: DemandAssessmentAvailability = DemandAssessmentAvailability.COMPLETE,
) -> DemandAssessment:
    partial = availability is DemandAssessmentAvailability.PARTIAL
    return DemandAssessment(
        demand_level=level,
        popularity_level=PopularityLevel.HIGH,
        review_quality=ReviewQuality.GOOD,
        availability=availability,
        available_metrics=(
            "search_volume",
            "review_count",
            "rating",
            "coupang_popularity_rank",
        ) if partial else (
            "search_volume",
            "review_count",
            "rating",
            "coupang_popularity_rank",
            "itemscout_popularity_rank",
        ),
        missing_metrics=("itemscout_popularity_rank",) if partial else (),
        reasons=("itemscout_popularity_rank evidence unavailable",) if partial else (),
        confidence=Decimal("0.7"),
        summary="Demand assessment.",
        generated_at=NOW,
        schema_version="demand-assessment-v1",
    )


def external_signal() -> ExternalMarketSignal:
    market_identity = identity()
    return ExternalMarketSignal(
        signal_id="signal-1",
        identity=market_identity,
        source_type=ExternalSignalSourceType.MANUAL_INPUT,
        signal_name="search_volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
        evidence=MarketEvidence(
            value=1200,
            source="founder",
            reference="manual:1",
            observed_at=NOW,
            status=MarketEvidenceStatus.HUMAN_VERIFIED,
            confidence=Decimal("0.9"),
            market=market_identity.market,
            marketplace=market_identity.marketplace,
            collection_method="manual",
            schema_version="market-evidence-v1",
        ),
        captured_at=NOW,
        schema_version="external-signal-v1",
        verified_at=NOW,
        operator_id="founder-1",
    )


def test_economics_evaluator_passes_dimension_metadata() -> None:
    value = with_metadata(
        decision_input(),
        DecisionDimension.ECONOMICS,
        availability=DecisionEvidenceAvailability.PARTIAL,
        confidence=Decimal("0.65"),
        freshness=DecisionFreshness.STALE,
    )
    result = EconomicsEvaluator().evaluate(value)

    assert result.dimension is DecisionDimension.ECONOMICS
    assert result.availability is DecisionEvidenceAvailability.PARTIAL
    assert result.confidence == Decimal("0.65")
    assert result.freshness is DecisionFreshness.STALE
    assert result.reason_codes == (DecisionReasonCode.ECONOMICS_READY,)


def test_economics_unavailable_reason() -> None:
    value = with_metadata(
        decision_input(),
        DecisionDimension.ECONOMICS,
        availability=DecisionEvidenceAvailability.UNAVAILABLE,
        confidence=None,
        freshness=DecisionFreshness.UNKNOWN,
    )
    assert EconomicsEvaluator().evaluate(value).reason_codes == (
        DecisionReasonCode.ECONOMICS_UNAVAILABLE,
    )


def test_safety_evaluator_maps_existing_status_without_calculation() -> None:
    ready = SafetyEvaluator().evaluate(decision_input())
    blocked = SafetyEvaluator().evaluate(
        decision_input(
            production_safety=ProductionSafetyAssessment(
                ProductionSafetyStatus.PROFITABILITY_FAILED,
                failed_checks=("profitability_filter",),
            )
        )
    )
    assert ready.reason_codes == (DecisionReasonCode.SAFETY_READY,)
    assert blocked.reason_codes == (DecisionReasonCode.SAFETY_BLOCKED,)


def test_competition_evaluator_uses_existing_assessment_levels() -> None:
    base = decision_input()
    unavailable = CompetitionEvaluator().evaluate(base)
    low_input = with_metadata(
        base,
        DecisionDimension.COMPETITION,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.8"),
        freshness=DecisionFreshness.FRESH,
        competition_assessment=competition(CompetitionLevel.LOW),
    )
    high_input = replace(
        low_input,
        competition_assessment=competition(CompetitionLevel.VERY_HIGH),
    )

    assert unavailable.reason_codes == (DecisionReasonCode.COMPETITION_UNAVAILABLE,)
    assert CompetitionEvaluator().evaluate(low_input).reason_codes == (
        DecisionReasonCode.LOW_COMPETITION,
    )
    assert CompetitionEvaluator().evaluate(high_input).reason_codes == (
        DecisionReasonCode.HIGH_COMPETITION,
    )


def test_demand_evaluator_preserves_direction_and_partial_availability() -> None:
    base = decision_input()
    unavailable = DemandEvaluator().evaluate(base)
    high_input = with_metadata(
        base,
        DecisionDimension.DEMAND,
        availability=DecisionEvidenceAvailability.PARTIAL,
        confidence=Decimal("0.7"),
        freshness=DecisionFreshness.FRESH,
        demand_assessment=demand(
            DemandLevel.HIGH,
            DemandAssessmentAvailability.PARTIAL,
        ),
    )
    low_input = with_metadata(
        high_input,
        DecisionDimension.DEMAND,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.7"),
        freshness=DecisionFreshness.FRESH,
        demand_assessment=demand(DemandLevel.LOW),
    )

    assert unavailable.reason_codes == (DecisionReasonCode.DEMAND_UNAVAILABLE,)
    assert DemandEvaluator().evaluate(high_input).reason_codes == (
        DecisionReasonCode.HIGH_DEMAND,
        DecisionReasonCode.DEMAND_PARTIAL,
    )
    assert DemandEvaluator().evaluate(low_input).reason_codes == (
        DecisionReasonCode.LOW_DEMAND,
    )


def test_external_evaluator_reports_presence_without_outcome() -> None:
    base = decision_input()
    unavailable = ExternalEvaluator().evaluate(base)
    present_input = with_metadata(
        base,
        DecisionDimension.EXTERNAL_REFERENCE,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.9"),
        freshness=DecisionFreshness.FRESH,
        external_signals=(external_signal(),),
    )
    present = ExternalEvaluator().evaluate(present_input)

    assert unavailable.reason_codes == (
        DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE,
    )
    assert present.reason_codes == (DecisionReasonCode.EXTERNAL_SIGNAL_AGREES,)
    assert not hasattr(present, "outcome")


def test_evaluators_do_not_read_unrelated_dimensions() -> None:
    base = decision_input()
    changed_safety = replace(
        base,
        production_safety=ProductionSafetyAssessment(
            ProductionSafetyStatus.PROFITABILITY_FAILED,
            failed_checks=("profitability_filter",),
        ),
    )
    assert EconomicsEvaluator().evaluate(base) == EconomicsEvaluator().evaluate(
        changed_safety
    )
    assert DemandEvaluator().evaluate(base) == DemandEvaluator().evaluate(
        changed_safety
    )


def test_service_returns_five_dimension_results_in_stable_order() -> None:
    response = DecisionEvaluationService().evaluate(
        EvaluateDecisionDimensionsRequest(decision_input())
    )

    assert tuple(result.dimension for result in response.dimension_results) == tuple(
        DecisionDimension
    )
    assert len(response.dimension_results) == 5
    assert not hasattr(response, "outcome")
    assert not hasattr(response, "decision_result")
