from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.application.opportunity_intelligence import (
    OpportunityDecisionReportBuilder,
    OpportunityIntelligenceInput,
    OpportunityIntelligenceService,
    OpportunityIntelligenceStatus,
)
from app.domain.discovery import DiscoveryResult
from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityEvaluation,
    OpportunityFactors,
    OpportunityGrade,
    OpportunityReason,
    OpportunityScore,
)
from app.models import Product


def make_score() -> OpportunityScore:
    return OpportunityScore(
        score=Decimal("82.50"),
        grade=OpportunityGrade.GOOD,
        confidence=Decimal("88"),
        factors=OpportunityFactors(
            price_score=Decimal("90"),
            trend_score=Decimal("80"),
            demand_score=Decimal("85"),
            competition_score=Decimal("70"),
            risk_score=Decimal("75"),
        ),
        generated_at=datetime.now(timezone.utc),
    )


def test_builder_creates_structured_decision_report() -> None:
    evaluation = OpportunityEvaluation(
        score=make_score(),
        decision=OpportunityDecision.BUY,
        reasons=(
            OpportunityReason.PRICE_ADVANTAGE,
            OpportunityReason.HIGH_DEMAND,
            OpportunityReason.HIGH_COMPETITION,
        ),
        evaluated_at=datetime.now(timezone.utc),
    )

    report = OpportunityDecisionReportBuilder().build(evaluation)

    assert report.decision is OpportunityDecision.BUY
    assert report.score == Decimal("82.50")
    assert report.grade is OpportunityGrade.GOOD
    assert report.confidence == Decimal("88")
    assert report.reasons == evaluation.reasons
    assert report.strengths == (
        OpportunityReason.PRICE_ADVANTAGE,
        OpportunityReason.HIGH_DEMAND,
    )
    assert report.warnings == (OpportunityReason.HIGH_COMPETITION,)
    assert report.recommended_action


class CompleteInputAdapter:
    def adapt(self, discovery_result: DiscoveryResult) -> OpportunityIntelligenceInput:
        return OpportunityIntelligenceInput(
            factors=OpportunityFactors(
                price_score=Decimal("90"),
                trend_score=Decimal("80"),
                demand_score=Decimal("70"),
                competition_score=Decimal("60"),
                risk_score=Decimal("50"),
            ),
            confidence=Decimal("82"),
        )


def test_service_returns_decision_report_for_evaluated_result() -> None:
    discovery_result = DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-report",
            title="Report Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=77,
        recommendation_grade="BUY",
        recommendation_action="기존 추천 유지",
    )

    result = OpportunityIntelligenceService(
        input_adapter=CompleteInputAdapter()
    ).evaluate(discovery_result)

    assert result.status is OpportunityIntelligenceStatus.EVALUATED
    assert result.decision_report is not None
    assert result.evaluation is not None
    assert result.score is not None
    assert result.decision_report.decision is result.evaluation.decision
    assert result.decision_report.score == result.score.score
    assert result.decision_report.confidence == result.score.confidence
