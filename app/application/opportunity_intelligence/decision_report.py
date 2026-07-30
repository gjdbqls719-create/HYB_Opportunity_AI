from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityEvaluation,
    OpportunityGrade,
    OpportunityReason,
)

_POSITIVE_REASONS = frozenset({
    OpportunityReason.PRICE_ADVANTAGE,
    OpportunityReason.UPWARD_TREND,
    OpportunityReason.HIGH_DEMAND,
    OpportunityReason.LOW_COMPETITION,
    OpportunityReason.LOW_RISK,
})

_NEGATIVE_REASONS = frozenset({
    OpportunityReason.PRICE_DISADVANTAGE,
    OpportunityReason.DOWNWARD_TREND,
    OpportunityReason.LOW_DEMAND,
    OpportunityReason.HIGH_COMPETITION,
    OpportunityReason.HIGH_RISK,
})

_RECOMMENDED_ACTIONS = {
    OpportunityDecision.STRONG_BUY: "우선 검토 후 적극적인 매입을 준비하세요.",
    OpportunityDecision.BUY: "수익성과 운영 조건을 확인한 뒤 매입을 검토하세요.",
    OpportunityDecision.WATCH: "즉시 매입하지 말고 가격과 시장 변화를 관찰하세요.",
    OpportunityDecision.SKIP: "현재 조건에서는 매입을 보류하세요.",
}


@dataclass(frozen=True, slots=True)
class OpportunityDecisionReport:
    """Opportunity 평가 결과를 전달 계층에서 재사용할 수 있는 표준 보고서."""

    decision: OpportunityDecision
    score: Decimal
    grade: OpportunityGrade
    confidence: Decimal
    reasons: tuple[OpportunityReason, ...]
    strengths: tuple[OpportunityReason, ...]
    warnings: tuple[OpportunityReason, ...]
    recommended_action: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, OpportunityDecision):
            raise TypeError("decision은 OpportunityDecision이어야 합니다.")
        if not isinstance(self.score, Decimal):
            raise TypeError("score는 Decimal이어야 합니다.")
        if not isinstance(self.grade, OpportunityGrade):
            raise TypeError("grade는 OpportunityGrade여야 합니다.")
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence는 Decimal이어야 합니다.")
        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons는 OpportunityReason의 tuple이어야 합니다.")
        if not isinstance(self.strengths, tuple):
            raise TypeError("strengths는 OpportunityReason의 tuple이어야 합니다.")
        if not isinstance(self.warnings, tuple):
            raise TypeError("warnings는 OpportunityReason의 tuple이어야 합니다.")
        if not self.recommended_action.strip():
            raise ValueError("recommended_action은 비어 있을 수 없습니다.")


class OpportunityDecisionReportBuilder:
    """도메인 평가 결과를 Application DTO로 변환한다."""

    def build(self, evaluation: OpportunityEvaluation) -> OpportunityDecisionReport:
        if not isinstance(evaluation, OpportunityEvaluation):
            raise TypeError("evaluation은 OpportunityEvaluation이어야 합니다.")

        reasons = evaluation.reasons
        strengths = tuple(reason for reason in reasons if reason in _POSITIVE_REASONS)
        warnings = tuple(reason for reason in reasons if reason in _NEGATIVE_REASONS)

        return OpportunityDecisionReport(
            decision=evaluation.decision,
            score=evaluation.score.score,
            grade=evaluation.score.grade,
            confidence=evaluation.score.confidence,
            reasons=reasons,
            strengths=strengths,
            warnings=warnings,
            recommended_action=_RECOMMENDED_ACTIONS[evaluation.decision],
        )
