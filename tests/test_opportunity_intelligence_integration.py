from __future__ import annotations

from decimal import Decimal

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceInput,
    OpportunityIntelligenceService,
    OpportunityIntelligenceStatus,
)
from app.domain.discovery import DiscoveryResult
from app.domain.opportunity import OpportunityDecision, OpportunityFactors
from app.infrastructure.opportunity_intelligence import (
    DiscoveryResultOpportunityIntelligenceAdapter,
)
from app.models import Product


def make_result(*, confidence: object = 82) -> DiscoveryResult:
    return DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-1",
            title="Test Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=77,
        recommendation_grade="BUY",
        recommendation_action="기존 추천 유지",
        metadata={"confidence_score": confidence},
    )


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


class InvalidInputAdapter:
    def adapt(self, discovery_result: DiscoveryResult) -> OpportunityIntelligenceInput:
        raise ValueError("invalid factor source")


def test_discovery_adapter_extracts_confidence_and_reports_missing_factors() -> None:
    prepared = DiscoveryResultOpportunityIntelligenceAdapter().adapt(
        make_result(confidence=90)
    )

    assert prepared.factors is None
    assert prepared.confidence == Decimal("90")
    assert prepared.missing_factors == (
        "price_score",
        "trend_score",
        "demand_score",
        "competition_score",
        "risk_score",
    )


def test_discovery_adapter_accepts_decimal_compatible_confidence() -> None:
    prepared = DiscoveryResultOpportunityIntelligenceAdapter().adapt(
        make_result(confidence="82.5")
    )

    assert prepared.confidence == Decimal("82.5")


def test_default_discovery_adapter_returns_unavailable_without_defaults() -> None:
    result = OpportunityIntelligenceService(
        input_adapter=DiscoveryResultOpportunityIntelligenceAdapter()
    ).evaluate(make_result())

    assert result.status is OpportunityIntelligenceStatus.UNAVAILABLE
    assert result.score is None
    assert result.evaluation is None
    assert len(result.missing_factors) == 5


def test_complete_adapter_runs_score_and_decision_engines() -> None:
    discovery_result = make_result()

    result = OpportunityIntelligenceService(
        input_adapter=CompleteInputAdapter()
    ).evaluate(discovery_result)

    assert result.status is OpportunityIntelligenceStatus.EVALUATED
    assert result.score is not None
    assert result.score.score == Decimal("73.50")
    assert result.score.confidence == Decimal("82")
    assert result.evaluation is not None
    assert result.evaluation.decision is OpportunityDecision.WATCH
    assert discovery_result.recommendation_grade == "BUY"
    assert discovery_result.recommendation_action == "기존 추천 유지"


def test_invalid_adapter_input_returns_failed_result() -> None:
    result = OpportunityIntelligenceService(
        input_adapter=InvalidInputAdapter()
    ).evaluate(make_result())

    assert result.status is OpportunityIntelligenceStatus.FAILED
    assert result.error_message == "invalid factor source"
    assert result.score is None
    assert result.evaluation is None


def test_invalid_confidence_returns_failed_result() -> None:
    result = OpportunityIntelligenceService(
        input_adapter=DiscoveryResultOpportunityIntelligenceAdapter()
    ).evaluate(make_result(confidence=101))

    assert result.status is OpportunityIntelligenceStatus.FAILED
    assert "0 이상 100 이하" in (result.error_message or "")
