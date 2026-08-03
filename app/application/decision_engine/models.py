from __future__ import annotations

from dataclasses import dataclass

from app.domain.decision_engine import DecisionDimensionResult, DecisionInput


@dataclass(frozen=True, slots=True)
class EvaluateDecisionDimensionsRequest:
    decision_input: DecisionInput

    def __post_init__(self) -> None:
        if not isinstance(self.decision_input, DecisionInput):
            raise TypeError("decision_input must be DecisionInput")


@dataclass(frozen=True, slots=True)
class EvaluateDecisionDimensionsResponse:
    dimension_results: tuple[DecisionDimensionResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dimension_results, tuple):
            raise TypeError("dimension_results must be a tuple")
        if any(
            not isinstance(value, DecisionDimensionResult)
            for value in self.dimension_results
        ):
            raise TypeError(
                "dimension_results must contain DecisionDimensionResult values"
            )
