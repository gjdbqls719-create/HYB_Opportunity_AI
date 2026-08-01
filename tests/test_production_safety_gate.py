from decimal import Decimal

from app.models import Product, ProductDataSource
from engine.price_intelligence import PriceIntelligence
from engine.production_safety import (
    ProductionSafetyStatus,
    apply_production_safety_gate,
    assess_production_safety,
)
from engine.recommendation import RecommendationResult


def make_product(
    *,
    source: ProductDataSource = ProductDataSource.PRODUCTION,
    shipping_cost: float | None = 5.0,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="safe-item",
        title="Safe Product",
        price=50.0,
        currency="USD",
        shipping_cost=shipping_cost,
        data_source=source,
    )


def make_price_intelligence(*, sample_size: int = 2) -> PriceIntelligence:
    return PriceIntelligence(
        currency="USD",
        lowest_price=Decimal("50"),
        average_price=Decimal("75"),
        median_price=Decimal("75"),
        highest_price=Decimal("100"),
        price_range=Decimal("50"),
        price_variation_rate=Decimal("66.67"),
        price_stability_level="low",
        recommended_selling_price=Decimal("75"),
        sample_size=sample_size,
    )


def make_analysis() -> dict[str, object]:
    return {
        "shipping_cost_source": "marketplace",
        "marketplace_fee_rate": 0.15,
        "payment_fee_rate": 0.0,
        "fixed_fee": 0.0,
        "marketplace_fee_known": True,
        "payment_fee_known": True,
        "fixed_fee_known": True,
        "net_profit": 8.75,
        "roi": 17.5,
        "passes_profitability_filter": True,
    }


def make_buy_recommendation() -> RecommendationResult:
    return RecommendationResult(
        score=85,
        stars=5,
        star_display="★★★★★",
        grade="STRONG_BUY",
        action="매입 추천",
        success_probability=80,
        reasons=("high score",),
        warnings=(),
        summary="strong candidate",
    )


def test_complete_production_economics_allows_buy_recommendation() -> None:
    assessment = assess_production_safety(
        product=make_product(),
        analysis=make_analysis(),
        price_intelligence=make_price_intelligence(),
    )
    result = apply_production_safety_gate(
        make_buy_recommendation(), assessment
    )

    assert assessment.status is ProductionSafetyStatus.READY
    assert result.grade == "STRONG_BUY"
    assert result.score == 85
    assert result.safety_status == "READY"
    assert result.original_grade == "STRONG_BUY"
    assert result.effective_grade == "STRONG_BUY"


def test_profitability_failure_downgrades_high_score_without_changing_score() -> None:
    analysis = make_analysis()
    analysis["passes_profitability_filter"] = False
    assessment = assess_production_safety(
        product=make_product(),
        analysis=analysis,
        price_intelligence=make_price_intelligence(),
    )

    result = apply_production_safety_gate(make_buy_recommendation(), assessment)

    assert assessment.status is ProductionSafetyStatus.PROFITABILITY_FAILED
    assert result.grade == "WATCH"
    assert result.effective_grade == "WATCH"
    assert result.original_grade == "STRONG_BUY"
    assert result.safety_status == "PROFITABILITY_FAILED"
    assert result.safety_status != "READY"
    assert result.score == 85
    assert any("profitability" in reason for reason in result.safety_reasons)


def test_unverified_fee_defaults_are_not_treated_as_verified_zero() -> None:
    analysis = make_analysis()
    analysis["payment_fee_known"] = False
    analysis["fixed_fee_known"] = False
    assessment = assess_production_safety(
        product=make_product(),
        analysis=analysis,
        price_intelligence=make_price_intelligence(),
    )

    assert assessment.status is ProductionSafetyStatus.INSUFFICIENT_DATA
    assert "payment_fee_rate" in assessment.missing_fields
    assert "fixed_fee" in assessment.missing_fields


def test_demo_source_cannot_produce_buy_recommendation() -> None:
    assessment = assess_production_safety(
        product=make_product(source=ProductDataSource.DEMO),
        analysis=make_analysis(),
        price_intelligence=make_price_intelligence(),
    )
    result = apply_production_safety_gate(
        make_buy_recommendation(), assessment
    )

    assert result.grade == "WATCH"
    assert result.score == 85
    assert result.safety_status == "INSUFFICIENT_DATA"
    assert "production_source" in assessment.missing_fields


def test_missing_shipping_and_sale_evidence_downgrades_buy() -> None:
    assessment = assess_production_safety(
        product=make_product(shipping_cost=None),
        analysis=make_analysis(),
        price_intelligence=make_price_intelligence(sample_size=1),
    )
    result = apply_production_safety_gate(
        make_buy_recommendation(), assessment
    )

    assert result.grade == "WATCH"
    assert assessment.missing_fields == (
        "shipping_cost",
        "expected_selling_price",
    )
    assert len(result.safety_reasons) == 2


def test_gate_does_not_upgrade_or_recalculate_existing_watch() -> None:
    recommendation = make_buy_recommendation()
    recommendation = RecommendationResult(
        score=45,
        stars=3,
        star_display="★★★☆☆",
        grade="WATCH",
        action="검토",
        success_probability=40,
        reasons=recommendation.reasons,
        warnings=(),
        summary="watch",
    )
    assessment = assess_production_safety(
        product=make_product(source=ProductDataSource.TEST),
        analysis=make_analysis(),
        price_intelligence=make_price_intelligence(),
    )

    result = apply_production_safety_gate(recommendation, assessment)

    assert result.grade == "WATCH"
    assert result.score == 45
    assert result.safety_status == "INSUFFICIENT_DATA"
