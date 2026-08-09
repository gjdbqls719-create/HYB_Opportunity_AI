"""Application owner for immutable exact-source Actual Outcomes."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    ACTUAL_OUTCOME_COMMAND_SCHEMA_VERSION,
    ACTUAL_OUTCOME_POLICY_NAME,
    ACTUAL_OUTCOME_POLICY_VERSION,
    ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION,
    ActualAcquisitionSettlement,
    ActualAcquisitionSettlementState,
    ActualOutcome,
    ActualOutcomeAcquisitionAllocation,
    ActualOutcomeBlockingReason,
    ActualOutcomeInventoryResolution,
    ActualOutcomeMetric,
    ActualOutcomeSaleComponent,
    ActualOutcomeSaleWindow,
    ActualOutcomeSourceManifest,
    ActualOutcomeState,
    ActualSaleFactAvailability,
    ActualSaleMonetaryCategory,
    ActualSaleSettlement,
    ActualSaleSettlementState,
    GoodsReceiptRecord,
    OwnedInventoryProductKey,
    actual_outcome_decimal_context,
)
from app.application.actual_sale_settlement import owned_inventory_product_key_from_receipt


class ActualOutcomeError(RuntimeError): pass
class ActualOutcomeSourceNotFoundError(ActualOutcomeError): pass
class ActualOutcomeOpportunityConflictError(ActualOutcomeError): pass
class ActualOutcomeSourceConflictError(ActualOutcomeError): pass
class ActualOutcomeReplayConflictError(ActualOutcomeError): pass
class ActualOutcomeSourceIntegrityError(ActualOutcomeError): pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _fingerprint(value: object) -> str:
    encoded = _snapshot(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _snapshot(value: object) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint_text(value: str) -> str:
    result = _text(value, "fingerprint").lower()
    if len(result) != 64 or any(c not in "0123456789abcdef" for c in result):
        raise ValueError("fingerprint must be SHA-256 text")
    return result


@dataclass(frozen=True, slots=True)
class CalculateActualOutcomeCommand:
    command_id: str
    opportunity_id: str
    actual_acquisition_settlement_id: str
    actual_sale_settlement_ids: tuple[str, ...]
    requested_at: datetime
    policy_name: str = ACTUAL_OUTCOME_POLICY_NAME
    policy_version: str = ACTUAL_OUTCOME_POLICY_VERSION
    schema_version: str = ACTUAL_OUTCOME_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "opportunity_id", "actual_acquisition_settlement_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.actual_sale_settlement_ids, tuple) or not self.actual_sale_settlement_ids:
            raise ValueError("actual_sale_settlement_ids must be a non-empty tuple")
        values = tuple(_text(v, "actual_sale_settlement_id") for v in self.actual_sale_settlement_ids)
        if len(set(values)) != len(values):
            raise ValueError("actual_sale_settlement_ids must be unique")
        object.__setattr__(self, "actual_sale_settlement_ids", values)
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if (self.policy_name, self.policy_version, self.schema_version) != (
            ACTUAL_OUTCOME_POLICY_NAME, ACTUAL_OUTCOME_POLICY_VERSION,
            ACTUAL_OUTCOME_COMMAND_SCHEMA_VERSION,
        ):
            raise ValueError("unsupported Actual Outcome command policy or schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ActualOutcomeReceipt:
    command_id: str
    outcome_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "outcome_id", _text(self.outcome_id, "outcome_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Actual Outcome receipt schema")


@dataclass(frozen=True, slots=True)
class ActualOutcomePublication:
    outcome: ActualOutcome
    receipt: ActualOutcomeReceipt
    replayed: bool
    aliased: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ActualOutcome) or not isinstance(self.receipt, ActualOutcomeReceipt):
            raise TypeError("Actual Outcome publication contains unsupported values")
        if self.receipt.outcome_id != self.outcome.outcome_id:
            raise ValueError("receipt must reference Actual Outcome")
        if not isinstance(self.replayed, bool) or not isinstance(self.aliased, bool):
            raise TypeError("publication flags must be bool")


class ActualOutcomeRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> ActualOutcomePublication | None: ...
    def get_actual_acquisition_settlement(self, settlement_id: str) -> ActualAcquisitionSettlement | None: ...
    def get_actual_sale_settlement(self, settlement_id: str) -> ActualSaleSettlement | None: ...
    def list_complete_settlements_for_product(self, product_key: OwnedInventoryProductKey) -> tuple[ActualSaleSettlement, ...]: ...
    def list_goods_receipts_for_opportunity(self, opportunity_id: str) -> tuple[GoodsReceiptRecord, ...]: ...
    def find_by_scope(self, scope_fingerprint: str) -> ActualOutcome | None: ...
    def save(self, command, outcome, receipt, scope_fingerprint: str) -> ActualOutcomePublication: ...


def product_key_from_acquisition(value: ActualAcquisitionSettlement) -> OwnedInventoryProductKey:
    source = value.source_manifest
    return OwnedInventoryProductKey(
        opportunity_identity=source.opportunity_identity,
        source_platform=source.source_platform,
        supplier_id=source.supplier_id,
        sourcing_product_id=source.sourcing_product_id,
        external_product_reference=source.external_product_reference,
        option_reference=source.option_reference,
        sku_reference=source.sku_reference,
        quantity_unit=source.executed_quantity_unit,
    )


def actual_outcome_scope_fingerprint(manifest: ActualOutcomeSourceManifest) -> str:
    return _fingerprint({
        "product_key": manifest.product_key,
        "purchase_execution_record_id": manifest.purchase_execution_record_id,
        "actual_acquisition_settlement_id": manifest.actual_acquisition_settlement_id,
        "goods_receipt_ids": manifest.goods_receipt_ids,
        "actual_sale_settlement_ids": manifest.actual_sale_settlement_ids,
        "policy_name": ACTUAL_OUTCOME_POLICY_NAME,
        "policy_version": ACTUAL_OUTCOME_POLICY_VERSION,
    })


def _allocation(batch: Decimal, executed: int, sold: int, remaining: int, damaged: int, unreceived: int, category) -> ActualOutcomeAcquisitionAllocation:
    with localcontext(actual_outcome_decimal_context()):
        per_unit = batch / Decimal(executed)
        buckets = {
            "sold": per_unit * Decimal(sold),
            "remaining": per_unit * Decimal(remaining),
            "damaged": per_unit * Decimal(damaged),
            "unreceived": per_unit * Decimal(unreceived),
        }
        residual = batch - sum(buckets.values(), Decimal("0"))
        for name, quantity in (("remaining", remaining), ("unreceived", unreceived), ("damaged", damaged), ("sold", sold)):
            if quantity:
                buckets[name] += residual
                break
    return ActualOutcomeAcquisitionAllocation(
        category, batch, per_unit, buckets["sold"], buckets["remaining"],
        buckets["damaged"], buckets["unreceived"],
    )


class CalculateActualOutcome:
    def __init__(self, repository: ActualOutcomeRepository, *, outcome_id_generator: Callable[[], str], calculated_clock: Callable[[], datetime], committed_clock: Callable[[], datetime]) -> None:
        if not all(callable(v) for v in (outcome_id_generator, calculated_clock, committed_clock)):
            raise TypeError("Actual Outcome dependencies must be callable")
        self._repository = repository
        self._identity = outcome_id_generator
        self._calculated = calculated_clock
        self._committed = committed_clock

    def execute(self, command: CalculateActualOutcomeCommand) -> ActualOutcomePublication:
        if not isinstance(command, CalculateActualOutcomeCommand):
            raise TypeError("command must be CalculateActualOutcomeCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        acquisition = self._repository.get_actual_acquisition_settlement(command.actual_acquisition_settlement_id)
        if acquisition is None:
            raise ActualOutcomeSourceNotFoundError("exact Actual Acquisition Settlement is missing")
        sales: list[ActualSaleSettlement] = []
        for settlement_id in command.actual_sale_settlement_ids:
            value = self._repository.get_actual_sale_settlement(settlement_id)
            if value is None:
                raise ActualOutcomeSourceNotFoundError("exact Actual Sale Settlement is missing")
            sales.append(value)
        selected = tuple(sales)
        ordered = tuple(sorted(selected, key=lambda v: (v.period_end.astimezone(timezone.utc), v.settlement_id)))
        if selected != ordered:
            raise ActualOutcomeSourceConflictError("Actual Sale Settlement IDs are not in deterministic chronological order")
        key = selected[0].source_manifest.product_key
        if any(value.source_manifest.product_key != key for value in selected):
            raise ActualOutcomeSourceConflictError("Actual Sale Settlements do not share one exact product key")
        if key.opportunity_identity.opportunity_id != command.opportunity_id:
            raise ActualOutcomeOpportunityConflictError("Actual Sale Settlement differs from route Opportunity")
        if product_key_from_acquisition(acquisition) != key:
            raise ActualOutcomeSourceConflictError("Actual Acquisition and Sale product lineage differs")
        purchase_id = acquisition.source_manifest.purchase_execution_record_id
        evaluation_start = min(v.period_start for v in selected)
        evaluation_through = max(v.period_end for v in selected)
        if command.requested_at < evaluation_through:
            raise ActualOutcomeSourceConflictError("requested_at cannot precede outcome evaluation boundary")
        complete_selected = tuple(v for v in selected if v.state is ActualSaleSettlementState.COMPLETE)
        complete_prefix = tuple(
            v for v in self._repository.list_complete_settlements_for_product(key)
            if v.period_end <= evaluation_through
        )
        if tuple(v.settlement_id for v in complete_selected) != tuple(v.settlement_id for v in complete_prefix):
            raise ActualOutcomeSourceConflictError("selected sale sources omit, reorder, or add to the COMPLETE cumulative prefix")
        all_receipts = tuple(
            value for value in self._repository.list_goods_receipts_for_opportunity(command.opportunity_id)
            if owned_inventory_product_key_from_receipt(value) == key
        )
        receipts = tuple(sorted(
            (value for value in all_receipts if value.source_manifest.purchase_execution_record_id == purchase_id and value.inspected_at < evaluation_through),
            key=lambda v: (v.inspected_at.astimezone(timezone.utc), v.record_id),
        ))
        executed = acquisition.source_manifest.executed_quantity
        received = sum(v.received_quantity for v in receipts)
        sellable = sum(v.sellable_quantity for v in receipts)
        damaged = sum(v.damaged_quantity for v in receipts)
        sold = sum(v.fulfilled_outbound_quantity for v in complete_selected)
        returned = sum(v.returned_quantity for v in complete_selected)
        if received > executed or sold > sellable:
            raise ActualOutcomeSourceIntegrityError("persisted quantity history is structurally impossible")
        remaining = sellable - sold
        unreceived = executed - received
        reasons: list[ActualOutcomeBlockingReason] = []
        if acquisition.state is not ActualAcquisitionSettlementState.COMPLETE:
            reasons.append(ActualOutcomeBlockingReason.ACQUISITION_NOT_COMPLETE)
        if len(complete_selected) != len(selected):
            reasons.append(ActualOutcomeBlockingReason.SALE_SET_NOT_COMPLETE)
        if any(value.source_manifest.contributing_purchase_execution_ids != (purchase_id,) for value in selected):
            reasons.append(ActualOutcomeBlockingReason.MULTI_PURCHASE_ALLOCATION_UNSUPPORTED)
        if any(value.settlement_currency != acquisition.target_currency for value in selected):
            reasons.append(ActualOutcomeBlockingReason.CURRENCY_MISMATCH)
        manifest = ActualOutcomeSourceManifest(
            product_key=key,
            purchase_execution_record_id=purchase_id,
            actual_acquisition_settlement_id=acquisition.settlement_id,
            goods_receipt_ids=tuple(v.record_id for v in receipts),
            actual_sale_settlement_ids=tuple(v.settlement_id for v in selected),
            sale_windows=tuple(ActualOutcomeSaleWindow(v.settlement_id, v.period_start, v.period_end) for v in selected),
            executed_quantity=executed,
            received_quantity=received,
            sellable_received_quantity=sellable,
            damaged_quantity=damaged,
            sold_quantity=sold,
            remaining_sellable_quantity=remaining,
            returned_quantity=returned,
            unreceived_quantity=unreceived,
            quantity_unit=key.quantity_unit,
            currency=acquisition.target_currency,
            evaluation_start=evaluation_start,
            evaluation_through=evaluation_through,
            acquisition_policy_version=acquisition.policy_version,
            acquisition_schema_version=acquisition.schema_version,
            goods_receipt_policy_versions=tuple(v.policy_version for v in receipts),
            goods_receipt_schema_versions=tuple(v.schema_version for v in receipts),
            sale_policy_versions=tuple(v.policy_version for v in selected),
            sale_schema_versions=tuple(v.schema_version for v in selected),
            acquisition_source_snapshot=_snapshot(acquisition),
            goods_receipt_source_snapshots=tuple(_snapshot(v) for v in receipts),
            sale_source_snapshots=tuple(_snapshot(v) for v in selected),
        )
        scope_fingerprint = actual_outcome_scope_fingerprint(manifest)
        alias = self._repository.find_by_scope(scope_fingerprint)
        if alias is not None:
            receipt = ActualOutcomeReceipt(command.command_id, alias.outcome_id, command.fingerprint, _aware(self._committed(), "committed_at"))
            return self._repository.save(command, alias, receipt, scope_fingerprint)
        calculated_at = _aware(self._calculated(), "calculated_at")
        committed_at = _aware(self._committed(), "committed_at")
        resolution = ActualOutcomeInventoryResolution.FULLY_RESOLVED if received == executed and remaining == 0 and returned == 0 else ActualOutcomeInventoryResolution.PARTIAL
        common = dict(
            outcome_id=_text(self._identity(), "outcome_id"), source_manifest=manifest,
            inventory_resolution=resolution, requested_at=command.requested_at,
            calculated_at=calculated_at, committed_at=committed_at,
            policy_name=command.policy_name, policy_version=command.policy_version,
        )
        if reasons:
            outcome = ActualOutcome(
                state=ActualOutcomeState.BLOCKED, blocking_reasons=tuple(reasons),
                acquisition_allocations=(), sale_components=(), other_sale_side_costs=None,
                acquisition_batch_total=None, actual_cogs=None,
                remaining_sellable_inventory_cost_basis=None, damaged_acquisition_loss=None,
                unreceived_acquisition_cost_basis=None, gross_realized_merchandise_revenue=None,
                recognized_sale_credits=None, recognized_sale_side_costs=None,
                net_realized_sale_contribution=None, actual_realized_profit=None,
                actual_margin=ActualOutcomeMetric(False, None),
                actual_acquisition_roi=ActualOutcomeMetric(False, None),
                known_payout_total=None, payout_reconciliation_states=(), **common,
            )
        else:
            allocations = tuple(
                _allocation(value.target_batch_amount, executed, sold, remaining, damaged, unreceived, value.category)  # type: ignore[arg-type]
                for value in acquisition.normalized_categories
            )
            components = []
            for category in ActualSaleMonetaryCategory:
                amounts = []
                for sale in selected:
                    fact = next(v for v in sale.fixed_monetary_facts if v.category is category)
                    amounts.append(Decimal("0") if fact.availability is ActualSaleFactAvailability.NOT_APPLICABLE else fact.amount)
                with localcontext(actual_outcome_decimal_context()):
                    amount = sum(amounts, Decimal("0"))  # type: ignore[arg-type]
                components.append(ActualOutcomeSaleComponent(category, amount))
            by_category = {v.category: v.amount for v in components}
            with localcontext(actual_outcome_decimal_context()):
                other_costs = sum((item.amount for sale in selected for item in sale.other_sale_side_costs.items), Decimal("0"))
                batch_total = sum((v.batch_amount for v in allocations), Decimal("0"))
                cogs = sum((v.sold_cogs for v in allocations), Decimal("0"))
                remaining_basis = sum((v.remaining_sellable_basis for v in allocations), Decimal("0"))
                damaged_loss = sum((v.damaged_loss for v in allocations), Decimal("0"))
                unreceived_basis = sum((v.unreceived_exposure for v in allocations), Decimal("0"))
                gross = by_category[ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE]
                credits = gross + by_category[ActualSaleMonetaryCategory.BUYER_SHIPPING] + by_category[ActualSaleMonetaryCategory.MARKETPLACE_FUNDED_DISCOUNT_SUPPORT]
                costs = other_costs + sum((by_category[v] for v in (
                    ActualSaleMonetaryCategory.REFUND, ActualSaleMonetaryCategory.MARKETPLACE_FEE,
                    ActualSaleMonetaryCategory.PAYMENT_FEE, ActualSaleMonetaryCategory.FIXED_FEE,
                    ActualSaleMonetaryCategory.RETURN_RELATED_FEE, ActualSaleMonetaryCategory.ADVERTISING,
                    ActualSaleMonetaryCategory.FULFILLMENT, ActualSaleMonetaryCategory.STORAGE,
                    ActualSaleMonetaryCategory.SALE_SIDE_INBOUND_HANDLING,
                )), Decimal("0"))
                contribution = credits - costs
                profit = contribution - cogs - damaged_loss
                margin = None if gross == 0 else profit / gross * Decimal("100")
                recognized_basis = cogs + damaged_loss
                roi = None if recognized_basis == 0 else profit / recognized_basis * Decimal("100")
                known_payouts = tuple(v.payout.amount for v in selected if v.payout.amount is not None)
                payout_total = None if not known_payouts else sum(known_payouts, Decimal("0"))
            outcome = ActualOutcome(
                state=ActualOutcomeState.CALCULABLE, blocking_reasons=(),
                acquisition_allocations=allocations, sale_components=tuple(components),
                other_sale_side_costs=other_costs, acquisition_batch_total=batch_total,
                actual_cogs=cogs, remaining_sellable_inventory_cost_basis=remaining_basis,
                damaged_acquisition_loss=damaged_loss, unreceived_acquisition_cost_basis=unreceived_basis,
                gross_realized_merchandise_revenue=gross, recognized_sale_credits=credits,
                recognized_sale_side_costs=costs, net_realized_sale_contribution=contribution,
                actual_realized_profit=profit, actual_margin=ActualOutcomeMetric(margin is not None, margin),
                actual_acquisition_roi=ActualOutcomeMetric(roi is not None, roi),
                known_payout_total=payout_total,
                payout_reconciliation_states=tuple(v.payout.reconciliation_state.value for v in selected),
                **common,
            )
        receipt = ActualOutcomeReceipt(command.command_id, outcome.outcome_id, command.fingerprint, committed_at)
        return self._repository.save(command, outcome, receipt, scope_fingerprint)


__all__ = [name for name in globals() if name.startswith(("ActualOutcome", "CalculateActual", "ACTUAL_OUTCOME")) or name in {"actual_outcome_scope_fingerprint", "product_key_from_acquisition"}]
