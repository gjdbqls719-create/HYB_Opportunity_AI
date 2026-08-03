from __future__ import annotations

from app.application.dashboard.models import (
    DashboardActionCard,
    DashboardEvidenceCard,
    DashboardReadModel,
    DashboardSummaryCard,
    DashboardWarningCard,
)
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionExplanation,
    DecisionOutcome,
    DecisionResult,
    Severity,
)


_PRIMARY_ACTIONS = {
    DecisionOutcome.INVEST: "Proceed to Validation",
    DecisionOutcome.REVIEW: "Collect More Evidence",
    DecisionOutcome.REJECT: "Do Not Proceed",
    DecisionOutcome.INSUFFICIENT_EVIDENCE: "Acquire Required Evidence",
}

_SEVERITY_PRIORITY = {
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 3,
}


class DashboardReadModelAssembler:
    def assemble(
        self,
        decision_result: DecisionResult,
        decision_explanation: DecisionExplanation,
    ) -> DashboardReadModel:
        if not isinstance(decision_result, DecisionResult):
            raise TypeError("decision_result must be DecisionResult")
        if not isinstance(decision_explanation, DecisionExplanation):
            raise TypeError("decision_explanation must be DecisionExplanation")
        self._validate_pair(decision_result, decision_explanation)

        summary = decision_explanation.summary
        summary_card = DashboardSummaryCard(summary=summary)
        action_card = DashboardActionCard(
            primary_action=_PRIMARY_ACTIONS[decision_result.outcome],
            secondary_action=None,
            outcome=decision_result.outcome,
        )
        explanation_items = tuple(
            item
            for section in decision_explanation.sections
            for item in section.items
        )
        warning_items = tuple(
            item
            for item in explanation_items
            if item.severity in {Severity.WARNING, Severity.CRITICAL}
        )
        warning_cards = tuple(
            DashboardWarningCard(item=item, display_order=index)
            for index, item in enumerate(warning_items, start=1)
        )
        result_by_dimension = {
            value.dimension: value for value in decision_result.dimension_results
        }
        evidence_cards = tuple(
            DashboardEvidenceCard(
                dimension_result=result_by_dimension[dimension],
                severity=self._dimension_severity(explanation_items, dimension),
                display_order=index,
            )
            for index, dimension in enumerate(DecisionDimension, start=1)
        )
        return DashboardReadModel(
            summary_card=summary_card,
            action_card=action_card,
            warning_cards=warning_cards,
            evidence_cards=evidence_cards,
            generated_at=decision_result.generated_at,
            schema_version=decision_result.schema_version,
            policy_version=decision_result.policy_version,
        )

    @staticmethod
    def _validate_pair(
        decision_result: DecisionResult,
        decision_explanation: DecisionExplanation,
    ) -> None:
        if decision_explanation.generated_at != decision_result.generated_at:
            raise ValueError("DecisionResult and DecisionExplanation generated_at must match")
        if decision_explanation.schema_version != decision_result.schema_version:
            raise ValueError("DecisionResult and DecisionExplanation schema_version must match")
        if decision_explanation.policy_version != decision_result.policy_version:
            raise ValueError("DecisionResult and DecisionExplanation policy_version must match")
        if decision_explanation.summary.outcome is not decision_result.outcome:
            raise ValueError("DecisionResult and DecisionExplanation outcomes must match")
        if (
            decision_explanation.summary.aggregate_confidence
            != decision_result.confidence.confidence
        ):
            raise ValueError("DecisionResult and DecisionExplanation confidence must match")
        result_by_dimension = {
            value.dimension: value for value in decision_result.dimension_results
        }
        for evidence in decision_explanation.evidence_summary:
            result = result_by_dimension[evidence.dimension]
            if (
                evidence.availability is not result.availability
                or evidence.confidence != result.confidence
                or evidence.freshness is not result.freshness
            ):
                raise ValueError(
                    "DecisionResult and DecisionExplanation evidence must match"
                )

    @staticmethod
    def _dimension_severity(items, dimension: DecisionDimension) -> Severity | None:
        severities = tuple(
            item.severity for item in items if item.dimension is dimension
        )
        if not severities:
            return None
        return max(severities, key=_SEVERITY_PRIORITY.__getitem__)
