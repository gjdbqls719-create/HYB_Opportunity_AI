from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from app.application.owned_inventory import (
    GetOwnedInventoryPositions,
    GetOwnedInventoryPositionsV2,
    OwnedInventorySourceConflictError,
)
from app.domain.capital import (
    ActualSaleMonetaryCategory,
    ActualSaleSettlementState,
    OWNED_INVENTORY_V2_POLICY_NAME,
    OWNED_INVENTORY_V2_POLICY_VERSION,
    OWNED_INVENTORY_V2_POSITION_SCHEMA_VERSION,
)
from test_actual_sale_settlement import MemorySaleRepository, command as sale_command
from test_actual_sale_settlement import complete_facts, owner as sale_owner, unknown
from test_owned_inventory import MemoryOwnedInventoryRepository, O2, NOW, _receipt


class MemoryOwnedInventoryV2Repository(MemoryOwnedInventoryRepository):
    def __init__(self, records=(), sales=(), identity=O2):
        super().__init__(records, identity)
        self.sales = sales

    def list_complete_actual_sale_settlements_for_opportunity(self, opportunity_id):
        self.calls.append(("sales", opportunity_id))
        return tuple(
            value
            for value in self.sales
            if value.state is ActualSaleSettlementState.COMPLETE
        )


def _sale(receipt, *, identity="sale-1", **changes):
    request = sale_command(receipt, **changes)
    repository = MemorySaleRepository(receipt)
    return sale_owner(repository, request, identity=identity).execute(request).settlement


def test_v2_authority_is_explicitly_versioned():
    assert GetOwnedInventoryPositionsV2 is not None
    assert OWNED_INVENTORY_V2_POLICY_NAME == (
        "receipt-and-complete-sale-derived-owned-inventory"
    )
    assert OWNED_INVENTORY_V2_POLICY_VERSION == "2.0.0"
    assert OWNED_INVENTORY_V2_POSITION_SCHEMA_VERSION == "owned-inventory-position-v2"


def test_receipt_only_v2_preserves_v1_semantics_without_reinterpreting_v1():
    receipt = _receipt("receipt-1", received=10, sellable=7, damaged=3)
    repository = MemoryOwnedInventoryV2Repository((receipt,))
    v2 = GetOwnedInventoryPositionsV2(repository).execute(O2.opportunity_id)[0]
    v1 = GetOwnedInventoryPositions(repository).execute(O2.opportunity_id)[0]

    assert (v2.total_received, v2.total_sellable_received, v2.total_damaged_received) == (10, 7, 3)
    assert (v2.total_outbound_quantity, v2.sellable_on_hand) == (0, 7)
    assert v2.contributing_actual_sale_settlement_ids == ()
    assert (v2.inbound_source_event_count, v2.outbound_source_event_count) == (1, 0)
    assert (v1.policy_name, v1.policy_version, v1.schema_version) == (
        "receipt-derived-owned-inventory", "1.0.0", "owned-inventory-position-v1"
    )


def test_complete_sale_is_subtracted_and_sources_are_immutable():
    receipt = _receipt("receipt-1", received=10, sellable=10)
    settlement = _sale(receipt, fulfilled_outbound_quantity=4)
    position = GetOwnedInventoryPositionsV2(
        MemoryOwnedInventoryV2Repository((receipt,), (settlement,))
    ).execute(O2.opportunity_id)[0]

    assert (position.total_outbound_quantity, position.sellable_on_hand) == (4, 6)
    assert position.contributing_actual_sale_settlement_ids == ("sale-1",)
    assert position.outbound_source_event_count == 1
    with pytest.raises(FrozenInstanceError):
        position.sellable_on_hand = 5


def test_blocked_sale_is_excluded_then_complete_child_contributes():
    receipt = _receipt("receipt-1", received=10, sellable=10)
    facts = list(complete_facts())
    facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    blocked = _sale(
        receipt,
        identity="blocked-sale",
        fulfilled_outbound_quantity=8,
        fixed_monetary_facts=tuple(facts),
    )
    repository = MemoryOwnedInventoryV2Repository((receipt,), (blocked,))
    before = GetOwnedInventoryPositionsV2(repository).execute(O2.opportunity_id)[0]
    assert (before.total_outbound_quantity, before.sellable_on_hand) == (0, 10)

    complete = _sale(receipt, identity="complete-sale", fulfilled_outbound_quantity=4)
    repository.sales = (blocked, complete)
    after = GetOwnedInventoryPositionsV2(repository).execute(O2.opportunity_id)[0]
    assert (after.total_outbound_quantity, after.sellable_on_hand) == (4, 6)
    assert after.contributing_actual_sale_settlement_ids == ("complete-sale",)


def test_zero_sale_and_multiple_windows_preserve_deterministic_sale_sources():
    receipt = _receipt("receipt-1", received=20, sellable=20)
    base = sale_command(receipt)
    zero = _sale(receipt, identity="sale-zero", fulfilled_outbound_quantity=0)
    later = _sale(
        receipt,
        identity="sale-later",
        command_id="sale-command-later",
        external_report_reference="report-later",
        transaction_references=("order-later",),
        period_start=base.period_end,
        period_end=base.period_end + timedelta(days=1),
        requested_at=base.period_end + timedelta(days=1, minutes=1),
        finality=replace(base.finality, observed_at=base.period_end + timedelta(days=1)),
        fulfilled_outbound_quantity=6,
    )
    first = _sale(receipt, identity="sale-first", fulfilled_outbound_quantity=4)
    position = GetOwnedInventoryPositionsV2(
        MemoryOwnedInventoryV2Repository((receipt,), (later, zero, first))
    ).execute(O2.opportunity_id)[0]
    assert (position.total_outbound_quantity, position.sellable_on_hand) == (10, 10)
    assert position.contributing_actual_sale_settlement_ids == (
        "sale-first", "sale-zero", "sale-later"
    )
    assert position.outbound_source_event_count == 3


def test_multiple_purchases_and_variants_are_exactly_separated():
    first = _receipt("receipt-a", purchase_id="purchase-a", received=10, sellable=10)
    second = _receipt(
        "receipt-b", purchase_id="purchase-b", received=20, sellable=20,
        received_at=NOW + timedelta(minutes=1)
    )
    sku_b = _receipt("receipt-c", sku_reference="sku-b", received=8, sellable=8)
    sale_a = _sale(first, identity="sale-a", fulfilled_outbound_quantity=4)
    sale_b = _sale(
        sku_b, identity="sale-b", command_id="sale-b-command",
        external_report_reference="sale-b-report", transaction_references=("sale-b-order",),
        fulfilled_outbound_quantity=3,
    )
    positions = GetOwnedInventoryPositionsV2(
        MemoryOwnedInventoryV2Repository((second, sku_b, first), (sale_b, sale_a))
    ).execute(O2.opportunity_id)
    primary = next(value for value in positions if value.product_key.sku_reference == "sku-a")
    variant = next(value for value in positions if value.product_key.sku_reference == "sku-b")
    assert (primary.total_sellable_received, primary.sellable_on_hand) == (30, 26)
    assert primary.contributing_purchase_execution_ids == ("purchase-a", "purchase-b")
    assert (variant.total_sellable_received, variant.sellable_on_hand) == (8, 5)


def test_unmatched_or_negative_complete_outbound_fails_closed():
    receipt = _receipt("receipt-a", received=10, sellable=10)
    other = _receipt("receipt-b", sku_reference="sku-b", received=10, sellable=10)
    unmatched = _sale(other, fulfilled_outbound_quantity=1)
    with pytest.raises(OwnedInventorySourceConflictError, match="no matching"):
        GetOwnedInventoryPositionsV2(
            MemoryOwnedInventoryV2Repository((receipt,), (unmatched,))
        ).execute(O2.opportunity_id)

    oversold = replace(_sale(receipt, fulfilled_outbound_quantity=1), fulfilled_outbound_quantity=11)
    with pytest.raises(OwnedInventorySourceConflictError, match="negative"):
        GetOwnedInventoryPositionsV2(
            MemoryOwnedInventoryV2Repository((receipt,), (oversold,))
        ).execute(O2.opportunity_id)


def test_repeated_v2_read_is_identical_and_calls_only_receipts_and_complete_sales():
    receipt = _receipt("receipt-1")
    sale = _sale(receipt, fulfilled_outbound_quantity=2)
    repository = MemoryOwnedInventoryV2Repository((receipt,), (sale,))
    query = GetOwnedInventoryPositionsV2(repository)
    assert query.execute(O2.opportunity_id) == query.execute(O2.opportunity_id)
    assert {name for name, _ in repository.calls} == {"opportunity", "receipts", "sales"}
