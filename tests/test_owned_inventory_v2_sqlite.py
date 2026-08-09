from dataclasses import replace
from datetime import timedelta

from app.application.owned_inventory import GetOwnedInventoryPositionsV2
from app.domain.capital import ActualSaleMonetaryCategory, ActualSaleSettlementState
from app.infrastructure.actual_sale_settlement import SQLiteActualSaleSettlementRepository
from test_actual_sale_settlement import complete_facts, command as sale_command, owner as sale_owner, unknown
from test_actual_sale_settlement_sqlite import seed


def test_complete_enumeration_excludes_blocked_and_v2_read_is_pure_and_rebuildable(tmp_path):
    path = tmp_path / "owned-inventory-v2.sqlite3"
    _, receipt = seed(path)
    facts = list(complete_facts())
    facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    blocked_request = sale_command(
        receipt, fulfilled_outbound_quantity=8, fixed_monetary_facts=tuple(facts)
    )
    with SQLiteActualSaleSettlementRepository(path) as repository:
        blocked = sale_owner(repository, blocked_request, identity="blocked").execute(
            blocked_request
        ).settlement
        before_changes = repository._connection.total_changes
        before = GetOwnedInventoryPositionsV2(repository).execute(
            receipt.source_manifest.opportunity_identity.opportunity_id
        )[0]
        assert repository._connection.total_changes == before_changes
        assert before.total_outbound_quantity == 0
        assert before.contributing_actual_sale_settlement_ids == ()

        complete_request = sale_command(
            receipt,
            command_id="complete-command",
            predecessor_settlement_id=blocked.settlement_id,
            fulfilled_outbound_quantity=4,
        )
        complete = sale_owner(
            repository, complete_request, identity="complete"
        ).execute(complete_request).settlement
        assert complete.state is ActualSaleSettlementState.COMPLETE
        changes_after_write = repository._connection.total_changes
        first = GetOwnedInventoryPositionsV2(repository).execute(
            receipt.source_manifest.opportunity_identity.opportunity_id
        )[0]
        second = GetOwnedInventoryPositionsV2(repository).execute(
            receipt.source_manifest.opportunity_identity.opportunity_id
        )[0]
        assert first == second
        assert repository._connection.total_changes == changes_after_write
        assert first.total_outbound_quantity == 4
        assert first.sellable_on_hand == receipt.sellable_quantity - 4
        assert first.contributing_actual_sale_settlement_ids == ("complete",)

    with SQLiteActualSaleSettlementRepository(path) as restarted:
        rebuilt = GetOwnedInventoryPositionsV2(restarted).execute(
            receipt.source_manifest.opportunity_identity.opportunity_id
        )[0]
        assert rebuilt == first
        assert restarted.list_complete_actual_sale_settlements_for_opportunity(
            receipt.source_manifest.opportunity_identity.opportunity_id
        ) == (complete,)


def test_zero_complete_is_enumerated_in_period_end_then_id_order(tmp_path):
    path = tmp_path / "owned-inventory-v2-order.sqlite3"
    _, receipt = seed(path)
    first_request = sale_command(receipt, fulfilled_outbound_quantity=0)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        first = sale_owner(repository, first_request, identity="sale-b").execute(
            first_request
        ).settlement
        second_request = replace(
            first_request,
            command_id="second-command",
            external_report_reference="second-report",
            transaction_references=("second-order",),
            period_start=first_request.period_end,
            period_end=first_request.period_end + timedelta(days=1),
            requested_at=first_request.requested_at + timedelta(days=1),
            finality=replace(
                first_request.finality,
                observed_at=first_request.finality.observed_at + timedelta(days=1),
            ),
            fulfilled_outbound_quantity=1,
        )
        second = sale_owner(repository, second_request, identity="sale-a").execute(
            second_request
        ).settlement
        position = GetOwnedInventoryPositionsV2(repository).execute(
            receipt.source_manifest.opportunity_identity.opportunity_id
        )[0]
        assert position.contributing_actual_sale_settlement_ids == (
            first.settlement_id,
            second.settlement_id,
        )
        assert position.outbound_source_event_count == 2
        assert position.total_outbound_quantity == 1
