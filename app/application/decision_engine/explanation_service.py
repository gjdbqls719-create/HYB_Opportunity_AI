from __future__ import annotations

from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceSummary,
    DecisionExplanation,
    DecisionExplanationItem,
    DecisionExplanationSection,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionResult,
    DecisionSummary,
    ExplanationCode,
    Severity,
)


_SUMMARY_RULES = {
    DecisionOutcome.INVEST: (
        ExplanationCode.INVEST_READY,
        "Investment conditions satisfy the current decision policy.",
    ),
    DecisionOutcome.REVIEW: (
        ExplanationCode.REVIEW_MORE_EVIDENCE,
        "Additional evidence is recommended.",
    ),
    DecisionOutcome.REJECT: (
        ExplanationCode.REJECT_SAFETY,
        "Safety policy blocks this opportunity.",
    ),
    DecisionOutcome.INSUFFICIENT_EVIDENCE: (
        ExplanationCode.INSUFFICIENT_VERIFIED_EVIDENCE,
        "Insufficient verified evidence is available.",
    ),
}

_SEVERITY_OVERRIDES = {
    DecisionReasonCode.ECONOMICS_READY: Severity.INFO,
    DecisionReasonCode.LOW_COMPETITION: Severity.INFO,
    DecisionReasonCode.HIGH_DEMAND: Severity.INFO,
    DecisionReasonCode.DEMAND_PARTIAL: Severity.WARNING,
    DecisionReasonCode.MARKET_STALE: Severity.WARNING,
    DecisionReasonCode.EXTERNAL_SIGNAL_UNAVAILABLE: Severity.WARNING,
    DecisionReasonCode.SAFETY_BLOCKED: Severity.CRITICAL,
}


class DecisionExplanationService:
    def __init__(self, *, explanation_version: str = "decision-explanation-v1") -> None:
        if not isinstance(explanation_version, str) or not explanation_version.strip():
            raise ValueError("explanation_version must be non-empty text")
        self._explanation_version = explanation_version.strip()

    def explain(self, decision_result: DecisionResult) -> DecisionExplanation:
        if not isinstance(decision_result, DecisionResult):
            raise TypeError("decision_result must be DecisionResult")
        result_by_dimension = {
            value.dimension: value for value in decision_result.dimension_results
        }
        reason_dimension = self._reason_dimensions(result_by_dimension)
        missing = tuple(
            dimension
            for dimension in DecisionDimension
            if dimension in decision_result.confidence.missing_dimensions
        )
        summary = self._summary(decision_result, reason_dimension, missing)
        sections = self._sections(
            decision_result,
            result_by_dimension,
            reason_dimension,
            missing,
        )
        evidence_summary = tuple(
            DecisionEvidenceSummary(
                dimension=dimension,
                availability=result_by_dimension[dimension].availability,
                confidence=result_by_dimension[dimension].confidence,
                freshness=result_by_dimension[dimension].freshness,
            )
            for dimension in DecisionDimension
        )
        return DecisionExplanation(
            summary=summary,
            sections=sections,
            evidence_summary=evidence_summary,
            missing_evidence=missing,
            generated_at=decision_result.generated_at,
            schema_version=decision_result.schema_version,
            policy_version=decision_result.policy_version,
            explanation_version=self._explanation_version,
        )

    @staticmethod
    def _reason_dimensions(result_by_dimension):
        mapping: dict[DecisionReasonCode, DecisionDimension] = {}
        for dimension in DecisionDimension:
            for reason in result_by_dimension[dimension].reason_codes:
                mapping.setdefault(reason, dimension)
        return mapping

    @staticmethod
    def _summary(
        decision_result: DecisionResult,
        reason_dimension: dict[DecisionReasonCode, DecisionDimension],
        missing: tuple[DecisionDimension, ...],
    ) -> DecisionSummary:
        summary_code, default_text = _SUMMARY_RULES[decision_result.outcome]
        supporting_dimensions = {
            reason_dimension[reason]
            for reason in decision_result.supporting_reasons
            if reason in reason_dimension
        }
        return DecisionSummary(
            outcome=decision_result.outcome,
            aggregate_confidence=decision_result.confidence.confidence,
            supporting_dimension_count=len(supporting_dimensions),
            missing_dimension_count=len(missing),
            summary_code=summary_code,
            default_text=default_text,
        )

    def _sections(
        self,
        decision_result: DecisionResult,
        result_by_dimension,
        reason_dimension: dict[DecisionReasonCode, DecisionDimension],
        missing: tuple[DecisionDimension, ...],
    ) -> tuple[DecisionExplanationSection, ...]:
        missing_set = set(missing)
        strengths = self._items(
            tuple(
                (reason, reason_dimension[reason], Severity.INFO)
                for reason in decision_result.supporting_reasons
                if reason in reason_dimension
                and reason_dimension[reason] not in missing_set
            )
        )
        warnings = self._items(
            tuple(
                (reason, reason_dimension[reason], self._severity(reason, fallback))
                for reasons, fallback in (
                    (decision_result.blocking_reasons, Severity.CRITICAL),
                    (decision_result.uncertainty_reasons, Severity.WARNING),
                )
                for reason in reasons
                if reason in reason_dimension
                and reason_dimension[reason] not in missing_set
            )
        )
        missing_items_data: list[
            tuple[DecisionReasonCode, DecisionDimension, Severity]
        ] = []
        for dimension in missing:
            reasons = result_by_dimension[dimension].reason_codes
            reason = reasons[0] if reasons else DecisionReasonCode.INSUFFICIENT_EVIDENCE
            missing_items_data.append((reason, dimension, Severity.WARNING))
        missing_items = self._items(tuple(missing_items_data))
        return (
            DecisionExplanationSection("Summary", 1, ()),
            DecisionExplanationSection("Strengths", 2, strengths),
            DecisionExplanationSection("Warnings", 3, warnings),
            DecisionExplanationSection("Missing Evidence", 4, missing_items),
        )

    @staticmethod
    def _severity(reason: DecisionReasonCode, fallback: Severity) -> Severity:
        return _SEVERITY_OVERRIDES.get(reason, fallback)

    @staticmethod
    def _items(
        values: tuple[
            tuple[DecisionReasonCode, DecisionDimension, Severity], ...
        ],
    ) -> tuple[DecisionExplanationItem, ...]:
        unique = tuple(dict.fromkeys(values))
        return tuple(
            DecisionExplanationItem(
                reason_code=reason,
                dimension=dimension,
                severity=severity,
                default_text=reason.value.replace("_", " ").capitalize() + ".",
                display_order=index,
            )
            for index, (reason, dimension, severity) in enumerate(unique, start=1)
        )
