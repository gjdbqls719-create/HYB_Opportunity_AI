from __future__ import annotations

from app.domain.decision_engine import (
    DecisionDimension,
    DecisionDimensionResult,
    DecisionEvidenceAvailability,
    DecisionInput,
    DecisionReasonCode,
)
from app.domain.market_intelligence import (
    CompetitionLevel,
    DemandLevel,
)
from app.domain.opportunity import ProductionSafetyStatus


def _metadata(decision_input: DecisionInput, dimension: DecisionDimension):
    return next(
        value
        for value in decision_input.evidence_metadata
        if value.dimension is dimension
    )


def _result(
    decision_input: DecisionInput,
    dimension: DecisionDimension,
    reason_codes: tuple[DecisionReasonCode, ...],
) -> DecisionDimensionResult:
    metadata = _metadata(decision_input, dimension)
    return DecisionDimensionResult(
        dimension=dimension,
        availability=metadata.availability,
        confidence=metadata.confidence,
        freshness=metadata.freshness,
        assessment_reference=None,
        reason_codes=reason_codes,
        generated_at=decision_input.generated_at,
        schema_version=decision_input.schema_version,
        policy_version=decision_input.policy_version,
    )


class EconomicsEvaluator:
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult:
        metadata = _metadata(decision_input, DecisionDimension.ECONOMICS)
        reason = (
            DecisionReasonCode.ECONOMICS_UNAVAILABLE
            if metadata.availability is DecisionEvidenceAvailability.UNAVAILABLE
            else DecisionReasonCode.ECONOMICS_READY
        )
        return _result(
            decision_input,
            DecisionDimension.ECONOMICS,
            (reason,),
        )


class SafetyEvaluator:
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult:
        reason = (
            DecisionReasonCode.SAFETY_READY
            if decision_input.production_safety.status is ProductionSafetyStatus.READY
            else DecisionReasonCode.SAFETY_BLOCKED
        )
        return _result(
            decision_input,
            DecisionDimension.SAFETY,
            (reason,),
        )


class CompetitionEvaluator:
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult:
        assessment = decision_input.competition_assessment
        if assessment is None:
            reasons = (DecisionReasonCode.COMPETITION_UNAVAILABLE,)
        elif assessment.competition_level in {
            CompetitionLevel.VERY_LOW,
            CompetitionLevel.LOW,
        }:
            reasons = (DecisionReasonCode.LOW_COMPETITION,)
        elif assessment.competition_level in {
            CompetitionLevel.HIGH,
            CompetitionLevel.VERY_HIGH,
        }:
            reasons = (DecisionReasonCode.HIGH_COMPETITION,)
        else:
            reasons = ()
        return _result(
            decision_input,
            DecisionDimension.COMPETITION,
            reasons,
        )


class DemandEvaluator:
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult:
        assessment = decision_input.demand_assessment
        metadata = _metadata(decision_input, DecisionDimension.DEMAND)
        if assessment is None:
            reasons = (DecisionReasonCode.DEMAND_UNAVAILABLE,)
        else:
            collected: list[DecisionReasonCode] = []
            if assessment.demand_level in {DemandLevel.HIGH, DemandLevel.VERY_HIGH}:
                collected.append(DecisionReasonCode.HIGH_DEMAND)
            elif assessment.demand_level in {DemandLevel.VERY_LOW, DemandLevel.LOW}:
                collected.append(DecisionReasonCode.LOW_DEMAND)
            if metadata.availability is DecisionEvidenceAvailability.PARTIAL:
                collected.append(DecisionReasonCode.DEMAND_PARTIAL)
            reasons = tuple(collected)
        return _result(
            decision_input,
            DecisionDimension.DEMAND,
            reasons,
        )


class ExternalEvaluator:
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult:
        reason = (
            DecisionReasonCode.EXTERNAL_SIGNAL_AGREES
            if decision_input.external_signals
            else DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE
        )
        return _result(
            decision_input,
            DecisionDimension.EXTERNAL_REFERENCE,
            (reason,),
        )
