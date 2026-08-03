from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.domain.decision_engine import (
    DecisionConfidence,
    DecisionDimension,
    DecisionDimensionResult,
    DecisionEvidenceAvailability,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionResult,
    OpportunityIdentity,
)


class DecisionPolicy(Protocol):
    def evaluate(
        self,
        dimension_results: tuple[DecisionDimensionResult, ...],
    ) -> DecisionResult: ...


_SUPPORTING_REASONS = frozenset({
    DecisionReasonCode.ECONOMICS_READY,
    DecisionReasonCode.SAFETY_READY,
    DecisionReasonCode.LOW_COMPETITION,
    DecisionReasonCode.HIGH_DEMAND,
    DecisionReasonCode.EXTERNAL_SIGNAL_AGREES,
})

_BLOCKING_REASONS = frozenset({DecisionReasonCode.SAFETY_BLOCKED})

_UNCERTAINTY_REASONS = frozenset(DecisionReasonCode).difference(
    _SUPPORTING_REASONS,
    _BLOCKING_REASONS,
)


class DefaultDecisionPolicy:
    """Combine dimension facts without recalculating any dimension."""

    def __init__(self, opportunity_identity: OpportunityIdentity) -> None:
        if not isinstance(opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        self._opportunity_identity = opportunity_identity

    def evaluate(
        self,
        dimension_results: tuple[DecisionDimensionResult, ...],
    ) -> DecisionResult:
        by_dimension = self._validate_results(dimension_results)
        outcome = self._outcome(by_dimension)
        confidence = self._aggregate_confidence(dimension_results)
        blocking, supporting, uncertainty = self._resolve_reasons(
            dimension_results
        )
        reference = dimension_results[0]
        return DecisionResult(
            opportunity_identity=self._opportunity_identity,
            outcome=outcome,
            confidence=confidence,
            dimension_results=dimension_results,
            blocking_reasons=blocking,
            supporting_reasons=supporting,
            uncertainty_reasons=uncertainty,
            generated_at=reference.generated_at,
            schema_version=reference.schema_version,
            policy_version=reference.policy_version,
        )

    @staticmethod
    def _validate_results(
        dimension_results: tuple[DecisionDimensionResult, ...],
    ) -> dict[DecisionDimension, DecisionDimensionResult]:
        if not isinstance(dimension_results, tuple):
            raise TypeError("dimension_results must be a tuple")
        if any(
            not isinstance(value, DecisionDimensionResult)
            for value in dimension_results
        ):
            raise TypeError(
                "dimension_results must contain DecisionDimensionResult values"
            )
        by_dimension = {value.dimension: value for value in dimension_results}
        if len(by_dimension) != len(dimension_results):
            raise ValueError("dimension_results cannot contain duplicate dimensions")
        if set(by_dimension) != set(DecisionDimension):
            raise ValueError("dimension_results must cover every decision dimension")
        reference = dimension_results[0]
        for value in dimension_results[1:]:
            if value.generated_at != reference.generated_at:
                raise ValueError("dimension_results must share generated_at")
            if value.schema_version != reference.schema_version:
                raise ValueError("dimension_results must share schema_version")
            if value.policy_version != reference.policy_version:
                raise ValueError("dimension_results must share policy_version")
        return by_dimension

    @staticmethod
    def _outcome(
        by_dimension: dict[DecisionDimension, DecisionDimensionResult],
    ) -> DecisionOutcome:
        economics = by_dimension[DecisionDimension.ECONOMICS]
        safety = by_dimension[DecisionDimension.SAFETY]
        competition = by_dimension[DecisionDimension.COMPETITION]
        demand = by_dimension[DecisionDimension.DEMAND]

        if economics.availability is DecisionEvidenceAvailability.UNAVAILABLE:
            return DecisionOutcome.INSUFFICIENT_EVIDENCE
        if DecisionReasonCode.SAFETY_BLOCKED in safety.reason_codes:
            return DecisionOutcome.REJECT
        if (
            DecisionReasonCode.HIGH_COMPETITION in competition.reason_codes
            and DecisionReasonCode.LOW_DEMAND in demand.reason_codes
        ):
            return DecisionOutcome.REVIEW
        if (
            DecisionReasonCode.LOW_COMPETITION in competition.reason_codes
            and DecisionReasonCode.HIGH_DEMAND in demand.reason_codes
            and DecisionReasonCode.ECONOMICS_READY in economics.reason_codes
            and DecisionReasonCode.SAFETY_READY in safety.reason_codes
        ):
            return DecisionOutcome.INVEST
        return DecisionOutcome.REVIEW

    @staticmethod
    def _aggregate_confidence(
        dimension_results: tuple[DecisionDimensionResult, ...],
    ) -> DecisionConfidence:
        available = tuple(
            value
            for value in dimension_results
            if value.availability is not DecisionEvidenceAvailability.UNAVAILABLE
            and value.confidence is not None
        )
        missing = tuple(
            value.dimension
            for value in dimension_results
            if value.availability is DecisionEvidenceAvailability.UNAVAILABLE
        )
        confidence = (
            sum((value.confidence for value in available), Decimal("0"))
            / Decimal(len(available))
            if available
            else Decimal("0")
        )
        missing_set = set(missing)
        core_dimensions = {
            DecisionDimension.ECONOMICS,
            DecisionDimension.SAFETY,
            DecisionDimension.COMPETITION,
            DecisionDimension.DEMAND,
        }
        if not missing:
            availability = DecisionEvidenceAvailability.COMPLETE
        elif core_dimensions.issubset(missing_set):
            availability = DecisionEvidenceAvailability.UNAVAILABLE
        else:
            availability = DecisionEvidenceAvailability.PARTIAL
        return DecisionConfidence(
            confidence=confidence,
            availability=availability,
            missing_dimensions=missing,
        )

    @staticmethod
    def _resolve_reasons(
        dimension_results: tuple[DecisionDimensionResult, ...],
    ) -> tuple[
        tuple[DecisionReasonCode, ...],
        tuple[DecisionReasonCode, ...],
        tuple[DecisionReasonCode, ...],
    ]:
        reasons = tuple(dict.fromkeys(
            reason
            for result in dimension_results
            for reason in result.reason_codes
        ))
        blocking = tuple(reason for reason in reasons if reason in _BLOCKING_REASONS)
        supporting = tuple(reason for reason in reasons if reason in _SUPPORTING_REASONS)
        uncertainty = tuple(reason for reason in reasons if reason in _UNCERTAINTY_REASONS)
        return blocking, supporting, uncertainty
