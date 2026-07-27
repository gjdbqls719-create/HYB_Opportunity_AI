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
    DiscoveryFactorPolicy,
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


def test_discovery_adapter_builds_complete_factors_from_verified_metadata() -> None:
    result = DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-factor",
            title="Factor Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=80,
        metadata={
            "confidence_score": 82,
            "trend_score_adjustment": 15,
            "analysis": {
                "roi": 50,
                "estimated_monthly_sales": 500,
                "competitor_count": 5,
                "risk_level": "low",
            },
        },
    )

    prepared = DiscoveryResultOpportunityIntelligenceAdapter().adapt(result)

    assert prepared.missing_factors == ()
    assert prepared.confidence == Decimal("82")
    assert prepared.factors == OpportunityFactors(
        price_score=Decimal("80.00"),
        trend_score=Decimal("100"),
        demand_score=Decimal("100"),
        competition_score=Decimal("90.00"),
        risk_score=Decimal("90"),
    )


def test_default_adapter_can_run_full_intelligence_when_sources_are_complete() -> None:
    discovery_result = DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-complete",
            title="Complete Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=80,
        metadata={
            "confidence_score": 80,
            "trend_score_adjustment": 0,
            "analysis": {
                "roi": 30,
                "estimated_monthly_sales": 200,
                "competitor_count": 20,
                "risk_level": "medium",
            },
        },
    )

    result = OpportunityIntelligenceService(
        input_adapter=DiscoveryResultOpportunityIntelligenceAdapter()
    ).evaluate(discovery_result)

    assert result.status is OpportunityIntelligenceStatus.EVALUATED
    assert result.score is not None
    assert result.score.factors == OpportunityFactors(
        price_score=Decimal("60.00"),
        trend_score=Decimal("50.00"),
        demand_score=Decimal("70.00"),
        competition_score=Decimal("60.00"),
        risk_score=Decimal("50"),
    )
    assert result.evaluation is not None


def test_discovery_adapter_reports_only_the_missing_factor_sources() -> None:
    discovery_result = DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-partial",
            title="Partial Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=80,
        metadata={
            "confidence_score": 80,
            "analysis": {
                "roi": 30,
                "estimated_monthly_sales": 200,
                "competitor_count": 20,
                "risk_level": "medium",
            },
        },
    )

    prepared = DiscoveryResultOpportunityIntelligenceAdapter().adapt(
        discovery_result
    )

    assert prepared.factors is None
    assert prepared.missing_factors == ("trend_score",)


def test_invalid_factor_source_returns_failed_result() -> None:
    discovery_result = DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-invalid",
            title="Invalid Product",
            price=100,
            currency="USD",
        ),
        opportunity_score=80,
        metadata={
            "confidence_score": 80,
            "trend_score_adjustment": 0,
            "analysis": {
                "roi": 30,
                "estimated_monthly_sales": -1,
                "competitor_count": 20,
                "risk_level": "medium",
            },
        },
    )

    result = OpportunityIntelligenceService(
        input_adapter=DiscoveryResultOpportunityIntelligenceAdapter()
    ).evaluate(discovery_result)

    assert result.status is OpportunityIntelligenceStatus.FAILED
    assert "0 이상" in (result.error_message or "")


def test_profitability_score_preserves_existing_roi_mapping() -> None:
    policy = DiscoveryFactorPolicy()

    assert policy.profitability_score(roi=Decimal("0")) == Decimal("0")
    assert policy.profitability_score(roi=Decimal("15")) == Decimal("40.00")
    assert policy.profitability_score(roi=Decimal("30")) == Decimal("60.00")
    assert policy.profitability_score(roi=Decimal("50")) == Decimal("80.00")
    assert policy.profitability_score(roi=Decimal("100")) == Decimal("100")


def test_legacy_price_score_delegates_to_profitability_score() -> None:
    policy = DiscoveryFactorPolicy()

    assert policy.price_score(Decimal("37.5")) == policy.profitability_score(
        roi=Decimal("37.5")
    )


def test_profitability_score_rejects_non_decimal_roi() -> None:
    policy = DiscoveryFactorPolicy()

    try:
        policy.profitability_score(roi=30)  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == "roi는 Decimal이어야 합니다."
    else:
        raise AssertionError("TypeError가 발생해야 합니다.")


def test_profitability_score_rejects_non_finite_roi() -> None:
    policy = DiscoveryFactorPolicy()

    try:
        policy.profitability_score(roi=Decimal("NaN"))
    except ValueError as error:
        assert str(error) == "roi는 유한한 값이어야 합니다."
    else:
        raise AssertionError("ValueError가 발생해야 합니다.")
