from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.actual_sale_settlement import (
    AdmitActualSaleSettlement,
    AdmitActualSaleSettlementCommand,
    ActualSaleSettlementOversellConflictError,
    ActualSaleSettlementProductConflictError,
    ActualSaleSettlementPublication,
    ActualSaleSettlementReplayConflictError,
    ActualSaleSettlementTerminalConflictError,
)

from app.domain.capital import (
    ActualSaleEvidenceReference,
    ActualSaleFactAvailability,
    ActualSaleMonetaryFact,
    ActualSaleMonetaryCategory,
    ActualSalePayoutFact,
    ActualSalePayoutReconciliationState,
    ActualSaleFinalityFact,
    ActualSaleSettlementState,
    FIXED_ACTUAL_SALE_CATEGORIES,
    OtherActualSaleCosts,
)
from test_goods_receipt import (
    MemoryGoodsReceiptRepository,
    command as goods_command,
    owner as goods_owner,
    purchase as make_purchase,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def test_actual_sale_known_fact_is_explicit_and_immutable() -> None:
    evidence = ActualSaleEvidenceReference(
        reference="coupang-report-1",
        observed_at=NOW,
        operator_id="founder",
        collection_method="manual_csv",
    )
    fact = ActualSaleMonetaryFact(
        category=ActualSaleMonetaryCategory.MARKETPLACE_FEE,
        availability=ActualSaleFactAvailability.KNOWN,
        amount=Decimal("1000"),
        currency="krw",
        occurred_at=NOW - timedelta(hours=1),
        evidence=evidence,
        unresolved_reason=None,
    )

    assert fact.currency == "KRW"
    assert fact.amount == Decimal("1000")
    assert ActualSaleSettlementState.COMPLETE.value == "complete"
    with pytest.raises(FrozenInstanceError):
        fact.amount = Decimal("0")


def evidence(reference="coupang-report-1"):
    return ActualSaleEvidenceReference(reference, NOW, "founder-1", "manual_csv")


def known(category, amount="0", currency="KRW"):
    return ActualSaleMonetaryFact(
        category, ActualSaleFactAvailability.KNOWN, Decimal(amount), currency,
        NOW, evidence(f"evidence-{category.value}"), None,
    )


def not_applicable(category):
    return ActualSaleMonetaryFact(
        category, ActualSaleFactAvailability.NOT_APPLICABLE, None, None, None,
        evidence(f"na-{category.value}"), None,
    )


def unknown(category):
    return ActualSaleMonetaryFact(
        category, ActualSaleFactAvailability.UNKNOWN, None, None, None, None,
        f"{category.value} unresolved",
    )


def complete_facts():
    values = []
    for category in FIXED_ACTUAL_SALE_CATEGORIES:
        if category is ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE:
            values.append(known(category, "4000"))
        elif category is ActualSaleMonetaryCategory.PAYMENT_FEE:
            values.append(not_applicable(category))
        else:
            values.append(known(category))
    return tuple(values)


def goods_receipt():
    purchase = make_purchase()
    repository = MemoryGoodsReceiptRepository(purchase)
    return goods_owner(repository).execute(goods_command(purchase)).record


class MemorySaleRepository:
    def __init__(self, receipt):
        self.receipts = (receipt,)
        self.settlements = {}
        self.results = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result and result.receipt.command_fingerprint != fingerprint:
            raise ActualSaleSettlementReplayConflictError("payload conflict")
        return result

    def get_goods_receipt(self, record_id):
        return next((v for v in self.receipts if v.record_id == record_id), None)

    def list_goods_receipts_for_opportunity(self, opportunity_id):
        return tuple(v for v in self.receipts if v.source_manifest.opportunity_identity.opportunity_id == opportunity_id)

    def get_settlement(self, settlement_id):
        return self.settlements.get(settlement_id)

    def get_chain_tip_for_subject(self, manifest):
        values = [
            v for v in self.settlements.values()
            if v.source_manifest.product_key == manifest.product_key
            and v.source_manifest.marketplace == manifest.marketplace
            and v.source_manifest.seller_account_reference == manifest.seller_account_reference
            and v.source_manifest.external_report_reference == manifest.external_report_reference
        ]
        return max(values, key=lambda v: v.revision) if values else None

    def list_complete_settlements_for_product(self, product_key):
        return tuple(v for v in self.settlements.values() if v.source_manifest.product_key == product_key and v.state is ActualSaleSettlementState.COMPLETE)

    def save(self, command, settlement, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay:
            return replay
        result = ActualSaleSettlementPublication(settlement, receipt, False)
        self.settlements[settlement.settlement_id] = settlement
        self.results[command.command_id] = result
        return result


def command(receipt, **changes):
    period_start = receipt.inspected_at + timedelta(minutes=1)
    period_end = period_start + timedelta(days=1)
    values = dict(
        command_id="sale-command-1",
        opportunity_id=receipt.source_manifest.opportunity_identity.opportunity_id,
        anchor_goods_receipt_id=receipt.record_id,
        predecessor_settlement_id=None,
        marketplace="coupang",
        seller_account_reference="coupang-store-1",
        marketplace_product_reference="coupang-product-1",
        marketplace_option_reference="option-a",
        marketplace_sku_reference="sku-a",
        external_report_reference="coupang-report-1",
        transaction_references=("order-1",),
        period_start=period_start,
        period_end=period_end,
        fulfilled_outbound_quantity=min(1, receipt.sellable_quantity),
        cancelled_quantity=0,
        refunded_quantity=0,
        returned_quantity=0,
        quantity_unit=receipt.quantity_unit,
        settlement_currency="KRW",
        fixed_monetary_facts=complete_facts(),
        other_sale_side_costs=OtherActualSaleCosts(
            ActualSaleFactAvailability.KNOWN, (), evidence("other-scope"), None
        ),
        payout=ActualSalePayoutFact(
            ActualSaleFactAvailability.KNOWN, Decimal("4000"), "KRW",
            "payout-1", period_end, evidence("payout"), None,
            ActualSalePayoutReconciliationState.NOT_SCOPE_COMPARABLE,
            "account payout contains timing items", evidence("reconciliation"),
        ),
        finality=ActualSaleFinalityFact(
            True, period_end, evidence("finality"), None
        ),
        operator_id="founder-1",
        requested_at=period_end + timedelta(minutes=1),
    )
    values.update(changes)
    return AdmitActualSaleSettlementCommand(**values)


def owner(repository, request, identity="sale-settlement-1", *, fail=False):
    def forbidden():
        raise AssertionError("dependency called during replay")
    return AdmitActualSaleSettlement(
        repository,
        settlement_id_generator=forbidden if fail else lambda: identity,
        admitted_clock=forbidden if fail else lambda: request.requested_at + timedelta(minutes=1),
        committed_clock=forbidden if fail else lambda: request.requested_at + timedelta(minutes=2),
    )


def test_complete_manual_coupang_batch_preserves_exact_lineage_and_outbound():
    receipt = goods_receipt()
    repository = MemorySaleRepository(receipt)
    request = command(receipt)
    result = owner(repository, request).execute(request)
    settlement = result.settlement
    assert settlement.state is ActualSaleSettlementState.COMPLETE
    assert settlement.fulfilled_outbound_quantity == request.fulfilled_outbound_quantity
    assert settlement.source_manifest.anchor_goods_receipt_id == receipt.record_id
    assert settlement.source_manifest.eligible_goods_receipt_ids == (receipt.record_id,)
    assert settlement.source_manifest.product_key.sku_reference == receipt.source_manifest.sku_reference
    assert settlement.source_manifest.marketplace == "COUPANG"
    assert settlement.fixed_monetary_facts[0].amount == Decimal("4000")
    assert settlement.fixed_monetary_facts[6].availability is ActualSaleFactAvailability.NOT_APPLICABLE
    assert settlement.payout.external_reference == "payout-1"
    assert not hasattr(settlement, "profit")


def test_zero_sales_complete_and_blocked_unknown_does_not_consume_inventory():
    receipt = goods_receipt()
    zero_repo = MemorySaleRepository(receipt)
    zero = command(receipt, fulfilled_outbound_quantity=0, transaction_references=())
    assert owner(zero_repo, zero).execute(zero).settlement.state is ActualSaleSettlementState.COMPLETE

    facts = list(complete_facts())
    facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    blocked_repo = MemorySaleRepository(receipt)
    blocked = command(receipt, fixed_monetary_facts=tuple(facts), fulfilled_outbound_quantity=receipt.sellable_quantity + 50)
    result = owner(blocked_repo, blocked).execute(blocked)
    assert result.settlement.state is ActualSaleSettlementState.BLOCKED
    assert blocked_repo.list_complete_settlements_for_product(result.settlement.source_manifest.product_key) == ()


def test_blocked_to_complete_exact_replay_terminal_and_oversell():
    receipt = goods_receipt()
    repository = MemorySaleRepository(receipt)
    facts = list(complete_facts())
    facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    first_command = command(receipt, fixed_monetary_facts=tuple(facts))
    first = owner(repository, first_command).execute(first_command)
    replay = owner(repository, first_command, fail=True).execute(first_command)
    assert replay.replayed is True and replay.settlement == first.settlement
    child_command = command(
        receipt,
        command_id="sale-command-2",
        predecessor_settlement_id=first.settlement.settlement_id,
    )
    child = owner(repository, child_command, identity="sale-settlement-2").execute(child_command)
    assert child.settlement.state is ActualSaleSettlementState.COMPLETE
    terminal = replace(child_command, command_id="sale-command-3", predecessor_settlement_id=child.settlement.settlement_id)
    with pytest.raises(ActualSaleSettlementTerminalConflictError):
        owner(repository, terminal, identity="sale-settlement-3").execute(terminal)

    other = MemorySaleRepository(receipt)
    oversell = command(receipt, fulfilled_outbound_quantity=receipt.sellable_quantity + 1)
    with pytest.raises(ActualSaleSettlementOversellConflictError):
        owner(other, oversell).execute(oversell)


def test_cross_currency_is_blocked_and_quantity_unit_is_exact():
    receipt = goods_receipt()
    repository = MemorySaleRepository(receipt)
    facts = list(complete_facts())
    facts[5] = known(ActualSaleMonetaryCategory.MARKETPLACE_FEE, "1", "USD")
    request = command(receipt, fixed_monetary_facts=tuple(facts))
    result = owner(repository, request).execute(request)
    assert result.settlement.state is ActualSaleSettlementState.BLOCKED
    invalid_unit = command(receipt, command_id="unit-conflict", quantity_unit="case")
    with pytest.raises(ActualSaleSettlementProductConflictError, match="quantity unit"):
        owner(MemorySaleRepository(receipt), invalid_unit).execute(invalid_unit)


def test_reconciled_payout_is_checked_and_different_sku_cannot_supply_inventory():
    receipt = goods_receipt()
    reconciled = replace(
        command(receipt).payout,
        amount=Decimal("3999"),
        reconciliation_state=ActualSalePayoutReconciliationState.RECONCILED,
        reconciliation_explanation="components match",
    )
    request = command(receipt, payout=reconciled)
    with pytest.raises(ValueError, match="canonical components"):
        owner(MemorySaleRepository(receipt), request).execute(request)

    second_source = replace(receipt.source_manifest, sku_reference="different-sku")
    second = replace(receipt, record_id="different-receipt", source_manifest=second_source)
    repository = MemorySaleRepository(receipt)
    repository.receipts = (receipt, second)
    oversell = command(receipt, command_id="sku-isolation", fulfilled_outbound_quantity=receipt.sellable_quantity + 1)
    with pytest.raises(ActualSaleSettlementOversellConflictError):
        owner(repository, oversell).execute(oversell)
