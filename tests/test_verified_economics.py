from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import (
    EconomicEvidence,
    EconomicsCalculation,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.models import Product, ProductDataSource
from engine.opportunity import (
    build_verified_economics_input,
    calculate_product_opportunity,
    calculate_verified_economics,
)
from engine.price_intelligence import PriceIntelligence
from engine.production_safety import (
    ProductionSafetyStatus,
    assess_production_safety,
)


def evidence(
    status: EvidenceStatus,
    source: str = "test",
) -> EconomicEvidence:
    return EconomicEvidence(status=status, source=source)


def money(
    amount: str | None,
    status: EvidenceStatus = EvidenceStatus.VERIFIED,
) -> MoneyInput:
    return MoneyInput(
        amount=Decimal(amount) if amount is not None else None,
        currency="USD",
        evidence=evidence(status),
    )


def rate(
    value: str | None,
    status: EvidenceStatus = EvidenceStatus.VERIFIED,
) -> RateInput:
    return RateInput(
        rate=Decimal(value) if value is not None else None,
        evidence=evidence(status),
    )


def complete_input() -> VerifiedEconomicsInput:
    return VerifiedEconomicsInput(
        purchase_cost=money("50", EvidenceStatus.ESTIMATED),
        shipping_cost=money("5"),
        marketplace_fee_rate=rate("0.10"),
        payment_fee_rate=rate("0.03"),
        fixed_fee=money("0.30"),
        tax_rate=rate("0", EvidenceStatus.DEFAULT),
        duty_cost=money(None, EvidenceStatus.UNSUPPORTED),
        other_cost=money("2", EvidenceStatus.ESTIMATED),
        expected_sale_price=money("100", EvidenceStatus.ESTIMATED),
    )


def price_intelligence() -> PriceIntelligence:
    return PriceIntelligence(
        currency="USD",
        lowest_price=Decimal("80"),
        average_price=Decimal("100"),
        median_price=Decimal("100"),
        highest_price=Decimal("120"),
        price_range=Decimal("40"),
        price_variation_rate=Decimal("40"),
        price_stability_level="medium",
        recommended_selling_price=Decimal("100"),
        sample_size=2,
    )


def test_evidence_status_and_timestamp_are_validated() -> None:
    observed_at = datetime(2026, 8, 2, tzinfo=timezone.utc)
    value = EconomicEvidence(
        status="verified",
        source="ebay",
        observed_at=observed_at,
    )

    assert value.status is EvidenceStatus.VERIFIED
    assert value.observed_at == observed_at

    with pytest.raises(ValueError, match="지원하지 않는"):
        EconomicEvidence(status="invalid", source="test")
    with pytest.raises(ValueError, match="출처"):
        EconomicEvidence(status=EvidenceStatus.VERIFIED, source=" ")


def test_money_input_distinguishes_verified_default_and_missing() -> None:
    verified_zero = money("0", EvidenceStatus.VERIFIED)
    default_zero = money("0", EvidenceStatus.DEFAULT)
    missing = money(None, EvidenceStatus.MISSING)

    assert verified_zero.amount == default_zero.amount == Decimal("0")
    assert verified_zero.evidence.status is EvidenceStatus.VERIFIED
    assert default_zero.evidence.status is EvidenceStatus.DEFAULT
    assert missing.amount is None

    with pytest.raises(ValueError, match="값이 없어야"):
        money("0", EvidenceStatus.MISSING)
    with pytest.raises(ValueError, match="3자리"):
        MoneyInput(Decimal("1"), "US", evidence(EvidenceStatus.VERIFIED))


def test_rate_input_validates_presence_and_non_negative_value() -> None:
    assert rate("0", EvidenceStatus.VERIFIED).rate == Decimal("0")
    assert rate("0", EvidenceStatus.DEFAULT).evidence.status is EvidenceStatus.DEFAULT

    with pytest.raises(ValueError, match="값이 필요"):
        rate(None, EvidenceStatus.VERIFIED)
    with pytest.raises(ValueError, match="0 이상"):
        rate("-0.01")


def test_verified_economics_validates_currency_and_rate_bounds() -> None:
    values = complete_input()
    assert values.is_ready is True

    with pytest.raises(ValueError, match="동일한 통화"):
        VerifiedEconomicsInput(
            purchase_cost=values.purchase_cost,
            shipping_cost=MoneyInput(Decimal("5"), "KRW", evidence(EvidenceStatus.VERIFIED)),
            marketplace_fee_rate=values.marketplace_fee_rate,
            payment_fee_rate=values.payment_fee_rate,
            fixed_fee=values.fixed_fee,
            tax_rate=values.tax_rate,
            duty_cost=values.duty_cost,
            other_cost=values.other_cost,
            expected_sale_price=values.expected_sale_price,
        )


def test_mapper_preserves_verified_and_default_provenance() -> None:
    product = Product(
        marketplace="ebay",
        item_id="item-1",
        title="Product",
        price=50,
        currency="USD",
        shipping_cost=0,
        data_source=ProductDataSource.PRODUCTION,
    )

    result = build_verified_economics_input(
        product=product,
        selling_price=100,
        marketplace_fee_rate=0,
        payment_fee_rate=0,
        fixed_fee=0,
        marketplace_fee_known=True,
        payment_fee_known=False,
        fixed_fee_known=True,
    )

    assert result.shipping_cost.amount == Decimal("0")
    assert result.shipping_cost.evidence.status is EvidenceStatus.VERIFIED
    assert result.marketplace_fee_rate.evidence.status is EvidenceStatus.VERIFIED
    assert result.payment_fee_rate.evidence.status is EvidenceStatus.DEFAULT
    assert result.fixed_fee.evidence.status is EvidenceStatus.VERIFIED
    assert result.duty_cost.evidence.status is EvidenceStatus.UNSUPPORTED
    assert result.is_ready is False
    assert result.readiness_missing_fields == ("payment_fee_rate",)


def test_wrapper_matches_legacy_roi_and_recommendation() -> None:
    product = Product(
        marketplace="ebay",
        item_id="item-2",
        title="Product",
        price=50,
        currency="USD",
        shipping_cost=5,
    )
    economics = build_verified_economics_input(
        product=product,
        selling_price=100,
        marketplace_fee_rate=0.10,
        payment_fee_rate=0.03,
        fixed_fee=0.30,
        marketplace_fee_known=True,
        payment_fee_known=True,
        fixed_fee_known=True,
        tax_rate=0.05,
        other_cost=2,
    )
    wrapped = calculate_verified_economics(
        marketplace="ebay",
        economics=economics,
        estimated_monthly_sales=100,
        competitor_count=10,
        risk_level="medium",
    )
    legacy = calculate_product_opportunity(
        product=product,
        selling_price=100,
        marketplace_fee_rate=0.10,
        payment_fee_rate=0.03,
        fixed_fee=0.30,
        marketplace_fee_known=True,
        payment_fee_known=True,
        fixed_fee_known=True,
        tax_rate=0.05,
        other_cost=2,
        estimated_monthly_sales=100,
        competitor_count=10,
        risk_level="medium",
    )

    assert wrapped.roi == Decimal(str(legacy["roi"]))
    assert wrapped.net_profit.amount == Decimal(str(legacy["net_profit"]))
    assert wrapped.analysis["recommendation"] == legacy["recommendation"]
    assert isinstance(wrapped, EconomicsCalculation)


def test_safety_prefers_contract_and_legacy_fallback_remains_available() -> None:
    product = Product(
        marketplace="ebay",
        item_id="item-3",
        title="Product",
        price=50,
        currency="USD",
        shipping_cost=5,
        data_source=ProductDataSource.PRODUCTION,
    )
    analysis = {
        "shipping_cost_source": "marketplace",
        "marketplace_fee_rate": 0.15,
        "payment_fee_rate": 0.0,
        "fixed_fee": 0.0,
        "marketplace_fee_known": True,
        "payment_fee_known": True,
        "fixed_fee_known": True,
        "net_profit": 10,
        "roi": 20,
        "passes_profitability_filter": True,
    }
    legacy = assess_production_safety(
        product=product,
        analysis=analysis,
        price_intelligence=price_intelligence(),
    )

    incomplete = complete_input()
    incomplete = VerifiedEconomicsInput(
        purchase_cost=incomplete.purchase_cost,
        shipping_cost=incomplete.shipping_cost,
        marketplace_fee_rate=incomplete.marketplace_fee_rate,
        payment_fee_rate=rate("0", EvidenceStatus.DEFAULT),
        fixed_fee=incomplete.fixed_fee,
        tax_rate=incomplete.tax_rate,
        duty_cost=incomplete.duty_cost,
        other_cost=incomplete.other_cost,
        expected_sale_price=incomplete.expected_sale_price,
    )
    calculation = calculate_verified_economics(
        marketplace="ebay",
        economics=incomplete,
    )
    contract = assess_production_safety(
        product=product,
        analysis=analysis,
        price_intelligence=price_intelligence(),
        economics=calculation,
    )

    assert legacy.status is ProductionSafetyStatus.READY
    assert contract.status is ProductionSafetyStatus.INSUFFICIENT_DATA
    assert "payment_fee_rate" in contract.missing_fields
