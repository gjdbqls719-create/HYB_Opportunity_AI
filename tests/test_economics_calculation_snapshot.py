from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.economics_calculation_snapshot import (
    EconomicsCalculationSnapshotRepository,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.economics_calculation_snapshot import (
    ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION,
    EconomicsAnalysisSnapshot,
    EconomicsCalculationParameters,
    EconomicsCalculationSnapshot,
    ProfitabilityResultSnapshot,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import (
    EconomicEvidence,
    EconomicsCalculation,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from engine.opportunity import calculate_verified_economics


NOW = datetime(2026, 8, 4, 11, tzinfo=timezone.utc)


def evidence(status=EvidenceStatus.VERIFIED, source="operator"):
    return EconomicEvidence(status, source, NOW, "source-record-1")


def money(amount, status=EvidenceStatus.VERIFIED, source="operator"):
    return MoneyInput(amount, "USD", evidence(status, source))


def rate(value):
    return RateInput(value, evidence())


def inputs() -> VerifiedEconomicsInput:
    return VerifiedEconomicsInput(
        purchase_cost=money(Decimal("50")),
        shipping_cost=money(Decimal("5")),
        marketplace_fee_rate=rate(Decimal("0.10")),
        payment_fee_rate=rate(Decimal("0.03")),
        fixed_fee=money(Decimal("0.30")),
        tax_rate=rate(Decimal("0.05")),
        duty_cost=money(None, EvidenceStatus.UNSUPPORTED, "legacy_calculator"),
        other_cost=money(Decimal("2")),
        expected_sale_price=money(Decimal("100"), EvidenceStatus.ESTIMATED, "price_intelligence"),
    )


def identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.LISTING,
        market="US", marketplace="ebay", canonical_product_id=None,
        marketplace_item_id="item-1", normalized_query=None,
        category="electronics", variant_identity=None, condition="new",
        window_started_at=NOW - timedelta(minutes=1), window_ended_at=NOW,
    )


def calculation() -> EconomicsCalculation:
    return calculate_verified_economics(
        marketplace="ebay",
        economics=inputs(),
        minimum_net_profit=Decimal("10"),
        minimum_roi=Decimal("20"),
        estimated_monthly_sales=100,
        competitor_count=10,
        risk_level="medium",
        context={"item_id": "item-1", "shipping_cost_known": True},
    )


def parameters() -> EconomicsCalculationParameters:
    return EconomicsCalculationParameters(
        marketplace="ebay",
        minimum_net_profit=Decimal("10"),
        minimum_roi=Decimal("20"),
        estimated_monthly_sales=100,
        competitor_count=10,
        risk_level="medium",
        context_items=(("item_id", "item-1"), ("shipping_cost_known", True)),
    )


def snapshot(result: EconomicsCalculation | None = None) -> EconomicsCalculationSnapshot:
    value = result or calculation()
    profitability = ProfitabilityResultSnapshot(
        minimum_net_profit=Decimal("10"),
        minimum_roi=Decimal("20"),
        passes_net_profit_filter=value.analysis["passes_net_profit_filter"],
        passes_roi_filter=value.analysis["passes_roi_filter"],
        passes_profitability_filter=value.analysis["passes_profitability_filter"],
    )
    return EconomicsCalculationSnapshot(
        snapshot_id="economics-calculation-1",
        opportunity_identity=OpportunityIdentity("opp-1", "ebay:item-1"),
        market_observation_identity=identity(),
        candidate_opportunity_binding_id="binding-1",
        verified_economics_opportunity_id="opp-1",
        revenue=value.inputs.expected_sale_price,
        marketplace_fee=value.marketplace_fee,
        payment_fee=value.payment_fee,
        tax_cost=value.tax_cost,
        landed_cost=value.landed_cost,
        selling_cost=value.selling_cost,
        total_cost=value.total_cost,
        net_profit=value.net_profit,
        roi=value.roi,
        landed_cost_roi=value.landed_cost_roi,
        margin_rate=value.margin_rate,
        break_even=money(None, EvidenceStatus.UNSUPPORTED, "legacy_calculator"),
        profitability_result=profitability,
        calculation_parameters=parameters(),
        analysis=EconomicsAnalysisSnapshot.from_runtime(value.analysis),
        calculation_version="verified-economics-calculator-v1",
        generated_at=NOW,
    )


def test_snapshot_preserves_actual_runtime_results_without_runtime_object() -> None:
    result = calculation()
    value = snapshot(result)
    for name in (
        "marketplace_fee", "payment_fee", "tax_cost", "landed_cost",
        "selling_cost", "total_cost", "net_profit", "roi",
        "landed_cost_roi", "margin_rate",
    ):
        assert getattr(value, name) == getattr(result, name)
    assert value.revenue == result.inputs.expected_sale_price
    assert "economics_calculation" not in EconomicsCalculationSnapshot.__dataclass_fields__
    assert not any(getattr(value, field.name) is result for field in fields(value))


def test_profitability_and_unsupported_break_even_are_explicit() -> None:
    value = snapshot()
    assert value.profitability_result.passes_profitability_filter is True
    assert value.break_even.amount is None
    assert value.break_even.evidence.status is EvidenceStatus.UNSUPPORTED
    assert value.verified_economics_opportunity_id == "opp-1"


def test_snapshot_is_immutable_equal_versioned_and_timezone_aware() -> None:
    value = snapshot()
    assert value == snapshot()
    assert value.schema_version == ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION
    assert value.generated_at == NOW
    with pytest.raises(FrozenInstanceError):
        value.roi = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        value.calculation_parameters.context_items += (("new", "value"),)


@pytest.mark.parametrize(
    "override,error",
    (
        ({"verified_economics_opportunity_id": ""}, ValueError),
        ({"roi": 1.0}, TypeError),
        ({"margin_rate": Decimal("Infinity")}, ValueError),
        ({"generated_at": NOW.replace(tzinfo=None)}, ValueError),
        ({"net_profit": money(Decimal("1"), source="different")}, ValueError),
        ({"calculation_version": ""}, ValueError),
    ),
)
def test_snapshot_rejects_invalid_contract_values(override, error) -> None:
    value = snapshot()
    payload = {field.name: getattr(value, field.name) for field in fields(value)}
    if "net_profit" in override:
        override["net_profit"] = MoneyInput(
            override["net_profit"].amount, "KRW", override["net_profit"].evidence
        )
    payload.update(override)
    with pytest.raises(error):
        EconomicsCalculationSnapshot(**payload)


def test_context_and_profitability_contracts_reject_mutability_and_conflicts() -> None:
    with pytest.raises(TypeError):
        EconomicsCalculationParameters(
            "ebay", Decimal("0"), Decimal("0"), 0, 0, "medium",
            (("mutable", []),),
        )
    with pytest.raises(ValueError):
        ProfitabilityResultSnapshot(
            Decimal("0"), Decimal("0"), True, False, True
        )


class MemoryEconomicsCalculationSnapshotRepository:
    def __init__(self): self.values = {}
    def save_snapshot(self, value): self.values[value.snapshot_id] = value; return value
    def get_snapshot(self, snapshot_id): return self.values.get(snapshot_id)
    def get_by_opportunity(self, identity_value):
        return tuple(v for v in self.values.values() if v.opportunity_identity == identity_value)
    def get_by_market_identity(self, identity_value):
        return tuple(v for v in self.values.values() if v.market_observation_identity == identity_value)


def exercise_repository(repository: EconomicsCalculationSnapshotRepository) -> None:
    value = snapshot()
    assert repository.save_snapshot(value) == value
    assert repository.get_snapshot(value.snapshot_id) == value
    assert repository.get_by_opportunity(value.opportunity_identity) == (value,)
    assert repository.get_by_market_identity(value.market_observation_identity) == (value,)


def test_repository_boundary_supports_required_operations() -> None:
    exercise_repository(MemoryEconomicsCalculationSnapshotRepository())
