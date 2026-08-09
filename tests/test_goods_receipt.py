from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from app.application.goods_receipt import (
    AdmitGoodsReceipt,
    AdmitGoodsReceiptCommand,
    GoodsReceiptCumulativeQuantityConflictError,
    GoodsReceiptOpportunityConflictError,
    GoodsReceiptPublication,
    GoodsReceiptReplayConflictError,
    GoodsReceiptSourceNotFoundError,
    GoodsReceiptUnitConflictError,
)
from app.domain.capital import GoodsReceiptEvidenceReference
from app.infrastructure.goods_receipt import ProductionGoodsReceiptRecordIdentityGenerator
from test_purchase_execution import command as purchase_command
from test_purchase_execution import owner as purchase_owner
from test_purchase_execution import prepared as prepared_purchase


class MemoryGoodsReceiptRepository:
    def __init__(self, purchase):
        self.purchase = purchase
        self.records = {}
        self.results = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is not None and result.receipt.command_fingerprint != fingerprint:
            raise GoodsReceiptReplayConflictError("payload conflict")
        return result

    def get_purchase_execution_record(self, record_id):
        return self.purchase if self.purchase.record_id == record_id else None

    def get_cumulative_received_quantity(self, purchase_execution_record_id):
        return sum(
            value.received_quantity
            for value in self.records.values()
            if value.source_manifest.purchase_execution_record_id
            == purchase_execution_record_id
        )

    def save(self, command, record, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        cumulative = self.get_cumulative_received_quantity(
            record.source_manifest.purchase_execution_record_id
        )
        if cumulative + record.received_quantity > self.purchase.actual_quantity:
            raise GoodsReceiptCumulativeQuantityConflictError("over receipt")
        result = GoodsReceiptPublication(record, receipt, False)
        self.records[record.record_id] = record
        self.results[command.command_id] = result
        return result


def purchase():
    source = prepared_purchase()
    return purchase_owner(source).execute(purchase_command(source)).record


def command(record, **changes):
    received = changes.pop("received_quantity", record.actual_quantity)
    values = {
        "command_id": "goods-receipt-command-1",
        "opportunity_id": record.source_manifest.opportunity_identity.opportunity_id,
        "purchase_execution_record_id": record.record_id,
        "received_quantity": received,
        "quantity_unit": record.actual_quantity_unit,
        "sellable_quantity": received,
        "damaged_quantity": 0,
        "evidence_references": (
            GoodsReceiptEvidenceReference(
                "artifact://delivery/photo-1",
                record.executed_at + timedelta(minutes=1),
                "founder-1",
                "founder_inspection",
            ),
        ),
        "delivery_reference": "carrier-tracking-001",
        "operator_id": "founder-1",
        "received_at": record.executed_at + timedelta(minutes=1),
        "inspected_at": record.executed_at + timedelta(minutes=2),
        "requested_at": record.executed_at + timedelta(minutes=3),
    }
    values.update(changes)
    return AdmitGoodsReceiptCommand(**values)


def owner(repository, identity="goods-receipt-1", *, fail=False):
    def forbidden():
        raise AssertionError("dependency called during replay")

    return AdmitGoodsReceipt(
        repository,
        record_id_generator=forbidden if fail else lambda: identity,
        admitted_clock=(
            forbidden
            if fail
            else lambda: repository.purchase.executed_at + timedelta(minutes=4)
        ),
        committed_clock=(
            forbidden
            if fail
            else lambda: repository.purchase.executed_at + timedelta(minutes=5)
        ),
    )


def test_full_receipt_is_immutable_and_reconstructs_exact_purchase_lineage():
    record = purchase()
    repository = MemoryGoodsReceiptRepository(record)
    result = owner(repository).execute(command(record))
    receipt = result.record
    source = receipt.source_manifest
    assert result.replayed is False
    assert source.purchase_execution_record_id == record.record_id
    assert source.opportunity_identity == record.source_manifest.opportunity_identity
    assert source.supplier_id == record.source_manifest.supplier_id
    assert source.sourcing_product_id == record.source_manifest.sourcing_product_id
    assert source.external_product_reference == record.source_manifest.external_product_reference
    assert source.quote_id == record.source_manifest.quote_id
    assert source.quote_revision == record.source_manifest.quote_revision
    assert source.executed_quantity == record.actual_quantity
    assert receipt.received_quantity == record.actual_quantity
    assert receipt.sellable_quantity == record.actual_quantity
    assert receipt.damaged_quantity == 0
    assert receipt.delivery_reference == "carrier-tracking-001"
    assert receipt.evidence_references[0].collection_method == "founder_inspection"
    assert not hasattr(receipt, "state")
    assert not hasattr(receipt, "fulfilled")
    assert not hasattr(receipt, "inventory_balance")
    with pytest.raises(FrozenInstanceError):
        receipt.received_quantity = 0


def test_partial_multiple_receipts_and_damaged_condition_exactly_fill_purchase():
    record = purchase()
    assert record.actual_quantity >= 2
    repository = MemoryGoodsReceiptRepository(record)
    first_quantity = record.actual_quantity - 1
    first = owner(repository).execute(
        command(
            record,
            received_quantity=first_quantity,
            sellable_quantity=first_quantity - 1,
            damaged_quantity=1,
        )
    )
    second = owner(repository, "goods-receipt-2").execute(
        command(
            record,
            command_id="goods-receipt-command-2",
            received_quantity=1,
            sellable_quantity=1,
            damaged_quantity=0,
            delivery_reference=None,
        )
    )
    assert first.record.damaged_quantity == 1
    assert second.record.delivery_reference is None
    assert len(repository.records) == 2
    assert repository.get_cumulative_received_quantity(record.record_id) == record.actual_quantity
    with pytest.raises(GoodsReceiptCumulativeQuantityConflictError):
        owner(repository, "goods-receipt-3").execute(
            command(
                record,
                command_id="goods-receipt-command-3",
                received_quantity=1,
                sellable_quantity=1,
                damaged_quantity=0,
            )
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"received_quantity": 0, "sellable_quantity": 0},
        {"received_quantity": -1, "sellable_quantity": 0},
        {"received_quantity": 2, "sellable_quantity": 2, "damaged_quantity": 1},
        {"received_quantity": 2, "sellable_quantity": -1, "damaged_quantity": 3},
        {"received_quantity": True, "sellable_quantity": 1},
    ),
)
def test_quantity_contract_rejects_zero_negative_bool_and_condition_mismatch(changes):
    with pytest.raises(ValueError):
        command(purchase(), **changes)


def test_exact_unit_wrong_opportunity_missing_source_and_time_order_are_rejected():
    record = purchase()
    repository = MemoryGoodsReceiptRepository(record)
    with pytest.raises(GoodsReceiptUnitConflictError):
        owner(repository).execute(command(record, quantity_unit="case"))
    with pytest.raises(GoodsReceiptOpportunityConflictError):
        owner(repository).execute(command(record, opportunity_id="different-o2"))
    with pytest.raises(GoodsReceiptSourceNotFoundError):
        owner(repository).execute(
            command(record, purchase_execution_record_id="missing-purchase")
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        command(record, received_at=record.executed_at.replace(tzinfo=None))
    with pytest.raises(ValueError, match="cannot precede received"):
        command(
            record,
            inspected_at=record.executed_at,
            received_at=record.executed_at + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="cannot precede Purchase Execution"):
        owner(repository).execute(
            command(
                record,
                received_at=record.executed_at - timedelta(seconds=1),
                inspected_at=record.executed_at,
            )
        )


def test_exact_replay_precedes_source_cumulative_identity_and_clocks_and_change_conflicts():
    record = purchase()
    repository = MemoryGoodsReceiptRepository(record)
    request = command(record)
    first = owner(repository).execute(request)
    repository.purchase = None
    replay = owner(repository, fail=True).execute(request)
    assert replay.replayed is True
    assert replay.record is first.record
    assert replay.receipt is first.receipt
    with pytest.raises(GoodsReceiptReplayConflictError):
        owner(repository, fail=True).execute(replace(request, delivery_reference="changed"))


def test_goods_receipt_has_no_actual_settlement_prerequisite_or_inventory_side_effect():
    record = purchase()
    repository = MemoryGoodsReceiptRepository(record)
    assert not hasattr(repository, "get_actual_acquisition_settlement")
    result = owner(repository).execute(command(record))
    assert result.record.source_manifest.purchase_execution_record_id == record.record_id
    assert not hasattr(result.record, "actual_acquisition_settlement_id")
    assert not hasattr(result.record, "inventory_snapshot")


def test_production_goods_receipt_identity_is_stateless_uuid4_hex():
    identity = ProductionGoodsReceiptRecordIdentityGenerator()
    first, second = identity(), identity()
    assert first != second
    assert len(first) == len(second) == 32
    assert all(character in "0123456789abcdef" for character in first + second)
