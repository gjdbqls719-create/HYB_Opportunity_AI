from __future__ import annotations

from decimal import Decimal

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceInput,
    OpportunityIntelligenceService,
    OpportunityIntelligenceStatus,
    OpportunityRecommendationLevel,
    OpportunityTrendLevel,
)
from app.domain.discovery import DiscoveryResult
from app.domain.opportunity import OpportunityFactors
from app.domain.trend import PriceTrendAnalysis, PriceVolatility, TrendDirection
from app.engine import OpportunityConfidenceLevel, OpportunityRiskLevel
from app.models import Product


def make_discovery_result() -> DiscoveryResult:
    return DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="service-enrichment-item",
            title="Service Enrichment Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=90,
    )


def make_factors(*, risk_score: str = "85") -> OpportunityFactors:
    return OpportunityFactors(
        price_score=Decimal("95"),
        trend_score=Decimal("95"),
        demand_score=Decimal("95"),
        competition_score=Decimal("90"),
        risk_score=Decimal(risk_score),
    )


def make_strong_trend() -> PriceTrendAnalysis:
    return PriceTrendAnalysis(
        current_price=Decimal("110"),
        highest_price=Decimal("110"),
        lowest_price=Decimal("100"),
        average_price=Decimal("105"),
        median_price=Decimal("105"),
        price_range=Decimal("10"),
        change_rate=Decimal("10"),
        direction=TrendDirection.UP,
        volatility=PriceVolatility.LOW,
        near_lowest=True,
        near_highest=False,
        sample_count=3,
    )


class EnrichedInputAdapter:
    def adapt(self, discovery_result: DiscoveryResult) -> OpportunityIntelligenceInput:
        return OpportunityIntelligenceInput(
            factors=make_factors(),
            confidence=Decimal("95"),
            trend_analysis=make_strong_trend(),
        )


class BaseInputAdapter:
    def adapt(self, discovery_result: DiscoveryResult) -> OpportunityIntelligenceInput:
        return OpportunityIntelligenceInput(
            factors=make_factors(risk_score="50"),
            confidence=Decimal("82"),
        )


def test_service_returns_full_enriched_result_when_trend_analysis_is_available() -> None:
    result = OpportunityIntelligenceService(
        input_adapter=EnrichedInputAdapter()
    ).evaluate(make_discovery_result())

    assert result.status is OpportunityIntelligenceStatus.EVALUATED
    assert result.confidence_assessment is not None
    assert result.confidence_assessment.level is OpportunityConfidenceLevel.VERY_HIGH
    assert result.risk_assessment is not None
    assert result.risk_assessment.level is OpportunityRiskLevel.LOW
    assert result.trend_assessment is not None
    assert result.trend_assessment.level is OpportunityTrendLevel.STRONG_BUY_TREND
    assert result.recommendation is not None
    assert result.recommendation.level is OpportunityRecommendationLevel.STRONG_BUY


def test_service_preserves_base_evaluation_when_trend_analysis_is_unavailable() -> None:
    result = OpportunityIntelligenceService(
        input_adapter=BaseInputAdapter()
    ).evaluate(make_discovery_result())

    assert result.status is OpportunityIntelligenceStatus.EVALUATED
    assert result.score is not None
    assert result.evaluation is not None
    assert result.decision_report is not None
    assert result.confidence_assessment is not None
    assert result.confidence_assessment.level is OpportunityConfidenceLevel.HIGH
    assert result.risk_assessment is not None
    assert result.risk_assessment.level is OpportunityRiskLevel.MEDIUM
    assert result.trend_assessment is None
    assert result.recommendation is None


def test_input_rejects_invalid_trend_analysis_type() -> None:
    try:
        OpportunityIntelligenceInput(
            factors=make_factors(),
            confidence=Decimal("90"),
            trend_analysis="invalid",  # type: ignore[arg-type]
        )
    except TypeError as error:
        assert str(error) == (
            "trend_analysis는 PriceTrendAnalysis 또는 None이어야 합니다."
        )
    else:
        raise AssertionError("TypeError가 발생해야 합니다.")
