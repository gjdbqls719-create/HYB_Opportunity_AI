from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.actual_acquisition_settlement import (
    ActualAcquisitionSettlementOpportunityConflictError,
    ActualAcquisitionSettlementPublication,
    ActualAcquisitionSettlementReplayConflictError,
    ActualAcquisitionSettlementRevisionConflictError,
    ActualAcquisitionSettlementTerminalConflictError,
    AdmitActualAcquisitionSettlement,
    AdmitActualAcquisitionSettlementCommand,
)
from app.domain.capital import (
    ACTUAL_ACQUISITION_DECIMAL_PRECISION,
    ActualAcquisitionBlockingReason,
    ActualAcquisitionCostCategory,
    ActualAcquisitionCostFact,
    ActualAcquisitionEvidenceReference,
    ActualAcquisitionFXSettlement,
    ActualAcquisitionFactAvailability,
    ActualAcquisitionSettlementState,
    OtherMandatoryAcquisitionCosts,
    OtherMandatoryAcquisitionCostItem,
)
from app.domain.sourcing import FXObservation
from app.infrastructure.actual_acquisition_settlement import (
    ProductionActualAcquisitionSettlementIdentityGenerator,
)
from test_purchase_execution import command as purchase_command
from test_purchase_execution import owner as purchase_owner
from test_purchase_execution import prepared as prepared_purchase


class MemorySettlementRepository:
    def __init__(self, purchase):
        self.purchase = purchase
        self.settlements = {}
        self.receipts = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.receipts.get(command_id)
        if result is not None and result.receipt.command_fingerprint != fingerprint:
            raise ActualAcquisitionSettlementReplayConflictError("payload conflict")
        return result

    def get_purchase_execution_record(self, record_id):
        return self.purchase if self.purchase.record_id == record_id else None

    def get_settlement(self, settlement_id):
        return self.settlements.get(settlement_id)

    def get_chain_tip_for_cardinality(self, purchase_execution_record_id):
        values = [
            value
            for value in self.settlements.values()
            if value.source_manifest.purchase_execution_record_id
            == purchase_execution_record_id
        ]
        return max(values, key=lambda value: value.revision) if values else None

    def save(self, command, settlement, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        tip = self.get_chain_tip_for_cardinality(
            settlement.source_manifest.purchase_execution_record_id
        )
        if tip is not None:
            if tip.state is ActualAcquisitionSettlementState.COMPLETE:
                raise ActualAcquisitionSettlementTerminalConflictError("terminal")
            if settlement.predecessor_settlement_id != tip.settlement_id:
                raise ActualAcquisitionSettlementRevisionConflictError("fork")
        elif settlement.revision != 1:
            raise ActualAcquisitionSettlementRevisionConflictError("missing root")
        result = ActualAcquisitionSettlementPublication(settlement, receipt, False)
        self.settlements[settlement.settlement_id] = settlement
        self.receipts[command.command_id] = result
        return result


def purchase():
    source = prepared_purchase()
    return purchase_owner(source).execute(purchase_command(source)).record


def evidence(reference="artifact://actual/1", operator="founder-1"):
    return ActualAcquisitionEvidenceReference(
        reference,
        purchase().executed_at + timedelta(minutes=1),
        operator,
        "founder_statement_review",
    )


def known(category, amount="0", currency="KRW", *, fx=None, suffix="1"):
    return ActualAcquisitionCostFact(
        category,
        ActualAcquisitionFactAvailability.KNOWN,
        Decimal(amount),
        currency,
        purchase().executed_at + timedelta(minutes=1),
        evidence(f"artifact://actual/{category.value}/{suffix}"),
        actual_fx=fx,
    )


def not_applicable(category, suffix="na"):
    return ActualAcquisitionCostFact(
        category,
        ActualAcquisitionFactAvailability.NOT_APPLICABLE,
        evidence=evidence(f"artifact://actual/{category.value}/{suffix}"),
    )


def unknown(category):
    return ActualAcquisitionCostFact(
        category,
        ActualAcquisitionFactAvailability.UNKNOWN,
        unresolved_reason="invoice not final",
    )


def complete_facts(*, unit_amount="9000"):
    return (
        known(ActualAcquisitionCostCategory.UNIT_PURCHASE, unit_amount),
        known(ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING, "1000"),
        not_applicable(ActualAcquisitionCostCategory.INTERNATIONAL_FREIGHT),
        known(ActualAcquisitionCostCategory.DOMESTIC_INBOUND, "0"),
        not_applicable(ActualAcquisitionCostCategory.DUTY_CUSTOMS),
    )


def no_other():
    return OtherMandatoryAcquisitionCosts(
        ActualAcquisitionFactAvailability.NOT_APPLICABLE,
        (),
        evidence("artifact://actual/other/none"),
    )


def request(record, **changes):
    values = {
        "command_id": "actual-settlement-command-1",
        "opportunity_id": record.source_manifest.opportunity_identity.opportunity_id,
        "purchase_execution_record_id": record.record_id,
        "predecessor_settlement_id": None,
        "target_currency": "KRW",
        "fixed_cost_facts": complete_facts(),
        "other_mandatory_costs": no_other(),
        "operator_id": "founder-1",
        "requested_at": record.executed_at + timedelta(minutes=2),
    }
    values.update(changes)
    return AdmitActualAcquisitionSettlementCommand(**values)


def authority(repository, identity="actual-settlement-1", *, fail=False):
    def forbidden():
        raise AssertionError("dependency called during replay")

    return AdmitActualAcquisitionSettlement(
        repository,
        settlement_id_generator=forbidden if fail else lambda: identity,
        admitted_clock=forbidden if fail else lambda: repository.purchase.executed_at + timedelta(minutes=3),
        committed_clock=forbidden if fail else lambda: repository.purchase.executed_at + timedelta(minutes=4),
    )


def test_complete_same_currency_derives_batch_and_per_unit_without_fake_fx():
    record = purchase()
    repository = MemorySettlementRepository(record)
    result = authority(repository).execute(request(record))
    settlement = result.settlement
    assert settlement.state is ActualAcquisitionSettlementState.COMPLETE
    assert settlement.blocking_reasons == ()
    assert settlement.acquisition_batch_total == Decimal("10000")
    assert settlement.acquisition_per_unit == Decimal("10000") / Decimal(record.actual_quantity)
    assert all(value.actual_fx is None for value in settlement.fixed_cost_facts)
    assert settlement.policy_precision == ACTUAL_ACQUISITION_DECIMAL_PRECISION


def test_complete_cross_currency_preserves_actual_fx_and_original_amount():
    record = purchase()
    fx_evidence = evidence("artifact://card-charge/1")
    fx = ActualAcquisitionFXSettlement(
        "CNY", "KRW", Decimal("10"), Decimal("1900"), Decimal("190"),
        "card-provider", "corporate-card", "charge-1",
        record.executed_at + timedelta(minutes=1), fx_evidence,
    )
    facts = list(complete_facts())
    facts[0] = known(ActualAcquisitionCostCategory.UNIT_PURCHASE, "10", "CNY", fx=fx)
    repository = MemorySettlementRepository(record)
    settlement = authority(repository).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    assert settlement.state is ActualAcquisitionSettlementState.COMPLETE
    assert settlement.fixed_cost_facts[0].amount == Decimal("10")
    assert settlement.normalized_categories[0].target_batch_amount == Decimal("1900")
    assert not isinstance(fx, FXObservation)


@pytest.mark.parametrize(
    ("index", "reason"),
    (
        (0, ActualAcquisitionBlockingReason.UNIT_PURCHASE_UNKNOWN),
        (1, ActualAcquisitionBlockingReason.SUPPLIER_SIDE_SHIPPING_UNKNOWN),
        (4, ActualAcquisitionBlockingReason.DUTY_CUSTOMS_UNKNOWN),
    ),
)
def test_unknown_fixed_fact_is_blocked_without_totals(index, reason):
    record = purchase()
    facts = list(complete_facts())
    facts[index] = unknown(facts[index].category)
    settlement = authority(MemorySettlementRepository(record)).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    assert settlement.state is ActualAcquisitionSettlementState.BLOCKED
    assert reason in settlement.blocking_reasons
    assert settlement.acquisition_batch_total is None
    assert settlement.acquisition_per_unit is None


def test_unresolved_other_scope_and_missing_or_mismatched_fx_are_distinct():
    record = purchase()
    unresolved = OtherMandatoryAcquisitionCosts(
        ActualAcquisitionFactAvailability.UNKNOWN,
        (),
        None,
        "customs broker invoice pending",
    )
    first = authority(MemorySettlementRepository(record)).execute(
        request(record, other_mandatory_costs=unresolved)
    ).settlement
    assert first.blocking_reasons == (
        ActualAcquisitionBlockingReason.OTHER_MANDATORY_COST_SCOPE_UNRESOLVED,
    )

    facts = list(complete_facts())
    facts[0] = known(ActualAcquisitionCostCategory.UNIT_PURCHASE, "10", "CNY")
    second = authority(MemorySettlementRepository(record)).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    assert second.blocking_reasons == (ActualAcquisitionBlockingReason.ACTUAL_FX_MISSING,)

    wrong = ActualAcquisitionFXSettlement(
        "USD", "KRW", Decimal("10"), Decimal("14000"), Decimal("1400"),
        "bank", None, "wire-1", record.executed_at + timedelta(minutes=1),
        evidence("artifact://wire/1"),
    )
    facts[0] = known(ActualAcquisitionCostCategory.UNIT_PURCHASE, "10", "CNY", fx=wrong)
    third = authority(MemorySettlementRepository(record)).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    assert third.blocking_reasons == (ActualAcquisitionBlockingReason.ACTUAL_FX_MISMATCH,)


def test_explicit_zero_and_not_applicable_remain_distinct():
    facts = complete_facts()
    assert facts[2].availability is ActualAcquisitionFactAvailability.NOT_APPLICABLE
    assert facts[2].amount is None
    assert facts[3].availability is ActualAcquisitionFactAvailability.KNOWN
    assert facts[3].amount == Decimal("0")


def test_ordered_other_items_are_preserved_and_aggregated():
    record = purchase()
    items = (
        OtherMandatoryAcquisitionCostItem(
            "payment_provider_fee", Decimal("10"), "KRW",
            record.executed_at + timedelta(minutes=1), evidence("artifact://fee/1"),
        ),
        OtherMandatoryAcquisitionCostItem(
            "inspection_fee", Decimal("20"), "KRW",
            record.executed_at + timedelta(minutes=1), evidence("artifact://fee/2"),
        ),
    )
    other = OtherMandatoryAcquisitionCosts(
        ActualAcquisitionFactAvailability.KNOWN,
        items,
        evidence("artifact://other/scope-complete"),
    )
    settlement = authority(MemorySettlementRepository(record)).execute(
        request(record, other_mandatory_costs=other)
    ).settlement
    assert tuple(value.scope for value in settlement.other_mandatory_costs.items) == (
        "payment_provider_fee", "inspection_fee"
    )
    assert settlement.normalized_categories[-1].target_batch_amount == Decimal("30")


def test_actual_item_may_differ_from_purchase_committed_amount_without_mutating_purchase():
    record = purchase()
    original = record.actual_total_committed_amount
    settlement = authority(MemorySettlementRepository(record)).execute(
        request(record, fixed_cost_facts=complete_facts(unit_amount="1"))
    ).settlement
    assert settlement.fixed_cost_facts[0].amount == Decimal("1")
    assert record.actual_total_committed_amount == original
    assert settlement.fixed_cost_facts[0].amount != original


def test_exact_lineage_wrong_opportunity_and_immutability():
    record = purchase()
    repository = MemorySettlementRepository(record)
    settlement = authority(repository).execute(request(record)).settlement
    source = settlement.source_manifest
    assert source.purchase_execution_record_id == record.record_id
    assert source.supplier_id == record.source_manifest.supplier_id
    assert source.sourcing_product_id == record.source_manifest.sourcing_product_id
    assert source.quote_id == record.source_manifest.quote_id
    assert source.executed_quantity == record.actual_quantity
    with pytest.raises(FrozenInstanceError):
        settlement.state = ActualAcquisitionSettlementState.BLOCKED
    with pytest.raises(ActualAcquisitionSettlementOpportunityConflictError):
        authority(MemorySettlementRepository(record)).execute(
            request(record, opportunity_id="wrong-o2")
        )


def test_exact_replay_precedes_identity_and_changed_payload_conflicts():
    record = purchase()
    repository = MemorySettlementRepository(record)
    command = request(record)
    first = authority(repository).execute(command)
    replay = authority(repository, fail=True).execute(command)
    assert replay.replayed is True
    assert replay.settlement is first.settlement
    with pytest.raises(ActualAcquisitionSettlementReplayConflictError):
        authority(repository).execute(replace(command, target_currency="USD"))


def test_blocked_to_complete_revision_is_linear_and_complete_is_terminal():
    record = purchase()
    repository = MemorySettlementRepository(record)
    facts = list(complete_facts())
    facts[1] = unknown(ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING)
    blocked = authority(repository).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    complete = authority(repository, "actual-settlement-2").execute(
        request(
            record,
            command_id="actual-settlement-command-2",
            predecessor_settlement_id=blocked.settlement_id,
        )
    ).settlement
    assert blocked.revision == 1
    assert complete.revision == 2
    assert complete.predecessor_settlement_id == blocked.settlement_id
    assert complete.state is ActualAcquisitionSettlementState.COMPLETE
    with pytest.raises(ActualAcquisitionSettlementTerminalConflictError):
        authority(repository, "actual-settlement-3").execute(
            request(
                record,
                command_id="actual-settlement-command-3",
                predecessor_settlement_id=complete.settlement_id,
            )
        )


def test_existing_chain_requires_exact_tip_and_cannot_fork():
    record = purchase()
    repository = MemorySettlementRepository(record)
    facts = list(complete_facts())
    facts[0] = unknown(ActualAcquisitionCostCategory.UNIT_PURCHASE)
    facts[1] = unknown(ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING)
    root = authority(repository).execute(
        request(record, fixed_cost_facts=tuple(facts))
    ).settlement
    with pytest.raises(ActualAcquisitionSettlementRevisionConflictError):
        authority(repository, "missing-predecessor").execute(
            request(record, command_id="command-without-predecessor")
        )
    child_facts = list(complete_facts())
    child_facts[1] = unknown(ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING)
    child = authority(repository, "child-1").execute(
        request(
            record,
            command_id="child-command-1",
            predecessor_settlement_id=root.settlement_id,
            fixed_cost_facts=tuple(child_facts),
        )
    ).settlement
    assert child.revision == 2
    with pytest.raises(ActualAcquisitionSettlementRevisionConflictError):
        authority(repository, "fork-child").execute(
            request(
                record,
                command_id="fork-command",
                predecessor_settlement_id=root.settlement_id,
                fixed_cost_facts=tuple(child_facts),
            )
        )


def test_structural_fx_contradiction_and_duplicate_other_scope_are_rejected():
    record = purchase()
    with pytest.raises(ValueError, match="contradicts"):
        ActualAcquisitionFXSettlement(
            "CNY", "KRW", Decimal("10"), Decimal("999"), Decimal("190"),
            "provider", None, "bad", record.executed_at,
            evidence("artifact://bad-fx"),
        )
    item = OtherMandatoryAcquisitionCostItem(
        "fee", Decimal("1"), "KRW", record.executed_at, evidence("artifact://fee")
    )
    with pytest.raises(ValueError, match="unique"):
        OtherMandatoryAcquisitionCosts(
            ActualAcquisitionFactAvailability.KNOWN,
            (item, item),
            evidence("artifact://scope"),
        )


def test_production_settlement_identity_is_stateless_uuid4_hex():
    identity = ProductionActualAcquisitionSettlementIdentityGenerator()
    first, second = identity(), identity()
    assert first != second
    assert len(first) == len(second) == 32
    assert all(character in "0123456789abcdef" for character in first + second)
