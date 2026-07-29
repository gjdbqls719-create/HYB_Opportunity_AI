from __future__ import annotations

from app.application.opportunity_intelligence.decision_report import (
    OpportunityDecisionReportBuilder,
)
from app.application.opportunity_intelligence.final_recommendation import (
    OpportunityRecommendationEngine,
)
from app.application.opportunity_intelligence.trend_interpreter import (
    OpportunityTrendInterpreter,
)
from app.application.opportunity_intelligence.models import (
    OpportunityIntelligenceResult,
    OpportunityIntelligenceStatus,
)
from app.application.opportunity_intelligence.ports import (
    OpportunityIntelligenceInputAdapter,
)
from app.domain.discovery import DiscoveryResult
from app.engine import (
    OpportunityConfidenceEngine,
    OpportunityDecisionEngine,
    OpportunityRiskEngine,
    OpportunityScoreEngine,
)


class OpportunityIntelligenceService:
    """입력 준비 상태를 확인하고 Score, Evaluation, Report 생성을 조율한다."""

    def __init__(
        self,
        *,
        input_adapter: OpportunityIntelligenceInputAdapter,
        score_engine: OpportunityScoreEngine | None = None,
        decision_engine: OpportunityDecisionEngine | None = None,
        report_builder: OpportunityDecisionReportBuilder | None = None,
        confidence_engine: OpportunityConfidenceEngine | None = None,
        risk_engine: OpportunityRiskEngine | None = None,
        trend_interpreter: OpportunityTrendInterpreter | None = None,
        recommendation_engine: OpportunityRecommendationEngine | None = None,
    ) -> None:
        self._input_adapter = input_adapter
        self._score_engine = score_engine or OpportunityScoreEngine()
        self._decision_engine = decision_engine or OpportunityDecisionEngine()
        self._report_builder = report_builder or OpportunityDecisionReportBuilder()
        self._confidence_engine = confidence_engine or OpportunityConfidenceEngine()
        self._risk_engine = risk_engine or OpportunityRiskEngine()
        self._trend_interpreter = trend_interpreter or OpportunityTrendInterpreter()
        self._recommendation_engine = (
            recommendation_engine or OpportunityRecommendationEngine()
        )

    def evaluate(self, discovery_result: DiscoveryResult) -> OpportunityIntelligenceResult:
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
            decision_report = self._report_builder.build(evaluation)
            confidence_assessment = self._confidence_engine.assess(
                prepared.confidence
            )
            risk_assessment = self._risk_engine.assess(
                score.factors.risk_score
            )

            trend_assessment = None
            recommendation = None
            if prepared.trend_analysis is not None:
                trend_assessment = self._trend_interpreter.interpret(
                    prepared.trend_analysis
                )
                recommendation = self._recommendation_engine.recommend(
                    decision_report=decision_report,
                    confidence=confidence_assessment,
                    risk=risk_assessment,
                    trend=trend_assessment,
                )
        except (TypeError, ValueError) as error:
            return OpportunityIntelligenceResult(
                status=OpportunityIntelligenceStatus.FAILED,
                error_message=str(error),
            )

        return OpportunityIntelligenceResult(
            status=OpportunityIntelligenceStatus.EVALUATED,
            score=score,
            evaluation=evaluation,
            decision_report=decision_report,
            confidence_assessment=confidence_assessment,
            risk_assessment=risk_assessment,
            trend_assessment=trend_assessment,
            recommendation=recommendation,
        )
