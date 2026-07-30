from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.opportunity_intelligence.decision_report import (
    OpportunityDecisionReport,
)
from app.application.opportunity_intelligence.trend_interpreter import (
    OpportunityTrendAssessment,
    OpportunityTrendLevel,
)
from app.domain.opportunity import OpportunityDecision
from app.engine.opportunity_confidence import (
    OpportunityConfidenceAssessment,
    OpportunityConfidenceLevel,
)
from app.engine.opportunity_risk import (
    OpportunityRiskAssessment,
    OpportunityRiskLevel,
)


class OpportunityRecommendationLevel(StrEnum):
    """모든 Opportunity 판단 결과를 종합한 최종 추천 단계."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WATCH = "watch"
    PASS = "pass"
    AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class OpportunityRecommendation:
    """Opportunity Intelligence가 전달하는 최종 투자 추천 결과."""

    level: OpportunityRecommendationLevel
    summary: str
    reasons: tuple[str, ...]
    strengths: tuple[str, ...]
    warnings: tuple[str, ...]
    next_action: str

    def __post_init__(self) -> None:
        if not isinstance(self.level, OpportunityRecommendationLevel):
            raise TypeError("level은 OpportunityRecommendationLevel이어야 합니다.")

        for field_name in ("summary", "next_action"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name}은 문자열이어야 합니다.")
            if not value.strip():
                raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")

        for field_name in ("reasons", "strengths", "warnings"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name}은 문자열 tuple이어야 합니다.")
            if any(not isinstance(item, str) for item in value):
                raise TypeError(f"{field_name}의 모든 항목은 문자열이어야 합니다.")
            if any(not item.strip() for item in value):
                raise ValueError(f"{field_name}에는 빈 문자열을 넣을 수 없습니다.")

        if not self.reasons:
            raise ValueError("reasons는 최소 한 개 이상이어야 합니다.")


class OpportunityRecommendationEngine:
    """독립 평가 결과를 보수적인 최종 투자 추천으로 종합한다."""

    def recommend(
        self,
        *,
        decision_report: OpportunityDecisionReport,
        confidence: OpportunityConfidenceAssessment,
        risk: OpportunityRiskAssessment,
        trend: OpportunityTrendAssessment,
    ) -> OpportunityRecommendation:
        self._validate_inputs(
            decision_report=decision_report,
            confidence=confidence,
            risk=risk,
            trend=trend,
        )

        level = self._determine_level(
            decision_report=decision_report,
            confidence=confidence,
            risk=risk,
            trend=trend,
        )
        strengths = self._build_strengths(
            decision_report=decision_report,
            confidence=confidence,
            risk=risk,
            trend=trend,
        )
        warnings = self._build_warnings(
            decision_report=decision_report,
            confidence=confidence,
            risk=risk,
            trend=trend,
        )
        reasons = self._build_reasons(
            decision_report=decision_report,
            confidence=confidence,
            risk=risk,
            trend=trend,
        )

        summary, next_action = self._recommendation_text(level)

        return OpportunityRecommendation(
            level=level,
            summary=summary,
            reasons=reasons,
            strengths=strengths,
            warnings=warnings,
            next_action=next_action,
        )

    @staticmethod
    def _validate_inputs(
        *,
        decision_report: object,
        confidence: object,
        risk: object,
        trend: object,
    ) -> None:
        if not isinstance(decision_report, OpportunityDecisionReport):
            raise TypeError("decision_report는 OpportunityDecisionReport여야 합니다.")
        if not isinstance(confidence, OpportunityConfidenceAssessment):
            raise TypeError("confidence는 OpportunityConfidenceAssessment여야 합니다.")
        if not isinstance(risk, OpportunityRiskAssessment):
            raise TypeError("risk는 OpportunityRiskAssessment여야 합니다.")
        if not isinstance(trend, OpportunityTrendAssessment):
            raise TypeError("trend는 OpportunityTrendAssessment여야 합니다.")

    @staticmethod
    def _determine_level(
        *,
        decision_report: OpportunityDecisionReport,
        confidence: OpportunityConfidenceAssessment,
        risk: OpportunityRiskAssessment,
        trend: OpportunityTrendAssessment,
    ) -> OpportunityRecommendationLevel:
        if risk.level is OpportunityRiskLevel.HIGH:
            return OpportunityRecommendationLevel.AVOID

        if decision_report.decision is OpportunityDecision.SKIP:
            return OpportunityRecommendationLevel.PASS

        if trend.level is OpportunityTrendLevel.HIGH_RISK_TREND:
            return OpportunityRecommendationLevel.PASS

        if confidence.level is OpportunityConfidenceLevel.LOW:
            return OpportunityRecommendationLevel.WATCH

        if (
            risk.level is OpportunityRiskLevel.MEDIUM
            or trend.requires_caution
        ):
            return OpportunityRecommendationLevel.WATCH

        if decision_report.decision is OpportunityDecision.WATCH:
            return OpportunityRecommendationLevel.WATCH

        if decision_report.decision is OpportunityDecision.BUY:
            if confidence.level in {
                OpportunityConfidenceLevel.HIGH,
                OpportunityConfidenceLevel.VERY_HIGH,
            } and trend.favorable:
                return OpportunityRecommendationLevel.BUY
            return OpportunityRecommendationLevel.WATCH

        if (
            confidence.level is OpportunityConfidenceLevel.VERY_HIGH
            and trend.level is OpportunityTrendLevel.STRONG_BUY_TREND
        ):
            return OpportunityRecommendationLevel.STRONG_BUY

        return OpportunityRecommendationLevel.BUY

    @staticmethod
    def _build_reasons(
        *,
        decision_report: OpportunityDecisionReport,
        confidence: OpportunityConfidenceAssessment,
        risk: OpportunityRiskAssessment,
        trend: OpportunityTrendAssessment,
    ) -> tuple[str, ...]:
        domain_reasons = tuple(reason.value for reason in decision_report.reasons)
        return domain_reasons + (
            confidence.reason,
            risk.reason,
            trend.summary,
        )

    @staticmethod
    def _build_strengths(
        *,
        decision_report: OpportunityDecisionReport,
        confidence: OpportunityConfidenceAssessment,
        risk: OpportunityRiskAssessment,
        trend: OpportunityTrendAssessment,
    ) -> tuple[str, ...]:
        strengths = [reason.value for reason in decision_report.strengths]

        if confidence.level in {
            OpportunityConfidenceLevel.HIGH,
            OpportunityConfidenceLevel.VERY_HIGH,
        }:
            strengths.append(confidence.reason)
        if risk.level is OpportunityRiskLevel.LOW:
            strengths.append(risk.reason)
        if trend.favorable:
            strengths.append(trend.summary)

        return tuple(strengths)

    @staticmethod
    def _build_warnings(
        *,
        decision_report: OpportunityDecisionReport,
        confidence: OpportunityConfidenceAssessment,
        risk: OpportunityRiskAssessment,
        trend: OpportunityTrendAssessment,
    ) -> tuple[str, ...]:
        warnings = [reason.value for reason in decision_report.warnings]

        if confidence.level is OpportunityConfidenceLevel.LOW:
            warnings.append(confidence.reason)
        if risk.requires_caution:
            warnings.append(risk.reason)
        if trend.requires_caution:
            warnings.append(trend.summary)

        return tuple(warnings)

    @staticmethod
    def _recommendation_text(
        level: OpportunityRecommendationLevel,
    ) -> tuple[str, str]:
        recommendations = {
            OpportunityRecommendationLevel.STRONG_BUY: (
                "점수, 신뢰도, 위험도와 가격 추세가 모두 강한 매입 기회를 지지합니다.",
                "운영 조건과 실제 매입 가능 수량을 확인한 뒤 우선 매입 후보로 진행하세요.",
            ),
            OpportunityRecommendationLevel.BUY: (
                "핵심 판단 지표가 전반적으로 매입 검토에 우호적입니다.",
                "예상 수익과 판매 운영 조건을 최종 확인한 뒤 매입을 검토하세요.",
            ),
            OpportunityRecommendationLevel.WATCH: (
                "일부 긍정 요소가 있으나 현재 정보만으로 즉시 매입을 권하기 어렵습니다.",
                "부족하거나 불안정한 지표를 추가 관측한 뒤 다시 평가하세요.",
            ),
            OpportunityRecommendationLevel.PASS: (
                "현재 기회는 핵심 판단 또는 가격 추세 조건을 충족하지 못했습니다.",
                "이번 매입은 보류하고 조건이 개선될 때 다시 검토하세요.",
            ),
            OpportunityRecommendationLevel.AVOID: (
                "현재 위험 수준이 높아 다른 긍정 요소보다 손실 가능성을 우선해야 합니다.",
                "현재 조건에서는 매입하지 말고 위험 요인이 해소될 때까지 제외하세요.",
            ),
        }
        return recommendations[level]
