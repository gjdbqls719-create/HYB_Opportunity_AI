from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from app.application.owned_inventory import (
    GetOwnedInventoryPositions,
    OwnedInventoryOpportunityNotFoundError,
    OwnedInventorySourceConflictError,
)
from app.domain.capital import (
    OWNED_INVENTORY_POLICY_NAME,
    OWNED_INVENTORY_POLICY_VERSION,
    OWNED_INVENTORY_POSITION_SCHEMA_VERSION,
    GoodsReceiptEvidenceReference,
    GoodsReceiptRecord,
    GoodsReceiptSourceManifest,
    OwnedInventoryPosition,
)
from app.domain.decision_engine import OpportunityIdentity


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
O2 = OpportunityIdentity("o2-1", "domestic-selling:o1-1")


def _receipt(
    record_id: str,
    *,
    purchase_id: str = "purchase-1",
    identity: OpportunityIdentity = O2,
    supplier_id: str = "supplier-1",
    sourcing_product_id: str = "product-1",
    external_product_reference: str = "external-product-1",
    option_reference: str | None = "black",
    sku_reference: str | None = "sku-a",
    quantity_unit: str = "unit",
    received: int = 10,
    sellable: int = 10,
    damaged: int = 0,
    received_at: datetime = NOW,
) -> GoodsReceiptRecord:
    return GoodsReceiptRecord(
        record_id=record_id,
        source_manifest=GoodsReceiptSourceManifest(
            opportunity_identity=identity,
            purchase_execution_record_id=purchase_id,
            real_money_execution_intent_id=f"intent-{purchase_id}",
            sourcing_admission_id="sourcing-1",
            sourcing_admission_revision=1,
            supplier_id=supplier_id,
            source_platform="1688",
            external_supplier_reference="shop-1",
            sourcing_product_id=sourcing_product_id,
            external_product_reference=external_product_reference,
            option_reference=option_reference,
            sku_reference=sku_reference,
            quote_id=f"quote-{purchase_id}",
            quote_revision=1,
            executed_quantity=100,
            executed_quantity_unit=quantity_unit,
            external_order_reference=f"order-{purchase_id}",
            founder_id="founder-1",
            purchase_executed_at=NOW - timedelta(days=1),
            purchase_policy_name="purchase-policy",
            purchase_policy_version="1.0.0",
            purchase_record_schema_version="purchase-record-v1",
        ),
        received_quantity=received,
        quantity_unit=quantity_unit,
        sellable_quantity=sellable,
        damaged_quantity=damaged,
        evidence_references=(
            GoodsReceiptEvidenceReference(
                reference=f"artifact://receipt/{record_id}",
                observed_at=received_at,
                operator_id="founder-1",
                collection_method="inspection",
            ),
        ),
        delivery_reference=None,
        operator_id="founder-1",
        received_at=received_at,
        inspected_at=received_at,
        requested_at=received_at,
        admitted_at=received_at,
    )


class MemoryOwnedInventoryRepository:
    def __init__(
        self,
        records: tuple[GoodsReceiptRecord, ...] = (),
        identity: OpportunityIdentity | None = O2,
    ) -> None:
        self.records = records
        self.identity = identity
        self.calls: list[tuple[str, str]] = []

    def get_opportunity_identity(self, opportunity_id: str):
        self.calls.append(("opportunity", opportunity_id))
        return self.identity

    def list_goods_receipts_for_opportunity(self, opportunity_id: str):
        self.calls.append(("receipts", opportunity_id))
        return self.records


def test_missing_opportunity_fails_before_receipt_enumeration():
    repository = MemoryOwnedInventoryRepository(identity=None)

    with pytest.raises(OwnedInventoryOpportunityNotFoundError):
        GetOwnedInventoryPositions(repository).execute("missing-o2")

    assert repository.calls == [("opportunity", "missing-o2")]


def test_existing_opportunity_without_receipts_returns_empty_positions():
    repository = MemoryOwnedInventoryRepository()

    assert GetOwnedInventoryPositions(repository).execute(O2.opportunity_id) == ()
    assert repository.calls == [
        ("opportunity", O2.opportunity_id),
        ("receipts", O2.opportunity_id),
    ]


def test_single_full_receipt_builds_immutable_versioned_position():
    result = GetOwnedInventoryPositions(
        MemoryOwnedInventoryRepository((_receipt("receipt-1"),))
    ).execute(O2.opportunity_id)

    assert len(result) == 1
    position = result[0]
    assert isinstance(position, OwnedInventoryPosition)
    assert position.product_key.opportunity_identity == O2
    assert position.total_received == 10
    assert position.total_sellable_received == 10
    assert position.total_damaged_received == 0
    assert position.total_outbound_quantity == 0
    assert position.sellable_on_hand == 10
    assert position.contributing_purchase_execution_ids == ("purchase-1",)
    assert position.contributing_goods_receipt_ids == ("receipt-1",)
    assert position.source_event_count == 1
    assert position.policy_name == OWNED_INVENTORY_POLICY_NAME
    assert position.policy_version == OWNED_INVENTORY_POLICY_VERSION
    assert position.schema_version == OWNED_INVENTORY_POSITION_SCHEMA_VERSION
    with pytest.raises(FrozenInstanceError):
        position.sellable_on_hand = 9
    with pytest.raises(ValueError, match="no authoritative outbound"):
        replace(position, total_outbound_quantity=1, sellable_on_hand=9)
    with pytest.raises(ValueError, match="unsupported Owned Inventory policy"):
        replace(position, policy_version="caller-selected")


def test_partial_damaged_receipts_are_aggregated_in_factual_event_order():
    later = _receipt(
        "receipt-b",
        received=40,
        sellable=40,
        received_at=NOW + timedelta(hours=1),
    )
    earlier = _receipt(
        "receipt-a", received=60, sellable=58, damaged=2, received_at=NOW
    )

    position = GetOwnedInventoryPositions(
        MemoryOwnedInventoryRepository((later, earlier))
    ).execute(O2.opportunity_id)[0]

    assert position.total_received == 100
    assert position.total_sellable_received == 98
    assert position.total_damaged_received == 2
    assert position.total_outbound_quantity == 0
    assert position.sellable_on_hand == 98
    assert position.contributing_goods_receipt_ids == ("receipt-a", "receipt-b")
    assert position.contributing_purchase_execution_ids == ("purchase-1",)


def test_multiple_purchases_same_key_aggregate_but_sku_and_supplier_do_not():
    same_a = _receipt("receipt-a", purchase_id="purchase-a", sellable=10)
    same_b = _receipt(
        "receipt-b",
        purchase_id="purchase-b",
        received=20,
        sellable=20,
        received_at=NOW + timedelta(minutes=1),
    )
    sku_b = _receipt(
        "receipt-c",
        purchase_id="purchase-c",
        sku_reference="sku-b",
        received=7,
        sellable=7,
    )
    supplier_b = _receipt(
        "receipt-d",
        purchase_id="purchase-d",
        supplier_id="supplier-2",
        sourcing_product_id="product-2",
        external_product_reference="external-product-2",
        received=5,
        sellable=5,
    )

    positions = GetOwnedInventoryPositions(
        MemoryOwnedInventoryRepository((supplier_b, sku_b, same_b, same_a))
    ).execute(O2.opportunity_id)

    assert len(positions) == 3
    primary = next(value for value in positions if value.product_key.sku_reference == "sku-a" and value.product_key.supplier_id == "supplier-1")
    assert primary.sellable_on_hand == 30
    assert primary.contributing_purchase_execution_ids == ("purchase-a", "purchase-b")
    assert primary.contributing_goods_receipt_ids == ("receipt-a", "receipt-b")
    assert next(value for value in positions if value.product_key.sku_reference == "sku-b").sellable_on_hand == 7
    assert next(value for value in positions if value.product_key.supplier_id == "supplier-2").sellable_on_hand == 5
    assert positions == tuple(sorted(positions, key=lambda value: value.product_key.sort_key))


def test_missing_option_and_concrete_option_are_distinct_and_unit_is_exact():
    missing = _receipt("receipt-none", option_reference=None, sku_reference=None)
    concrete = _receipt("receipt-option", option_reference="black", sku_reference=None)
    case = _receipt("receipt-case", option_reference=None, sku_reference=None, quantity_unit="case")

    positions = GetOwnedInventoryPositions(
        MemoryOwnedInventoryRepository((case, concrete, missing))
    ).execute(O2.opportunity_id)

    assert len(positions) == 3
    assert {value.quantity_unit for value in positions} == {"unit", "case"}


def test_repeated_projection_is_identical_and_does_not_use_unrelated_authorities():
    records = (_receipt("receipt-1"),)
    service = GetOwnedInventoryPositions(MemoryOwnedInventoryRepository(records))

    assert service.execute(O2.opportunity_id) == service.execute(O2.opportunity_id)
    import inspect
    import app.application.owned_inventory as module

    source = inspect.getsource(module)
    assert "app.infrastructure" not in source
    assert "latest" not in source.lower()
    assert "InventorySnapshot" not in source
    assert "ActualAcquisitionSettlement" not in source
    assert "actual_economics" not in source


def test_duplicate_receipt_identity_fails_closed():
    duplicate = _receipt("receipt-1")
    repository = MemoryOwnedInventoryRepository((duplicate, duplicate))

    with pytest.raises(OwnedInventorySourceConflictError):
        GetOwnedInventoryPositions(repository).execute(O2.opportunity_id)


def test_receipt_from_different_opportunity_identity_fails_closed():
    other = OpportunityIdentity(O2.opportunity_id, "different-discovery-reference")
    repository = MemoryOwnedInventoryRepository((_receipt("receipt-1", identity=other),))

    with pytest.raises(OwnedInventorySourceConflictError):
        GetOwnedInventoryPositions(repository).execute(O2.opportunity_id)
