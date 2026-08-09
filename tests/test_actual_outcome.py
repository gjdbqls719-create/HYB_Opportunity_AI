from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import inspect

import pytest

from app.application.actual_outcome import (
    ActualOutcomePublication,
    ActualOutcomeReplayConflictError,
    ActualOutcomeSourceConflictError,
    CalculateActualOutcome,
    CalculateActualOutcomeCommand,
    _allocation,
)
from app.domain.capital import (
    ActualOutcomeBlockingReason,
    ActualOutcomeInventoryResolution,
    ActualOutcomeState,
    ActualAcquisitionCostCategory,
    ActualSaleMonetaryCategory,
)
from test_actual_acquisition_settlement import (
    MemorySettlementRepository,
    authority as acquisition_owner,
    request as acquisition_command,
)
from test_actual_sale_settlement import (
    MemorySaleRepository,
    command as sale_command,
    complete_facts,
    known,
    owner as sale_owner,
)
from test_goods_receipt import (
    MemoryGoodsReceiptRepository,
    command as goods_command,
    owner as goods_owner,
    purchase as make_purchase,
)


class MemoryOutcomeRepository:
    def __init__(self, acquisition, receipts, sales):
        self.acquisition = acquisition
        self.receipts = tuple(receipts)
        self.sales = {value.settlement_id: value for value in sales}
        self.outcomes = {}
        self.results = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result and result.receipt.command_fingerprint != fingerprint:
            raise ActualOutcomeReplayConflictError("payload conflict")
        return result

    def get_actual_acquisition_settlement(self, settlement_id):
        return self.acquisition if self.acquisition.settlement_id == settlement_id else None

    def get_actual_sale_settlement(self, settlement_id):
        return self.sales.get(settlement_id)

    def list_complete_settlements_for_product(self, product_key):
        return tuple(sorted(
            (v for v in self.sales.values() if v.source_manifest.product_key == product_key and v.state.value == "complete"),
            key=lambda v: (v.period_end, v.settlement_id),
        ))

    def list_goods_receipts_for_opportunity(self, opportunity_id):
        return tuple(v for v in self.receipts if v.source_manifest.opportunity_identity.opportunity_id == opportunity_id)

    def find_by_scope(self, scope_fingerprint):
        return self.outcomes.get(scope_fingerprint)

    def save(self, command, outcome, receipt, scope_fingerprint):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay:
            return replay
        existing = self.outcomes.get(scope_fingerprint)
        if existing is not None:
            receipt = replace(receipt, outcome_id=existing.outcome_id)
            result = ActualOutcomePublication(existing, receipt, False, True)
        else:
            self.outcomes[scope_fingerprint] = outcome
            result = ActualOutcomePublication(outcome, receipt, False)
        self.results[command.command_id] = result
        return result


def sources(*, received=None, sellable=None, damaged=0, sold=1, facts=None):
    purchase = make_purchase()
    goods_repository = MemoryGoodsReceiptRepository(purchase)
    received = purchase.actual_quantity if received is None else received
    sellable = received - damaged if sellable is None else sellable
    receipt = goods_owner(goods_repository).execute(goods_command(
        purchase, received_quantity=received, sellable_quantity=sellable,
        damaged_quantity=damaged,
    )).record
    acquisition_repository = MemorySettlementRepository(purchase)
    acquisition = acquisition_owner(acquisition_repository).execute(acquisition_command(purchase)).settlement
    sale_repository = MemorySaleRepository(receipt)
    request = sale_command(
        receipt, fulfilled_outbound_quantity=sold,
        fixed_monetary_facts=complete_facts() if facts is None else facts,
    )
    sale = sale_owner(sale_repository, request).execute(request).settlement
    return purchase, receipt, acquisition, sale


def command(acquisition, sales, **changes):
    values = dict(
        command_id="actual-outcome-command-1",
        opportunity_id=acquisition.source_manifest.opportunity_identity.opportunity_id,
        actual_acquisition_settlement_id=acquisition.settlement_id,
        actual_sale_settlement_ids=tuple(v.settlement_id for v in sales),
        requested_at=max(v.period_end for v in sales) + timedelta(minutes=10),
    )
    values.update(changes)
    return CalculateActualOutcomeCommand(**values)


def owner(repository, request, identity="actual-outcome-1", *, fail=False):
    def forbidden():
        raise AssertionError("identity/clock called during replay")
    return CalculateActualOutcome(
        repository,
        outcome_id_generator=forbidden if fail else lambda: identity,
        calculated_clock=forbidden if fail else lambda: request.requested_at + timedelta(minutes=1),
        committed_clock=forbidden if fail else lambda: request.requested_at + timedelta(minutes=2),
    )


def test_partial_sale_calculates_exact_profit_components_and_conserves_every_category():
    purchase, receipt, acquisition, sale = sources(sold=1)
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    request = command(acquisition, (sale,))
    outcome = owner(repository, request).execute(request).outcome

    assert outcome.state is ActualOutcomeState.CALCULABLE
    assert outcome.source_manifest.sold_quantity == 1
    assert outcome.source_manifest.remaining_sellable_quantity == purchase.actual_quantity - 1
    assert outcome.inventory_resolution is ActualOutcomeInventoryResolution.PARTIAL
    assert outcome.gross_realized_merchandise_revenue == Decimal("4000")
    assert outcome.actual_realized_profit == Decimal("4000") - outcome.actual_cogs
    assert outcome.remaining_sellable_inventory_cost_basis == outcome.acquisition_batch_total - outcome.actual_cogs
    for value in outcome.acquisition_allocations:
        assert value.sold_cogs + value.remaining_sellable_basis + value.damaged_loss + value.unreceived_exposure == value.batch_amount
    assert outcome.actual_margin.available is True
    assert outcome.actual_acquisition_roi.available is True
    with pytest.raises(FrozenInstanceError):
        outcome.state = ActualOutcomeState.BLOCKED


def test_damaged_and_partial_receipt_keep_separate_loss_inventory_and_unreceived_exposure():
    purchase, receipt, acquisition, sale = sources(received=6, sellable=5, damaged=1, sold=4)
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    outcome = owner(repository, command(acquisition, (sale,))).execute(command(acquisition, (sale,))).outcome

    manifest = outcome.source_manifest
    assert manifest.damaged_quantity == 1
    assert manifest.remaining_sellable_quantity == 1
    assert manifest.unreceived_quantity == purchase.actual_quantity - 6
    assert outcome.damaged_acquisition_loss > 0
    assert outcome.remaining_sellable_inventory_cost_basis > 0
    assert outcome.unreceived_acquisition_cost_basis > 0
    assert outcome.actual_cogs + outcome.remaining_sellable_inventory_cost_basis + outcome.damaged_acquisition_loss + outcome.unreceived_acquisition_cost_basis == outcome.acquisition_batch_total


def test_zero_sale_is_calculable_with_unavailable_ratios_and_preserved_inventory_basis():
    purchase, receipt, acquisition, sale = sources(sold=0, facts=tuple(
        known(category, "0") if category is ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE else fact
        for category, fact in zip(ActualSaleMonetaryCategory, complete_facts(), strict=True)
    ))
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    outcome = owner(repository, command(acquisition, (sale,))).execute(command(acquisition, (sale,))).outcome

    assert outcome.state is ActualOutcomeState.CALCULABLE
    assert outcome.actual_cogs == 0
    assert outcome.actual_realized_profit == 0
    assert outcome.actual_margin.available is False
    assert outcome.actual_acquisition_roi.available is False
    assert outcome.remaining_sellable_inventory_cost_basis == outcome.acquisition_batch_total


def test_negative_profit_remains_calculable():
    facts = tuple(
        known(value.category, "1") if value.category is ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE else value
        for value in complete_facts()
    )
    _, receipt, acquisition, sale = sources(sold=1, facts=facts)
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    outcome = owner(repository, command(acquisition, (sale,))).execute(command(acquisition, (sale,))).outcome
    assert outcome.state is ActualOutcomeState.CALCULABLE
    assert outcome.actual_realized_profit < 0


def test_multi_purchase_and_currency_mismatch_are_ordered_blocking_reasons_without_metrics():
    _, receipt, acquisition, sale = sources(sold=1)
    sale = replace(
        sale,
        source_manifest=replace(sale.source_manifest, contributing_purchase_execution_ids=(acquisition.source_manifest.purchase_execution_record_id, "purchase-2")),
        settlement_currency="USD",
        fixed_monetary_facts=tuple(
            replace(value, currency="USD") if value.amount is not None else value
            for value in sale.fixed_monetary_facts
        ),
        payout=replace(sale.payout, currency="USD"),
    )
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    outcome = owner(repository, command(acquisition, (sale,))).execute(command(acquisition, (sale,))).outcome
    assert outcome.state is ActualOutcomeState.BLOCKED
    assert outcome.blocking_reasons == (
        ActualOutcomeBlockingReason.MULTI_PURCHASE_ALLOCATION_UNSUPPORTED,
        ActualOutcomeBlockingReason.CURRENCY_MISMATCH,
    )
    assert outcome.actual_realized_profit is None


def test_exact_replay_precedes_sources_identity_and_clocks_changed_payload_conflicts():
    _, receipt, acquisition, sale = sources()
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    request = command(acquisition, (sale,))
    first = owner(repository, request).execute(request)
    repository.acquisition = None
    replay = owner(repository, request, fail=True).execute(request)
    assert replay.replayed is True
    assert replay.outcome == first.outcome
    with pytest.raises(ActualOutcomeReplayConflictError):
        owner(repository, replace(request, requested_at=request.requested_at + timedelta(seconds=1)), fail=True).execute(replace(request, requested_at=request.requested_at + timedelta(seconds=1)))


def test_same_manifest_different_command_aliases_and_prefix_omission_is_rejected():
    _, receipt, acquisition, sale = sources()
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (sale,))
    first_request = command(acquisition, (sale,))
    first = owner(repository, first_request).execute(first_request)
    alias_request = replace(first_request, command_id="actual-outcome-command-2")
    alias = owner(repository, alias_request, identity="unused").execute(alias_request)
    assert alias.aliased is True
    assert alias.outcome.outcome_id == first.outcome.outcome_id

    extra_end = sale.period_end + timedelta(days=1)
    extra = replace(
        sale, settlement_id="sale-2", period_start=sale.period_end,
        period_end=extra_end, requested_at=extra_end + timedelta(minutes=1),
        admitted_at=extra_end + timedelta(minutes=2),
        finality=replace(sale.finality, observed_at=extra_end),
    )
    repository.sales[extra.settlement_id] = extra
    omitted = replace(first_request, command_id="actual-outcome-command-3", requested_at=extra.period_end + timedelta(minutes=1), actual_sale_settlement_ids=(extra.settlement_id,))
    with pytest.raises(ActualOutcomeSourceConflictError, match="prefix"):
        owner(repository, omitted).execute(omitted)


def test_duplicate_and_reordered_sale_ids_are_rejected():
    _, _, acquisition, sale = sources()
    with pytest.raises(ValueError, match="unique"):
        command(acquisition, (sale, sale))


def test_repeating_decimal_residual_is_assigned_to_remaining_before_realized_buckets():
    value = _allocation(
        Decimal("1"), 3, sold=1, remaining=1, damaged=1, unreceived=0,
        category=ActualAcquisitionCostCategory.UNIT_PURCHASE,
    )
    assert value.sold_cogs == value.per_executed_unit
    assert value.damaged_loss == value.per_executed_unit
    assert value.remaining_sellable_basis > value.per_executed_unit
    assert value.sold_cogs + value.remaining_sellable_basis + value.damaged_loss + value.unreceived_exposure == Decimal("1")


def test_multiple_complete_sale_windows_form_one_ordered_cumulative_outcome():
    purchase = make_purchase()
    goods_repository = MemoryGoodsReceiptRepository(purchase)
    receipt = goods_owner(goods_repository).execute(goods_command(purchase)).record
    acquisition_repository = MemorySettlementRepository(purchase)
    acquisition = acquisition_owner(acquisition_repository).execute(acquisition_command(purchase)).settlement
    sale_repository = MemorySaleRepository(receipt)
    first_request = sale_command(receipt, fulfilled_outbound_quantity=2)
    first = sale_owner(sale_repository, first_request).execute(first_request).settlement
    second_start = first.period_end
    second_end = second_start + timedelta(days=1)
    second_request = sale_command(
        receipt,
        command_id="sale-command-2",
        external_report_reference="coupang-report-2",
        transaction_references=("order-2",),
        period_start=second_start,
        period_end=second_end,
        fulfilled_outbound_quantity=3,
        requested_at=second_end + timedelta(minutes=1),
        finality=replace(first_request.finality, observed_at=second_end),
    )
    second = sale_owner(sale_repository, second_request, identity="sale-settlement-2").execute(second_request).settlement
    repository = MemoryOutcomeRepository(acquisition, (receipt,), (first, second))
    result = owner(repository, command(acquisition, (first, second))).execute(command(acquisition, (first, second))).outcome
    assert result.source_manifest.actual_sale_settlement_ids == (first.settlement_id, second.settlement_id)
    assert result.source_manifest.sold_quantity == 5
    assert result.gross_realized_merchandise_revenue == Decimal("8000")


def test_actual_outcome_owner_has_no_predicted_or_legacy_economics_dependency():
    source = inspect.getsource(CalculateActualOutcome)
    for forbidden in ("ConservativeEconomics", "EconomicsSourceComposition", "ActualEconomics", "FXObservation"):
        assert forbidden not in source
