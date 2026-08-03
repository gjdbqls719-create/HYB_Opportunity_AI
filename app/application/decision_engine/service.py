from __future__ import annotations

from app.application.decision_engine.models import (
    EvaluateDecisionDimensionsRequest,
    EvaluateDecisionDimensionsResponse,
)
from app.application.decision_engine.ports import DecisionDimensionEvaluator
from app.application.decision_engine.use_cases import (
    CompetitionEvaluator,
    DemandEvaluator,
    EconomicsEvaluator,
    ExternalEvaluator,
    SafetyEvaluator,
)
from app.domain.decision_engine import DecisionDimension


class DecisionEvaluationService:
    def __init__(
        self,
        *,
        economics_evaluator: DecisionDimensionEvaluator | None = None,
        safety_evaluator: DecisionDimensionEvaluator | None = None,
        competition_evaluator: DecisionDimensionEvaluator | None = None,
        demand_evaluator: DecisionDimensionEvaluator | None = None,
        external_evaluator: DecisionDimensionEvaluator | None = None,
    ) -> None:
        self._evaluators = (
            economics_evaluator or EconomicsEvaluator(),
            safety_evaluator or SafetyEvaluator(),
            competition_evaluator or CompetitionEvaluator(),
            demand_evaluator or DemandEvaluator(),
            external_evaluator or ExternalEvaluator(),
        )

    def evaluate(
        self,
        request: EvaluateDecisionDimensionsRequest,
    ) -> EvaluateDecisionDimensionsResponse:
        if not isinstance(request, EvaluateDecisionDimensionsRequest):
            raise TypeError("request must be EvaluateDecisionDimensionsRequest")
        results = tuple(
            evaluator.evaluate(request.decision_input)
            for evaluator in self._evaluators
        )
        if tuple(result.dimension for result in results) != tuple(DecisionDimension):
            raise ValueError(
                "dimension evaluators must return every decision dimension in order"
            )
        return EvaluateDecisionDimensionsResponse(dimension_results=results)
