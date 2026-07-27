from __future__ import annotations

from app.application.opportunity_intelligence.models import (
    OpportunityIntelligenceResult,
    OpportunityIntelligenceStatus,
)
from app.application.opportunity_intelligence.ports import (
    OpportunityIntelligenceInputAdapter,
)
from app.domain.discovery import DiscoveryResult
from app.engine import OpportunityDecisionEngine, OpportunityScoreEngine


class OpportunityIntelligenceService:
    """입력 준비 상태를 확인하고 Score와 Evaluation 생성을 조율한다."""

    def __init__(
        self,
        *,
        input_adapter: OpportunityIntelligenceInputAdapter,
        score_engine: OpportunityScoreEngine | None = None,
        decision_engine: OpportunityDecisionEngine | None = None,
    ) -> None:
        self._input_adapter = input_adapter
        self._score_engine = score_engine or OpportunityScoreEngine()
        self._decision_engine = decision_engine or OpportunityDecisionEngine()

    def evaluate(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceResult:
        if not isinstance(discovery_result, DiscoveryResult):
            raise TypeError("discovery_result는 DiscoveryResult여야 합니다.")

        try:
            prepared = self._input_adapter.adapt(discovery_result)

            if prepared.factors is None:
                return OpportunityIntelligenceResult(
                    status=OpportunityIntelligenceStatus.UNAVAILABLE,
                    missing_factors=prepared.missing_factors,
                )

            if prepared.confidence is None:
                return OpportunityIntelligenceResult(
                    status=OpportunityIntelligenceStatus.FAILED,
                    error_message="confidence를 준비할 수 없습니다.",
                )

            score = self._score_engine.calculate(
                prepared.factors,
                confidence=prepared.confidence,
            )
            evaluation = self._decision_engine.evaluate(score)
        except (TypeError, ValueError) as error:
            return OpportunityIntelligenceResult(
                status=OpportunityIntelligenceStatus.FAILED,
                error_message=str(error),
            )

        return OpportunityIntelligenceResult(
            status=OpportunityIntelligenceStatus.EVALUATED,
            score=score,
            evaluation=evaluation,
        )
