from dataclasses import replace
from decimal import Decimal

import pytest

from app.application.decision_engine import (
    DecisionEvaluationService,
    DecisionMatrix,
    DefaultDecisionPolicy,
    EvaluateDecisionDimensionsRequest,
)
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionFreshness,
    DecisionOutcome,
    DecisionReasonCode,
    OpportunityIdentity,
)
from app.domain.market_intelligence import CompetitionLevel, DemandLevel
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from test_decision_dimension_evaluation import (
    competition,
    demand,
    external_signal,
    with_metadata,
)
from test_decision_engine_domain import decision_input


def evaluated_results(value):
    return DecisionEvaluationService().evaluate(
        EvaluateDecisionDimensionsRequest(value)
    ).dimension_results


def market_input(
    *,
    competition_level: CompetitionLevel,
    demand_level: DemandLevel,
):
    value = decision_input()
    value = with_metadata(
        value,
        DecisionDimension.COMPETITION,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.8"),
        freshness=DecisionFreshness.FRESH,
        competition_assessment=competition(competition_level),
    )
    return with_metadata(
        value,
        DecisionDimension.DEMAND,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.7"),
        freshness=DecisionFreshness.FRESH,
        demand_assessment=demand(demand_level),
    )


def policy_for(value) -> DefaultDecisionPolicy:
    return DefaultDecisionPolicy(value.opportunity_identity)


def test_default_policy_invest_rule() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.outcome is DecisionOutcome.INVEST
    assert result.blocking_reasons == ()
    assert DecisionReasonCode.ECONOMICS_READY in result.supporting_reasons
    assert DecisionReasonCode.SAFETY_READY in result.supporting_reasons
    assert DecisionReasonCode.LOW_COMPETITION in result.supporting_reasons
    assert DecisionReasonCode.HIGH_DEMAND in result.supporting_reasons


def test_default_policy_rejects_safety_block() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    value = replace(
        value,
        production_safety=ProductionSafetyAssessment(
            ProductionSafetyStatus.PROFITABILITY_FAILED,
            failed_checks=("profitability_filter",),
        ),
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.outcome is DecisionOutcome.REJECT
    assert result.blocking_reasons == (DecisionReasonCode.SAFETY_BLOCKED,)


def test_default_policy_reports_insufficient_economics_first() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    value = with_metadata(
        value,
        DecisionDimension.ECONOMICS,
        availability=DecisionEvidenceAvailability.UNAVAILABLE,
        confidence=None,
        freshness=DecisionFreshness.UNKNOWN,
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.outcome is DecisionOutcome.INSUFFICIENT_EVIDENCE
    assert DecisionReasonCode.ECONOMICS_UNAVAILABLE in result.uncertainty_reasons


def test_high_competition_and_low_demand_returns_review() -> None:
    value = market_input(
        competition_level=CompetitionLevel.HIGH,
        demand_level=DemandLevel.LOW,
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.outcome is DecisionOutcome.REVIEW
    assert DecisionReasonCode.HIGH_COMPETITION in result.uncertainty_reasons
    assert DecisionReasonCode.LOW_DEMAND in result.uncertainty_reasons


def test_other_dimension_combination_defaults_to_review() -> None:
    value = market_input(
        competition_level=CompetitionLevel.MEDIUM,
        demand_level=DemandLevel.MEDIUM,
    )
    assert policy_for(value).evaluate(evaluated_results(value)).outcome is DecisionOutcome.REVIEW


def test_aggregate_confidence_averages_only_available_dimensions() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.confidence.confidence == Decimal("0.875")
    assert result.confidence.availability is DecisionEvidenceAvailability.PARTIAL
    assert result.confidence.missing_dimensions == (
        DecisionDimension.EXTERNAL_REFERENCE,
    )


def test_external_reason_is_preserved_without_changing_outcome() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    result = policy_for(value).evaluate(evaluated_results(value))

    assert result.outcome is DecisionOutcome.INVEST
    assert DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE in result.uncertainty_reasons

    present = with_metadata(
        value,
        DecisionDimension.EXTERNAL_REFERENCE,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=Decimal("0.9"),
        freshness=DecisionFreshness.FRESH,
        external_signals=(external_signal(),),
    )
    present_result = policy_for(present).evaluate(evaluated_results(present))
    assert present_result.outcome is DecisionOutcome.INVEST
    assert DecisionReasonCode.EXTERNAL_SIGNAL_AGREES in present_result.supporting_reasons


def test_aggregate_confidence_is_zero_when_every_dimension_is_unavailable() -> None:
    value = decision_input()
    results = tuple(
        replace(
            result,
            availability=DecisionEvidenceAvailability.UNAVAILABLE,
            confidence=None,
            freshness=DecisionFreshness.UNKNOWN,
            reason_codes=(DecisionReasonCode.ECONOMICS_UNAVAILABLE,)
            if result.dimension is DecisionDimension.ECONOMICS
            else result.reason_codes,
        )
        for result in evaluated_results(value)
    )
    decision = policy_for(value).evaluate(results)

    assert decision.confidence.confidence == Decimal("0")
    assert decision.confidence.availability is DecisionEvidenceAvailability.UNAVAILABLE
    assert set(decision.confidence.missing_dimensions) == set(DecisionDimension)


def test_policy_uses_only_dimension_results_for_decision() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    results = evaluated_results(value)
    first = DefaultDecisionPolicy(
        OpportunityIdentity("opportunity-1", "ebay:item-1")
    ).evaluate(results)
    second = DefaultDecisionPolicy(
        OpportunityIdentity("opportunity-2", "ebay:item-2")
    ).evaluate(results)

    assert first.outcome is second.outcome
    assert first.confidence == second.confidence
    assert first.dimension_results == second.dimension_results
    assert first.opportunity_identity != second.opportunity_identity


def test_policy_validates_dimension_completeness_and_common_metadata() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    results = evaluated_results(value)
    policy = policy_for(value)

    with pytest.raises(ValueError, match="every decision dimension"):
        policy.evaluate(results[:-1])
    inconsistent = results[:-1] + (
        replace(results[-1], policy_version="other-policy"),
    )
    with pytest.raises(ValueError, match="policy_version"):
        policy.evaluate(inconsistent)


def test_decision_matrix_runs_evaluation_then_policy() -> None:
    value = market_input(
        competition_level=CompetitionLevel.LOW,
        demand_level=DemandLevel.HIGH,
    )
    result = DecisionMatrix().evaluate(value)

    assert result.outcome is DecisionOutcome.INVEST
    assert result.opportunity_identity == value.opportunity_identity
    assert len(result.dimension_results) == 5
