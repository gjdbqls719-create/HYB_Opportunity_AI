from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.opportunity_intelligence import (
    OpportunityDecisionReportBuilder,
    OpportunityRecommendation,
    OpportunityRecommendationEngine,
    OpportunityRecommendationLevel,
    OpportunityTrendAssessment,
    OpportunityTrendLevel,
)
from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityEvaluation,
    OpportunityFactors,
    OpportunityGrade,
    OpportunityReason,
    OpportunityScore,
)
from app.engine import (
    OpportunityConfidenceEngine,
    OpportunityRiskEngine,
)


def make_report(
    decision: OpportunityDecision,
    *,
    reasons: tuple[OpportunityReason, ...] = (OpportunityReason.PRICE_ADVANTAGE,),
) -> object:
    score = OpportunityScore(
        score=Decimal("92"),
        grade=OpportunityGrade.EXCELLENT,
        confidence=Decimal("95"),
        factors=OpportunityFactors(
            price_score=Decimal("90"),
            trend_score=Decimal("90"),
            demand_score=Decimal("90"),
            competition_score=Decimal("90"),
            risk_score=Decimal("90"),
        ),
        generated_at=datetime.now(timezone.utc),
    )
    evaluation = OpportunityEvaluation(
        score=score,
        decision=decision,
        reasons=reasons,
        evaluated_at=datetime.now(timezone.utc),
    )
    return OpportunityDecisionReportBuilder().build(evaluation)


def make_trend(
    level: OpportunityTrendLevel,
    *,
    favorable: bool,
    requires_caution: bool,
) -> OpportunityTrendAssessment:
    return OpportunityTrendAssessment(
        level=level,
        summary=f"{level.value} 추세입니다.",
        recommended_action="가격 추세를 확인하세요.",
        favorable=favorable,
        requires_caution=requires_caution,
    )


def recommend(
    *,
    decision: OpportunityDecision = OpportunityDecision.STRONG_BUY,
    confidence_score: str = "95",
    safety_score: str = "90",
    trend_level: OpportunityTrendLevel = OpportunityTrendLevel.STRONG_BUY_TREND,
    trend_favorable: bool = True,
    trend_caution: bool = False,
):
    return OpportunityRecommendationEngine().recommend(
        decision_report=make_report(decision),
        confidence=OpportunityConfidenceEngine().assess(Decimal(confidence_score)),
        risk=OpportunityRiskEngine().assess(Decimal(safety_score)),
        trend=make_trend(
            trend_level,
            favorable=trend_favorable,
            requires_caution=trend_caution,
        ),
    )


def test_strong_buy_requires_all_strong_supporting_signals() -> None:
    result = recommend()

    assert result.level is OpportunityRecommendationLevel.STRONG_BUY
    assert result.strengths
    assert not result.warnings


def test_high_risk_overrides_positive_decision_and_trend() -> None:
    result = recommend(safety_score="20")

    assert result.level is OpportunityRecommendationLevel.AVOID
    assert result.warnings


def test_skip_decision_becomes_pass() -> None:
    result = recommend(decision=OpportunityDecision.SKIP)

    assert result.level is OpportunityRecommendationLevel.PASS


def test_high_risk_trend_caps_recommendation_at_pass() -> None:
    result = recommend(
        trend_level=OpportunityTrendLevel.HIGH_RISK_TREND,
        trend_favorable=False,
        trend_caution=True,
    )

    assert result.level is OpportunityRecommendationLevel.PASS


def test_low_confidence_caps_recommendation_at_watch() -> None:
    result = recommend(confidence_score="20")

    assert result.level is OpportunityRecommendationLevel.WATCH
    assert result.warnings


def test_medium_risk_caps_recommendation_at_watch() -> None:
    result = recommend(safety_score="55")

    assert result.level is OpportunityRecommendationLevel.WATCH


def test_buy_decision_remains_buy_with_supporting_signals() -> None:
    result = recommend(decision=OpportunityDecision.BUY, confidence_score="75")

    assert result.level is OpportunityRecommendationLevel.BUY


def test_strong_buy_decision_is_downgraded_without_very_high_confidence() -> None:
    result = recommend(confidence_score="75")

    assert result.level is OpportunityRecommendationLevel.BUY


def test_result_requires_at_least_one_reason() -> None:
    with pytest.raises(ValueError):
        OpportunityRecommendation(
            level=OpportunityRecommendationLevel.WATCH,
            summary="관찰이 필요합니다.",
            reasons=(),
            strengths=(),
            warnings=(),
            next_action="추가 데이터를 확인하세요.",
        )


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("decision_report", object(), "decision_report"),
        ("confidence", object(), "confidence"),
        ("risk", object(), "risk"),
        ("trend", object(), "trend"),
    ],
)
def test_rejects_invalid_input_types(
    field_name: str,
    value: object,
    message: str,
) -> None:
    arguments = {
        "decision_report": make_report(OpportunityDecision.BUY),
        "confidence": OpportunityConfidenceEngine().assess(Decimal("80")),
        "risk": OpportunityRiskEngine().assess(Decimal("80")),
        "trend": make_trend(
            OpportunityTrendLevel.FAVORABLE_TREND,
            favorable=True,
            requires_caution=False,
        ),
    }
    arguments[field_name] = value

    with pytest.raises(TypeError, match=message):
        OpportunityRecommendationEngine().recommend(**arguments)
