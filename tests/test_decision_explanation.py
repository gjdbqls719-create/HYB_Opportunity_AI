from dataclasses import FrozenInstanceError, replace
from datetime import datetime

import pytest

from app.application.decision_engine import DecisionExplanationService, DecisionMatrix
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionExplanation,
    DecisionFreshness,
    DecisionOutcome,
    DecisionReasonCode,
    ExplanationCode,
    Severity,
)
from app.domain.market_intelligence import CompetitionLevel, DemandLevel
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from test_decision_matrix import market_input


def decision(
    competition_level: CompetitionLevel = CompetitionLevel.LOW,
    demand_level: DemandLevel = DemandLevel.HIGH,
):
    return DecisionMatrix().evaluate(
        market_input(
            competition_level=competition_level,
            demand_level=demand_level,
        )
    )


def explanation_for(result=None) -> DecisionExplanation:
    return DecisionExplanationService().explain(result or decision())


def test_invest_explanation_summary_and_sections() -> None:
    value = explanation_for()

    assert value.summary.outcome is DecisionOutcome.INVEST
    assert value.summary.summary_code is ExplanationCode.INVEST_READY
    assert value.summary.default_text == (
        "Investment conditions satisfy the current decision policy."
    )
    assert tuple((section.title, section.display_order) for section in value.sections) == (
        ("Summary", 1),
        ("Strengths", 2),
        ("Warnings", 3),
        ("Missing Evidence", 4),
    )


def test_review_explanation_uses_more_evidence_summary() -> None:
    result = decision(CompetitionLevel.HIGH, DemandLevel.LOW)
    value = explanation_for(result)

    assert value.summary.summary_code is ExplanationCode.REVIEW_MORE_EVIDENCE
    assert value.summary.default_text == "Additional evidence is recommended."
    warning_codes = tuple(item.reason_code for item in value.sections[2].items)
    assert DecisionReasonCode.HIGH_COMPETITION in warning_codes
    assert DecisionReasonCode.LOW_DEMAND in warning_codes


def test_reject_explanation_uses_safety_summary_and_critical_severity() -> None:
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
    explanation = explanation_for(DecisionMatrix().evaluate(value))

    assert explanation.summary.summary_code is ExplanationCode.REJECT_SAFETY
    safety_item = next(
        item
        for item in explanation.sections[2].items
        if item.reason_code is DecisionReasonCode.SAFETY_BLOCKED
    )
    assert safety_item.severity is Severity.CRITICAL


def test_insufficient_evidence_explanation() -> None:
    original = decision()
    economics = next(
        value
        for value in original.dimension_results
        if value.dimension is DecisionDimension.ECONOMICS
    )
    unavailable = replace(
        economics,
        availability=DecisionEvidenceAvailability.UNAVAILABLE,
        confidence=None,
        freshness=DecisionFreshness.UNKNOWN,
        reason_codes=(DecisionReasonCode.ECONOMICS_UNAVAILABLE,),
    )
    results = tuple(
        unavailable if value.dimension is DecisionDimension.ECONOMICS else value
        for value in original.dimension_results
    )
    revised = replace(
        original,
        outcome=DecisionOutcome.INSUFFICIENT_EVIDENCE,
        dimension_results=results,
        confidence=replace(
                original.confidence,
                availability=DecisionEvidenceAvailability.PARTIAL,
                missing_dimensions=(
                    DecisionDimension.ECONOMICS,
                    DecisionDimension.EXTERNAL_REFERENCE,
                ),
        ),
        supporting_reasons=tuple(
            reason
            for reason in original.supporting_reasons
            if reason is not DecisionReasonCode.ECONOMICS_READY
        ),
        uncertainty_reasons=(
            DecisionReasonCode.ECONOMICS_UNAVAILABLE,
            DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE,
        ),
    )
    explanation = explanation_for(revised)

    assert explanation.summary.summary_code is ExplanationCode.INSUFFICIENT_VERIFIED_EVIDENCE
    assert explanation.missing_evidence == (
        DecisionDimension.ECONOMICS,
        DecisionDimension.EXTERNAL_REFERENCE,
    )
    assert explanation.sections[3].items[0].reason_code is DecisionReasonCode.ECONOMICS_UNAVAILABLE


def test_severity_mapping_and_evidence_summary_order() -> None:
    value = explanation_for()
    strengths = {item.reason_code: item.severity for item in value.sections[1].items}
    warnings = {
        item.reason_code: item.severity
        for section in value.sections[2:]
        for item in section.items
    }

    assert strengths[DecisionReasonCode.ECONOMICS_READY] is Severity.INFO
    assert strengths[DecisionReasonCode.LOW_COMPETITION] is Severity.INFO
    assert strengths[DecisionReasonCode.HIGH_DEMAND] is Severity.INFO
    assert warnings[DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE] is Severity.WARNING
    assert tuple(item.dimension for item in value.evidence_summary) == tuple(
        DecisionDimension
    )


@pytest.mark.parametrize(
    "reason",
    (DecisionReasonCode.DEMAND_PARTIAL, DecisionReasonCode.MARKET_STALE),
)
def test_explicit_warning_severity_mapping(reason: DecisionReasonCode) -> None:
    original = decision(CompetitionLevel.HIGH, DemandLevel.LOW)
    target_dimension = (
        DecisionDimension.DEMAND
        if reason is DecisionReasonCode.DEMAND_PARTIAL
        else DecisionDimension.COMPETITION
    )
    results = tuple(
        replace(value, reason_codes=(reason,))
        if value.dimension is target_dimension
        else value
        for value in original.dimension_results
    )
    revised = replace(
        original,
        dimension_results=results,
        uncertainty_reasons=(reason, DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE),
    )
    item = next(
        item
        for item in explanation_for(revised).sections[2].items
        if item.reason_code is reason
    )
    assert item.severity is Severity.WARNING


def test_missing_evidence_section_and_counts() -> None:
    value = explanation_for()

    assert value.missing_evidence == (DecisionDimension.EXTERNAL_REFERENCE,)
    assert value.summary.missing_dimension_count == 1
    assert value.sections[3].items[0].dimension is DecisionDimension.EXTERNAL_REFERENCE
    assert value.summary.supporting_dimension_count == 4


def test_explanation_is_immutable_equal_and_deterministic() -> None:
    result = decision()
    first = explanation_for(result)
    second = explanation_for(result)

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.policy_version = "changed"
    with pytest.raises(TypeError, match="tuple"):
        replace(first, sections=list(first.sections))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(first, generated_at=datetime(2026, 8, 3, 12))


def test_service_does_not_mutate_decision_result_and_preserves_versions() -> None:
    result = decision()
    before = repr(result)
    value = DecisionExplanationService(
        explanation_version="decision-explanation-v1"
    ).explain(result)

    assert repr(result) == before
    assert value.generated_at == result.generated_at
    assert value.schema_version == result.schema_version
    assert value.policy_version == result.policy_version
    assert value.explanation_version == "decision-explanation-v1"
