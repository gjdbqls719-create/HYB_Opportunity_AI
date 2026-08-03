from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from decimal import Decimal

import pytest

from app.application.dashboard import (
    DashboardReadModelAssembler,
    DashboardSummaryCard,
)
from app.application.decision_engine import DecisionExplanationService, DecisionMatrix
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionFreshness,
    DecisionOutcome,
    ExplanationCode,
    Severity,
)
from app.domain.market_intelligence import CompetitionLevel, DemandLevel
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from test_decision_dimension_evaluation import with_metadata
from test_decision_matrix import market_input


def result_for(outcome: DecisionOutcome):
    value = market_input(
        competition_level=(
            CompetitionLevel.HIGH
            if outcome is DecisionOutcome.REVIEW
            else CompetitionLevel.LOW
        ),
        demand_level=(
            DemandLevel.LOW
            if outcome is DecisionOutcome.REVIEW
            else DemandLevel.HIGH
        ),
    )
    if outcome is DecisionOutcome.REJECT:
        value = replace(
            value,
            production_safety=ProductionSafetyAssessment(
                ProductionSafetyStatus.PROFITABILITY_FAILED,
                failed_checks=("profitability_filter",),
            ),
        )
    elif outcome is DecisionOutcome.INSUFFICIENT_EVIDENCE:
        value = with_metadata(
            value,
            DecisionDimension.ECONOMICS,
            availability=DecisionEvidenceAvailability.UNAVAILABLE,
            confidence=None,
            freshness=DecisionFreshness.UNKNOWN,
        )
    return DecisionMatrix().evaluate(value)


def read_model(outcome: DecisionOutcome = DecisionOutcome.INVEST):
    result = result_for(outcome)
    explanation = DecisionExplanationService().explain(result)
    return DashboardReadModelAssembler().assemble(result, explanation)


@pytest.mark.parametrize(
    ("outcome", "primary_action"),
    (
        (DecisionOutcome.INVEST, "Proceed to Validation"),
        (DecisionOutcome.REVIEW, "Collect More Evidence"),
        (DecisionOutcome.REJECT, "Do Not Proceed"),
        (
            DecisionOutcome.INSUFFICIENT_EVIDENCE,
            "Acquire Required Evidence",
        ),
    ),
)
def test_dashboard_action_mapping(
    outcome: DecisionOutcome,
    primary_action: str,
) -> None:
    value = read_model(outcome)

    assert value.action_card.outcome is outcome
    assert value.action_card.primary_action == primary_action
    assert value.action_card.secondary_action is None


def test_summary_card_reuses_decision_summary_values() -> None:
    result = result_for(DecisionOutcome.INVEST)
    explanation = DecisionExplanationService().explain(result)
    value = DashboardReadModelAssembler().assemble(result, explanation)

    assert value.summary_card.outcome is explanation.summary.outcome
    assert value.summary_card.summary is explanation.summary
    assert value.summary_card.aggregate_confidence == explanation.summary.aggregate_confidence
    assert value.summary_card.summary_code is ExplanationCode.INVEST_READY
    assert value.summary_card.summary_text == explanation.summary.default_text


def test_warning_cards_include_only_warning_and_critical_items() -> None:
    review = read_model(DecisionOutcome.REVIEW)
    reject = read_model(DecisionOutcome.REJECT)

    assert review.warning_cards
    assert all(
        value.item.severity in {Severity.WARNING, Severity.CRITICAL}
        for value in review.warning_cards
    )
    assert tuple(value.display_order for value in review.warning_cards) == tuple(
        range(1, len(review.warning_cards) + 1)
    )
    assert any(
        value.item.severity is Severity.CRITICAL
        for value in reject.warning_cards
    )


def test_evidence_cards_use_fixed_dimension_order_and_existing_values() -> None:
    result = result_for(DecisionOutcome.INVEST)
    explanation = DecisionExplanationService().explain(result)
    value = DashboardReadModelAssembler().assemble(result, explanation)
    result_by_dimension = {
        item.dimension: item for item in result.dimension_results
    }

    assert tuple(card.dimension for card in value.evidence_cards) == tuple(
        DecisionDimension
    )
    assert tuple(card.display_order for card in value.evidence_cards) == (1, 2, 3, 4, 5)
    for card in value.evidence_cards:
        source = result_by_dimension[card.dimension]
        assert card.dimension_result is source
        assert card.availability is source.availability
        assert card.confidence == source.confidence
        assert card.freshness is source.freshness
    assert value.evidence_cards[-1].severity is Severity.WARNING


def test_read_model_is_immutable_equal_and_deterministic() -> None:
    first = read_model()
    second = read_model()

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.schema_version = "changed"
    with pytest.raises(TypeError, match="tuple"):
        replace(first, warning_cards=list(first.warning_cards))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(first, generated_at=datetime(2026, 8, 3, 12))


def test_assembler_preserves_inputs_and_versions() -> None:
    result = result_for(DecisionOutcome.INVEST)
    explanation = DecisionExplanationService().explain(result)
    result_before = repr(result)
    explanation_before = repr(explanation)

    value = DashboardReadModelAssembler().assemble(result, explanation)

    assert repr(result) == result_before
    assert repr(explanation) == explanation_before
    assert value.generated_at == result.generated_at
    assert value.schema_version == result.schema_version
    assert value.policy_version == result.policy_version


def test_assembler_rejects_mismatched_result_and_explanation() -> None:
    invest = result_for(DecisionOutcome.INVEST)
    review = result_for(DecisionOutcome.REVIEW)
    explanation = DecisionExplanationService().explain(review)

    with pytest.raises(ValueError, match="outcomes must match"):
        DashboardReadModelAssembler().assemble(invest, explanation)


def test_summary_card_validates_decimal_confidence() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        DashboardSummaryCard(
            summary=replace(
                read_model().summary_card.summary,
                aggregate_confidence=0.9,
            ),
        )
    assert read_model().summary_card.aggregate_confidence == Decimal("0.875")
