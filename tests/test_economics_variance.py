import sqlite3
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.economics_variance import (
    ActualEconomicsForVarianceNotFoundError,
    DuplicateEstimatedBaselineError,
    EconomicsVarianceService,
    EstimatedBaselineNotFoundError,
    GetVariance,
    map_economics_calculation_to_snapshot,
)
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    OpportunityValidationService,
)
from app.domain.opportunity import (
    ActualEconomics,
    EconomicEvidence,
    EstimatedEconomicsSnapshot,
    EvidenceStatus,
    MoneyInput,
    OpportunityLifecycle,
    RateInput,
    SnapshotValidationError,
    VarianceAvailability,
    VerifiedEconomicsInput,
    calculate_economics_variance,
)
from app.infrastructure.economics_variance import SQLiteEstimatedEconomicsSnapshotRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from engine.opportunity import calculate_verified_economics


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def evidence(status=EvidenceStatus.VERIFIED, source="test"):
    return EconomicEvidence(status=status, source=source, observed_at=NOW, reference="ref")


def snapshot(**overrides):
    required_evidence = {
        name: evidence(source=name)
        for name in (
            "purchase_price", "shipping_cost", "expected_sale_price",
            "marketplace_fee", "payment_fee", "fixed_fee",
            "expected_profit", "expected_roi", "tax_rate", "tax_cost",
        )
    }
    values = dict(
        snapshot_id="snap-1", opportunity_id="opp-1", baseline_kind="admission",
        currency="USD", purchase_price=Decimal("100"), shipping_cost=Decimal("10"),
        expected_sale_price=Decimal("180"), marketplace_fee=Decimal("18"),
        payment_fee=Decimal("5"), fixed_fee=Decimal("2"),
        expected_profit=Decimal("45"), expected_roi=Decimal("45"),
        tax_cost=Decimal("0"), other_cost=Decimal("0"), duty_cost=Decimal("0"),
        evidence_metadata=required_evidence,
        calculation_version="opportunity-v1", variance_formula_version="variance-v1",
        captured_at=NOW,
    )
    values.update(overrides)
    return EstimatedEconomicsSnapshot(**values)


def actual(*, settled=True, currency="USD"):
    item = ActualEconomics("opp-1", currency, created_at=NOW)
    item.record_purchase(
        purchase_price=Decimal("110"), shipping_cost=Decimal("5"), occurred_at=NOW,
    )
    if settled:
        item.record_sale(sale_price=Decimal("200"), occurred_at=NOW + timedelta(hours=1))
        item.complete_settlement(
            marketplace_fee=Decimal("20"), payment_fee=Decimal("4"),
            fixed_fee=Decimal("1"), settlement_amount=Decimal("175"),
            occurred_at=NOW + timedelta(hours=2),
        )
    return item


def metric(result, name):
    return next(value for value in result.metrics if value.metric == name)


def test_signed_absolute_percentage_decimal_and_roi_point_variance() -> None:
    result = calculate_economics_variance(snapshot(), actual())
    purchase = metric(result, "purchase_price")
    assert purchase.difference == Decimal("10")
    assert purchase.absolute_difference == Decimal("10")
    assert purchase.percentage_difference == Decimal("0.1")
    shipping = metric(result, "shipping_cost")
    assert shipping.difference == Decimal("-5")
    assert shipping.absolute_difference == Decimal("5")
    roi = metric(result, "roi")
    assert roi.difference == actual().calculate_actual_roi() - Decimal("45")
    assert roi.percentage_difference is None
    assert roi.unit == "percentage_points"


def test_zero_estimate_percentage_is_undefined_but_difference_remains() -> None:
    result = calculate_economics_variance(
        snapshot(shipping_cost=Decimal("0")), actual(),
    )
    shipping = metric(result, "shipping_cost")
    assert shipping.availability is VarianceAvailability.PERCENTAGE_UNDEFINED
    assert shipping.difference == Decimal("5")
    assert shipping.percentage_difference is None


def test_currency_incomplete_and_cost_scope_are_explicit() -> None:
    currency = calculate_economics_variance(snapshot(), actual(currency="KRW"))
    assert all(m.availability is VarianceAvailability.CURRENCY_MISMATCH for m in currency.metrics)
    incomplete = calculate_economics_variance(snapshot(), actual(settled=False))
    assert all(m.availability is VarianceAvailability.ACTUAL_INCOMPLETE for m in incomplete.metrics)
    scope = calculate_economics_variance(
        snapshot(tax_cost=Decimal("1")), actual(),
    )
    assert metric(scope, "profit").availability is VarianceAvailability.COST_SCOPE_MISMATCH
    assert metric(scope, "roi").availability is VarianceAvailability.COST_SCOPE_MISMATCH
    assert metric(scope, "purchase_price").availability is VarianceAvailability.COMPARABLE


def test_negative_expected_and_actual_values_are_supported() -> None:
    loss = ActualEconomics("opp-1", "USD", created_at=NOW)
    loss.record_purchase(
        purchase_price=Decimal("100"), shipping_cost=Decimal("10"), occurred_at=NOW,
    )
    loss.record_sale(sale_price=Decimal("80"), occurred_at=NOW)
    loss.complete_settlement(
        marketplace_fee=Decimal("8"), payment_fee=Decimal("2"),
        fixed_fee=Decimal("1"), settlement_amount=Decimal("69"), occurred_at=NOW,
    )
    result = calculate_economics_variance(
        snapshot(expected_profit=Decimal("-20"), expected_roi=Decimal("-20")),
        loss,
    )
    assert metric(result, "profit").actual == Decimal("-41")
    assert metric(result, "profit").difference == Decimal("-21")
    assert metric(result, "roi").actual == Decimal("-41")
    assert metric(result, "roi").difference == Decimal("-21")


def test_snapshot_is_immutable_and_repository_round_trips_without_overwrite() -> None:
    item = snapshot()
    with pytest.raises(FrozenInstanceError):
        item.expected_profit = Decimal("0")  # type: ignore[misc]
    with pytest.raises(TypeError):
        item.evidence_metadata["new"] = evidence()  # type: ignore[index]
    repository = SQLiteEstimatedEconomicsSnapshotRepository(":memory:")
    repository.create(item)
    assert repository.get_admission_baseline("opp-1") == item
    with pytest.raises(DuplicateEstimatedBaselineError):
        repository.create(snapshot(snapshot_id="snap-2"))
    assert repository.get_admission_baseline("opp-1") == item


@pytest.mark.parametrize(
    "missing_key",
    (
        "purchase_price", "shipping_cost", "expected_sale_price",
        "marketplace_fee", "payment_fee", "fixed_fee",
        "expected_profit", "expected_roi", "tax_rate", "tax_cost",
    ),
)
def test_snapshot_rejects_missing_required_evidence(missing_key: str) -> None:
    metadata = dict(snapshot().evidence_metadata)
    metadata.pop(missing_key)
    with pytest.raises(SnapshotValidationError, match=missing_key):
        snapshot(evidence_metadata=metadata)


def calculation():
    def money(value, status=EvidenceStatus.VERIFIED):
        return MoneyInput(
            Decimal(value) if value is not None else None, "USD", evidence(status)
        )
    def rate(value, status=EvidenceStatus.VERIFIED, source="test"):
        return RateInput(
            Decimal(value) if value is not None else None,
            evidence(status, source=source),
        )
    inputs = VerifiedEconomicsInput(
        purchase_cost=money("100"), shipping_cost=money("10"),
        marketplace_fee_rate=rate("0.10"), payment_fee_rate=rate("0.03"),
        fixed_fee=money("2"), tax_rate=rate("0", source="tax-authority"), duty_cost=money("0"),
        other_cost=money("0"), expected_sale_price=money("180"),
    )
    return calculate_verified_economics(marketplace="ebay", economics=inputs)


def test_mapper_preserves_calculation_values_evidence_and_versions() -> None:
    economics = calculation()
    result = map_economics_calculation_to_snapshot(
        snapshot_id="mapped", opportunity_id="opp-1", baseline_kind="admission",
        economics=economics, calculation_version="calc-1",
        variance_formula_version="variance-1", captured_at=NOW,
    )
    assert result.purchase_price == Decimal("100")
    assert result.expected_sale_price == Decimal("180")
    assert result.marketplace_fee == Decimal("18.0")
    assert result.evidence_metadata["purchase_price"].observed_at == NOW
    assert result.evidence_metadata["tax_rate"] == economics.inputs.tax_rate.evidence
    assert result.evidence_metadata["tax_rate"].source == "tax-authority"
    assert result.evidence_metadata["tax_cost"] == economics.tax_cost.evidence
    assert result.evidence_metadata["tax_cost"] != result.evidence_metadata["tax_rate"]
    assert result.evidence_metadata["expected_roi"] == economics.net_profit.evidence
    assert result.calculation_version == "calc-1"
    assert result.variance_formula_version == "variance-1"


def test_tax_rate_and_tax_cost_provenance_round_trip_separately() -> None:
    economics = calculation()
    item = map_economics_calculation_to_snapshot(
        snapshot_id="tax-round-trip", opportunity_id="opp-1",
        baseline_kind="admission", economics=economics,
        calculation_version="calc-1", variance_formula_version="variance-1",
        captured_at=NOW,
    )
    repository = SQLiteEstimatedEconomicsSnapshotRepository(":memory:")
    repository.create(item)
    restored = repository.get_admission_baseline("opp-1")
    assert restored is not None
    assert restored.evidence_metadata["tax_rate"] == economics.inputs.tax_rate.evidence
    assert restored.evidence_metadata["tax_cost"] == economics.tax_cost.evidence


class MemoryActuals:
    def __init__(self, item=None): self.item = item
    def get(self, opportunity_id): return self.item if self.item and self.item.opportunity_id == opportunity_id else None


def test_application_missing_actual_unsettled_and_settled_variance() -> None:
    baselines = SQLiteEstimatedEconomicsSnapshotRepository(":memory:")
    service = EconomicsVarianceService(baseline_repository=baselines, actual_repository=MemoryActuals())
    with pytest.raises(EstimatedBaselineNotFoundError):
        service.get(GetVariance("opp-1"))
    baselines.create(snapshot())
    with pytest.raises(ActualEconomicsForVarianceNotFoundError):
        service.get(GetVariance("opp-1"))
    incomplete = EconomicsVarianceService(
        baseline_repository=baselines, actual_repository=MemoryActuals(actual(settled=False)),
    ).get(GetVariance("opp-1"))
    assert all(m.availability is VarianceAvailability.ACTUAL_INCOMPLETE for m in incomplete.metrics)
    settled = EconomicsVarianceService(
        baseline_repository=baselines, actual_repository=MemoryActuals(actual()),
    ).get(GetVariance("opp-1"))
    assert settled.actual_version == 3
    assert metric(settled, "purchase_price").difference == Decimal("10")


def test_variance_query_has_no_lifecycle_side_effect() -> None:
    lifecycle = OpportunityLifecycle(
        "opp-1", "ebay:item-1", created_at=NOW, updated_at=NOW,
    )
    before = (lifecycle.status, lifecycle.version, lifecycle.updated_at)
    baselines = SQLiteEstimatedEconomicsSnapshotRepository(":memory:")
    baselines.create(snapshot())
    EconomicsVarianceService(
        baseline_repository=baselines, actual_repository=MemoryActuals(actual()),
    ).get(GetVariance("opp-1"))
    assert (lifecycle.status, lifecycle.version, lifecycle.updated_at) == before


def admission():
    return AddToValidationQueueCommand(
        discovery_reference="ebay:item-1", marketplace="ebay", title="Camera",
        admission_recommendation="WATCH", admission_score=70,
        admission_roi=float(calculation().roi), currency="USD",
        admission_safety_status="READY", operator_id="founder",
        reason="validation", captured_at=NOW, opportunity_id="opp-1",
    )


def test_variance_ready_admission_is_atomic_and_preserves_lifecycle() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = OpportunityValidationService(
        queue_repository=repository, lifecycle_repository=repository,
    )
    item = validation.add_with_economics(admission(), calculation())
    baseline = repository._economics.get_admission_baseline("opp-1")
    assert item.lifecycle_version == 1
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1
    assert baseline.opportunity_id == "opp-1"
    assert baseline.captured_at == NOW


def test_baseline_failure_rolls_back_lifecycle_history_and_admission() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteValidationQueueRepository(connection=connection)
    connection.execute(
        """CREATE TRIGGER fail_economics_baseline BEFORE INSERT
        ON opportunity_estimated_economics_snapshots BEGIN
        SELECT RAISE(ABORT, 'baseline failure'); END"""
    )
    validation = OpportunityValidationService(
        queue_repository=repository, lifecycle_repository=repository,
    )
    with pytest.raises(sqlite3.IntegrityError, match="baseline failure"):
        validation.add_with_economics(admission(), calculation())
    assert repository.get("opp-1") is None
    assert repository.list_transitions("opp-1") == ()
    assert repository.get_queue_item("opp-1") is None
    assert repository._economics.get_admission_baseline("opp-1") is None
