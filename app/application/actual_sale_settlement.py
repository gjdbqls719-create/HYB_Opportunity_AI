"""Application owner for immutable actual sale settlement revisions."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    ACTUAL_SALE_POLICY_NAME,
    ACTUAL_SALE_POLICY_VERSION,
    ActualSaleFactAvailability,
    ActualSaleFinalityFact,
    ActualSaleMonetaryFact,
    ActualSalePayoutFact,
    ActualSaleSettlement,
    ActualSaleSettlementSourceManifest,
    ActualSaleSettlementState,
    GoodsReceiptRecord,
    OtherActualSaleCosts,
    OwnedInventoryProductKey,
    evaluate_actual_sale_settlement,
)


ACTUAL_SALE_COMMAND_SCHEMA_VERSION = "actual-sale-settlement-command-v1"
ACTUAL_SALE_RECEIPT_SCHEMA_VERSION = "actual-sale-settlement-receipt-v1"


class ActualSaleSettlementError(RuntimeError): pass
class ActualSaleSettlementSourceNotFoundError(ActualSaleSettlementError): pass
class ActualSaleSettlementOpportunityConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementProductConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementRevisionConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementTerminalConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementReplayConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementWindowConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementReportConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementOversellConflictError(ActualSaleSettlementError): pass
class ActualSaleSettlementSourceLineageError(ActualSaleSettlementError): pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _currency(value: str) -> str:
    result = _text(value, "settlement_currency").upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError("settlement_currency must be a three-letter currency code")
    return result


def _quantity(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
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
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_text(value: str) -> str:
    result = _text(value, "command_fingerprint").lower()
    if len(result) != 64 or any(c not in "0123456789abcdef" for c in result):
        raise ValueError("command_fingerprint must be SHA-256 text")
    return result


def owned_inventory_product_key_from_receipt(record: GoodsReceiptRecord) -> OwnedInventoryProductKey:
    source = record.source_manifest
    return OwnedInventoryProductKey(
        opportunity_identity=source.opportunity_identity,
        source_platform=source.source_platform,
        supplier_id=source.supplier_id,
        sourcing_product_id=source.sourcing_product_id,
        external_product_reference=source.external_product_reference,
        option_reference=source.option_reference,
        sku_reference=source.sku_reference,
        quantity_unit=record.quantity_unit,
    )


@dataclass(frozen=True, slots=True)
class AdmitActualSaleSettlementCommand:
    command_id: str
    opportunity_id: str
    anchor_goods_receipt_id: str
    predecessor_settlement_id: str | None
    marketplace: str
    seller_account_reference: str
    marketplace_product_reference: str
    marketplace_option_reference: str | None
    marketplace_sku_reference: str | None
    external_report_reference: str
    transaction_references: tuple[str, ...]
    period_start: datetime
    period_end: datetime
    fulfilled_outbound_quantity: int
    cancelled_quantity: int
    refunded_quantity: int
    returned_quantity: int
    quantity_unit: str
    settlement_currency: str
    fixed_monetary_facts: tuple[ActualSaleMonetaryFact, ...]
    other_sale_side_costs: OtherActualSaleCosts
    payout: ActualSalePayoutFact
    finality: ActualSaleFinalityFact
    operator_id: str
    requested_at: datetime
    policy_name: str = ACTUAL_SALE_POLICY_NAME
    policy_version: str = ACTUAL_SALE_POLICY_VERSION
    schema_version: str = ACTUAL_SALE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "opportunity_id", "anchor_goods_receipt_id", "seller_account_reference", "marketplace_product_reference", "external_report_reference", "quantity_unit", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "marketplace", _text(self.marketplace, "marketplace").upper())
        for name in ("predecessor_settlement_id", "marketplace_option_reference", "marketplace_sku_reference"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if not isinstance(self.transaction_references, tuple):
            raise TypeError("transaction_references must be tuple")
        transactions = tuple(_text(v, "transaction_reference") for v in self.transaction_references)
        if len(set(transactions)) != len(transactions):
            raise ValueError("transaction references must be unique")
        object.__setattr__(self, "transaction_references", transactions)
        for name in ("period_start", "period_end", "requested_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.period_start >= self.period_end:
            raise ValueError("period_start must precede period_end")
        if self.requested_at < self.period_end:
            raise ValueError("requested_at cannot precede closed period_end")
        for name in ("fulfilled_outbound_quantity", "cancelled_quantity", "refunded_quantity", "returned_quantity"):
            object.__setattr__(self, name, _quantity(getattr(self, name), name))
        if self.refunded_quantity > self.fulfilled_outbound_quantity or self.returned_quantity > self.fulfilled_outbound_quantity:
            raise ValueError("refunded/returned quantity cannot exceed fulfilled outbound")
        object.__setattr__(self, "settlement_currency", _currency(self.settlement_currency))
        if not isinstance(self.fixed_monetary_facts, tuple) or any(not isinstance(v, ActualSaleMonetaryFact) for v in self.fixed_monetary_facts):
            raise TypeError("fixed_monetary_facts must contain ActualSaleMonetaryFact")
        if not isinstance(self.other_sale_side_costs, OtherActualSaleCosts):
            raise TypeError("other_sale_side_costs has unsupported type")
        if not isinstance(self.payout, ActualSalePayoutFact) or not isinstance(self.finality, ActualSaleFinalityFact):
            raise TypeError("payout/finality has unsupported type")
        if (self.policy_name, self.policy_version) != (ACTUAL_SALE_POLICY_NAME, ACTUAL_SALE_POLICY_VERSION):
            raise ValueError("unsupported actual sale settlement policy")
        if self.schema_version != ACTUAL_SALE_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale settlement command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ActualSaleSettlementReceipt:
    command_id: str
    settlement_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = ACTUAL_SALE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "settlement_id", _text(self.settlement_id, "settlement_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != ACTUAL_SALE_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale settlement receipt schema")


@dataclass(frozen=True, slots=True)
class ActualSaleSettlementPublication:
    settlement: ActualSaleSettlement
    receipt: ActualSaleSettlementReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.settlement, ActualSaleSettlement) or not isinstance(self.receipt, ActualSaleSettlementReceipt):
            raise TypeError("publication contains unsupported values")
        if self.receipt.settlement_id != self.settlement.settlement_id:
            raise ValueError("receipt must reference settlement")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class ActualSaleSettlementRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> ActualSaleSettlementPublication | None: ...
    def get_goods_receipt(self, record_id: str) -> GoodsReceiptRecord | None: ...
    def list_goods_receipts_for_opportunity(self, opportunity_id: str) -> tuple[GoodsReceiptRecord, ...]: ...
    def get_settlement(self, settlement_id: str) -> ActualSaleSettlement | None: ...
    def get_chain_tip_for_subject(self, manifest: ActualSaleSettlementSourceManifest) -> ActualSaleSettlement | None: ...
    def list_complete_settlements_for_product(self, product_key: OwnedInventoryProductKey) -> tuple[ActualSaleSettlement, ...]: ...
    def save(self, command, settlement, receipt) -> ActualSaleSettlementPublication: ...


def _same_subject(left: ActualSaleSettlementSourceManifest, right: ActualSaleSettlementSourceManifest) -> bool:
    return (
        left.product_key == right.product_key
        and left.marketplace == right.marketplace
        and left.seller_account_reference == right.seller_account_reference
        and left.external_report_reference == right.external_report_reference
    )


def _inventory_safe(receipts: tuple[GoodsReceiptRecord, ...], settlements: tuple[ActualSaleSettlement, ...]) -> bool:
    boundaries = sorted({value.period_end for value in settlements})
    for boundary in boundaries:
        inbound = sum(value.sellable_quantity for value in receipts if value.inspected_at < boundary)
        outbound = sum(value.fulfilled_outbound_quantity for value in settlements if value.period_end <= boundary)
        if outbound > inbound:
            return False
    return True


class AdmitActualSaleSettlement:
    def __init__(self, repository: ActualSaleSettlementRepository, *, settlement_id_generator: Callable[[], str], admitted_clock: Callable[[], datetime], committed_clock: Callable[[], datetime]) -> None:
        if not all(callable(v) for v in (settlement_id_generator, admitted_clock, committed_clock)):
            raise TypeError("actual sale settlement dependencies must be callable")
        self._repository = repository
        self._identity = settlement_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(self, command: AdmitActualSaleSettlementCommand) -> ActualSaleSettlementPublication:
        if not isinstance(command, AdmitActualSaleSettlementCommand):
            raise TypeError("command must be AdmitActualSaleSettlementCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        anchor = self._repository.get_goods_receipt(command.anchor_goods_receipt_id)
        if anchor is None:
            raise ActualSaleSettlementSourceNotFoundError("exact Goods Receipt anchor is missing")
        key = owned_inventory_product_key_from_receipt(anchor)
        if key.opportunity_identity.opportunity_id != command.opportunity_id:
            raise ActualSaleSettlementOpportunityConflictError("Goods Receipt differs from route Opportunity")
        if command.quantity_unit != key.quantity_unit:
            raise ActualSaleSettlementProductConflictError("quantity unit differs from exact product key")
        receipts = tuple(
            value for value in self._repository.list_goods_receipts_for_opportunity(command.opportunity_id)
            if owned_inventory_product_key_from_receipt(value) == key
        )
        eligible = tuple(sorted((v for v in receipts if v.inspected_at < command.period_end), key=lambda v: (v.inspected_at.astimezone(timezone.utc), v.record_id)))
        if anchor.record_id not in {v.record_id for v in eligible}:
            raise ActualSaleSettlementProductConflictError("anchor Goods Receipt is not eligible for evaluation window")
        purchase_ids: list[str] = []
        for value in eligible:
            purchase_id = value.source_manifest.purchase_execution_record_id
            if purchase_id not in purchase_ids:
                purchase_ids.append(purchase_id)
        manifest = ActualSaleSettlementSourceManifest(
            product_key=key,
            anchor_goods_receipt_id=anchor.record_id,
            eligible_goods_receipt_ids=tuple(v.record_id for v in eligible),
            contributing_purchase_execution_ids=tuple(purchase_ids),
            marketplace=command.marketplace,
            seller_account_reference=command.seller_account_reference,
            marketplace_product_reference=command.marketplace_product_reference,
            marketplace_option_reference=command.marketplace_option_reference,
            marketplace_sku_reference=command.marketplace_sku_reference,
            external_report_reference=command.external_report_reference,
            transaction_references=command.transaction_references,
        )
        tip = self._repository.get_chain_tip_for_subject(manifest)
        late_replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if late_replay is not None:
            return replace(late_replay, replayed=True)
        if command.predecessor_settlement_id is None:
            if tip is not None:
                raise ActualSaleSettlementRevisionConflictError("first settlement revision already exists")
            revision = 1
        else:
            predecessor = self._repository.get_settlement(command.predecessor_settlement_id)
            if predecessor is None:
                raise ActualSaleSettlementSourceNotFoundError("exact predecessor settlement is missing")
            if not _same_subject(predecessor.source_manifest, manifest) or predecessor.period_start != command.period_start or predecessor.period_end != command.period_end:
                raise ActualSaleSettlementRevisionConflictError("predecessor belongs to a different immutable sale scope")
            if (
                predecessor.source_manifest.marketplace_product_reference
                != manifest.marketplace_product_reference
                or predecessor.source_manifest.marketplace_option_reference
                != manifest.marketplace_option_reference
                or predecessor.source_manifest.marketplace_sku_reference
                != manifest.marketplace_sku_reference
            ):
                raise ActualSaleSettlementRevisionConflictError(
                    "marketplace product identity cannot change across revisions"
                )
            if tip is None or tip.settlement_id != predecessor.settlement_id:
                raise ActualSaleSettlementRevisionConflictError("predecessor is not exact chain tip")
            if predecessor.state is ActualSaleSettlementState.COMPLETE:
                raise ActualSaleSettlementTerminalConflictError("COMPLETE actual sale settlement is terminal")
            if predecessor.settlement_currency != command.settlement_currency:
                raise ActualSaleSettlementRevisionConflictError("settlement currency cannot change")
            for old, new in zip(predecessor.fixed_monetary_facts, command.fixed_monetary_facts, strict=True):
                if old.availability is not ActualSaleFactAvailability.UNKNOWN and new.availability is ActualSaleFactAvailability.UNKNOWN:
                    raise ActualSaleSettlementRevisionConflictError("resolved sale fact cannot regress to UNKNOWN")
            if predecessor.other_sale_side_costs.availability is not ActualSaleFactAvailability.UNKNOWN and command.other_sale_side_costs.availability is ActualSaleFactAvailability.UNKNOWN:
                raise ActualSaleSettlementRevisionConflictError("resolved other cost scope cannot regress to UNKNOWN")
            revision = predecessor.revision + 1
        reasons = evaluate_actual_sale_settlement(command.fixed_monetary_facts, command.other_sale_side_costs, command.payout, command.finality, command.settlement_currency)
        state = ActualSaleSettlementState.BLOCKED if reasons else ActualSaleSettlementState.COMPLETE
        settlement = ActualSaleSettlement(
            settlement_id=_text(self._identity(), "settlement_id"), source_manifest=manifest,
            revision=revision, predecessor_settlement_id=command.predecessor_settlement_id,
            period_start=command.period_start, period_end=command.period_end,
            fulfilled_outbound_quantity=command.fulfilled_outbound_quantity,
            cancelled_quantity=command.cancelled_quantity, refunded_quantity=command.refunded_quantity,
            returned_quantity=command.returned_quantity, quantity_unit=command.quantity_unit,
            settlement_currency=command.settlement_currency, fixed_monetary_facts=command.fixed_monetary_facts,
            other_sale_side_costs=command.other_sale_side_costs, payout=command.payout,
            finality=command.finality, state=state, blocking_reasons=reasons,
            operator_id=command.operator_id, requested_at=command.requested_at,
            admitted_at=_aware(self._admitted(), "admitted_at"), policy_name=command.policy_name,
            policy_version=command.policy_version,
        )
        if state is ActualSaleSettlementState.COMPLETE:
            existing = self._repository.list_complete_settlements_for_product(key)
            if not _inventory_safe(receipts, (*existing, settlement)):
                raise ActualSaleSettlementOversellConflictError("COMPLETE outbound exceeds chronological sellable inventory")
        receipt = ActualSaleSettlementReceipt(command.command_id, settlement.settlement_id, command.fingerprint, _aware(self._committed(), "committed_at"))
        return self._repository.save(command, settlement, receipt)


__all__ = [name for name in globals() if name.startswith(("ActualSale", "AdmitActualSale", "ACTUAL_SALE")) or name in {"owned_inventory_product_key_from_receipt"}]
