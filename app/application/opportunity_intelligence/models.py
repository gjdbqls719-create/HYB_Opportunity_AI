from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.application.opportunity_intelligence.decision_report import (
    OpportunityDecisionReport,
)
from app.application.opportunity_intelligence.final_recommendation import (
    OpportunityRecommendation,
)
from app.application.opportunity_intelligence.trend_interpreter import (
    OpportunityTrendAssessment,
)
from app.domain.opportunity import (
    OpportunityEvaluation,
    OpportunityFactors,
    OpportunityScore,
)
from app.domain.trend import PriceTrendAnalysis
from app.engine.opportunity_confidence import OpportunityConfidenceAssessment
from app.engine.opportunity_risk import OpportunityRiskAssessment


_FACTOR_NAMES = (
    "price_score",
    "trend_score",
    "demand_score",
    "competition_score",
    "risk_score",
)


class OpportunityIntelligenceStatus(str, Enum):
    """Opportunity Intelligence 통합 실행 상태."""

    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OpportunityIntelligenceInput:
    """Adapter가 Application Service에 전달하는 정규화 입력."""

    factors: OpportunityFactors | None
    confidence: Decimal | None
    trend_analysis: PriceTrendAnalysis | None = None
    missing_factors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.factors is not None and not isinstance(self.factors, OpportunityFactors):
            raise TypeError("factors는 OpportunityFactors 또는 None이어야 합니다.")
        if self.confidence is not None and not isinstance(self.confidence, Decimal):
            raise TypeError("confidence는 Decimal 또는 None이어야 합니다.")
        if self.trend_analysis is not None and not isinstance(
            self.trend_analysis, PriceTrendAnalysis
        ):
            raise TypeError(
                "trend_analysis는 PriceTrendAnalysis 또는 None이어야 합니다."
            )
        if not isinstance(self.missing_factors, tuple):
            raise TypeError("missing_factors는 문자열 tuple이어야 합니다.")
        if len(set(self.missing_factors)) != len(self.missing_factors):
            raise ValueError("missing_factors에는 중복 값을 넣을 수 없습니다.")
        for name in self.missing_factors:
            if not isinstance(name, str):
                raise TypeError("missing_factors의 모든 값은 문자열이어야 합니다.")
            if name not in _FACTOR_NAMES:
                raise ValueError(f"알 수 없는 Factor 이름입니다: {name}")
        if self.factors is None and not self.missing_factors:
            raise ValueError("factors가 없으면 missing_factors를 최소 하나 지정해야 합니다.")
        if self.factors is not None and self.missing_factors:
            raise ValueError("완전한 factors와 missing_factors를 동시에 제공할 수 없습니다.")


@dataclass(frozen=True, slots=True)
class OpportunityIntelligenceResult:
    """Opportunity Intelligence Application Service의 안정적인 결과 계약."""

    status: OpportunityIntelligenceStatus
    score: OpportunityScore | None = None
    evaluation: OpportunityEvaluation | None = None
    decision_report: OpportunityDecisionReport | None = None
    confidence_assessment: OpportunityConfidenceAssessment | None = None
    risk_assessment: OpportunityRiskAssessment | None = None
    trend_assessment: OpportunityTrendAssessment | None = None
    recommendation: OpportunityRecommendation | None = None
    missing_factors: tuple[str, ...] = ()
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OpportunityIntelligenceStatus):
            raise TypeError("status는 OpportunityIntelligenceStatus여야 합니다.")
        if not isinstance(self.missing_factors, tuple):
            raise TypeError("missing_factors는 문자열 tuple이어야 합니다.")

        if self.status is OpportunityIntelligenceStatus.EVALUATED:
            if self.score is None or self.evaluation is None or self.decision_report is None:
                raise ValueError(
                    "evaluated 결과에는 score, evaluation, decision_report가 필요합니다."
                )
            if self.confidence_assessment is None or self.risk_assessment is None:
                raise ValueError(
                    "evaluated 결과에는 confidence_assessment와 risk_assessment가 필요합니다."
                )
            if (self.trend_assessment is None) != (self.recommendation is None):
                raise ValueError(
                    "trend_assessment와 recommendation은 함께 제공되어야 합니다."
                )
            if self.missing_factors:
                raise ValueError("evaluated 결과에는 missing_factors가 없어야 합니다.")
            if self.error_message is not None:
                raise ValueError("evaluated 결과에는 error_message가 없어야 합니다.")
            return

        enriched_fields = (
            self.score,
            self.evaluation,
            self.decision_report,
            self.confidence_assessment,
            self.risk_assessment,
            self.trend_assessment,
            self.recommendation,
        )
        if any(value is not None for value in enriched_fields):
            raise ValueError(
                "evaluated가 아닌 결과에는 평가 결과를 넣을 수 없습니다."
            )

        if self.status is OpportunityIntelligenceStatus.UNAVAILABLE:
            if not self.missing_factors:
                raise ValueError("unavailable 결과에는 missing_factors가 필요합니다.")
            if self.error_message is not None:
                raise ValueError("unavailable 결과에는 error_message가 없어야 합니다.")
            return

        if not self.error_message:
            raise ValueError("failed 결과에는 error_message가 필요합니다.")
        if self.missing_factors:
            raise ValueError("failed 결과에는 missing_factors가 없어야 합니다.")
