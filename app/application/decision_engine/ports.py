from __future__ import annotations

from typing import Protocol

from app.domain.decision_engine import DecisionDimensionResult, DecisionInput


class DecisionDimensionEvaluator(Protocol):
    def evaluate(self, decision_input: DecisionInput) -> DecisionDimensionResult: ...
