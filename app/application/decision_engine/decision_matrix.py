from __future__ import annotations

from collections.abc import Callable

from app.application.decision_engine.models import EvaluateDecisionDimensionsRequest
from app.application.decision_engine.policy import (
    DecisionPolicy,
    DefaultDecisionPolicy,
)
from app.application.decision_engine.service import DecisionEvaluationService
from app.domain.decision_engine import (
    DecisionInput,
    DecisionResult,
    OpportunityIdentity,
)


PolicyFactory = Callable[[OpportunityIdentity], DecisionPolicy]


class DecisionMatrix:
    def __init__(
        self,
        *,
        evaluation_service: DecisionEvaluationService | None = None,
        policy_factory: PolicyFactory | None = None,
    ) -> None:
        self._evaluation_service = evaluation_service or DecisionEvaluationService()
        self._policy_factory = policy_factory or DefaultDecisionPolicy

    def evaluate(self, decision_input: DecisionInput) -> DecisionResult:
        if not isinstance(decision_input, DecisionInput):
            raise TypeError("decision_input must be DecisionInput")
        response = self._evaluation_service.evaluate(
            EvaluateDecisionDimensionsRequest(decision_input)
        )
        policy = self._policy_factory(decision_input.opportunity_identity)
        return policy.evaluate(response.dimension_results)
