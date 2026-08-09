"""Application owner for immutable physical Goods Receipt events."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    GOODS_RECEIPT_POLICY_NAME,
    GOODS_RECEIPT_POLICY_VERSION,
    GoodsReceiptEvidenceReference,
    GoodsReceiptRecord,
    GoodsReceiptSourceManifest,
    PurchaseExecutionRecord,
)


GOODS_RECEIPT_COMMAND_SCHEMA_VERSION = "goods-receipt-command-v1"
GOODS_RECEIPT_RECEIPT_SCHEMA_VERSION = "goods-receipt-command-receipt-v1"


class GoodsReceiptError(RuntimeError):
    pass


class GoodsReceiptSourceNotFoundError(GoodsReceiptError):
    pass


class GoodsReceiptOpportunityConflictError(GoodsReceiptError):
    pass


class GoodsReceiptUnitConflictError(GoodsReceiptError):
    pass


class GoodsReceiptCumulativeQuantityConflictError(GoodsReceiptError):
    pass


class GoodsReceiptReplayConflictError(GoodsReceiptError):
    pass


class GoodsReceiptSourceLineageError(GoodsReceiptError):
    pass


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


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_integer(value: int, name: str) -> int:
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
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_text(value: str) -> str:
    result = _text(value, "command_fingerprint").lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError("command_fingerprint must be SHA-256 text")
    return result


@dataclass(frozen=True, slots=True)
class AdmitGoodsReceiptCommand:
    command_id: str
    opportunity_id: str
    purchase_execution_record_id: str
    received_quantity: int
    quantity_unit: str
    sellable_quantity: int
    damaged_quantity: int
    evidence_references: tuple[GoodsReceiptEvidenceReference, ...]
    delivery_reference: str | None
    operator_id: str
    received_at: datetime
    inspected_at: datetime
    requested_at: datetime
    policy_name: str = GOODS_RECEIPT_POLICY_NAME
    policy_version: str = GOODS_RECEIPT_POLICY_VERSION
    schema_version: str = GOODS_RECEIPT_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "opportunity_id",
            "purchase_execution_record_id",
            "quantity_unit",
            "operator_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "received_quantity", _positive_integer(self.received_quantity, "received_quantity")
        )
        object.__setattr__(
            self, "sellable_quantity", _non_negative_integer(self.sellable_quantity, "sellable_quantity")
        )
        object.__setattr__(
            self, "damaged_quantity", _non_negative_integer(self.damaged_quantity, "damaged_quantity")
        )
        if self.sellable_quantity + self.damaged_quantity != self.received_quantity:
            raise ValueError("sellable_quantity plus damaged_quantity must equal received_quantity")
        if not isinstance(self.evidence_references, tuple) or not self.evidence_references:
            raise ValueError("evidence_references must be a non-empty tuple")
        if any(
            not isinstance(value, GoodsReceiptEvidenceReference)
            for value in self.evidence_references
        ):
            raise TypeError("evidence_references contains an unsupported value")
        ordered = tuple(
            sorted(
                self.evidence_references,
                key=lambda value: (
                    value.reference,
                    value.observed_at.astimezone(timezone.utc).isoformat(),
                ),
            )
        )
        if len({value.reference for value in ordered}) != len(ordered):
            raise ValueError("Goods Receipt evidence references must be unique")
        object.__setattr__(self, "evidence_references", ordered)
        object.__setattr__(
            self, "delivery_reference", _optional_text(self.delivery_reference, "delivery_reference")
        )
        for name in ("received_at", "inspected_at", "requested_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.inspected_at < self.received_at:
            raise ValueError("inspected_at cannot precede received_at")
        if (
            self.policy_name != GOODS_RECEIPT_POLICY_NAME
            or self.policy_version != GOODS_RECEIPT_POLICY_VERSION
        ):
            raise ValueError("unsupported Goods Receipt policy")
        if self.schema_version != GOODS_RECEIPT_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Goods Receipt command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class GoodsReceiptCommandReceipt:
    command_id: str
    record_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = GOODS_RECEIPT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "record_id", _text(self.record_id, "record_id"))
        object.__setattr__(
            self, "command_fingerprint", _fingerprint_text(self.command_fingerprint)
        )
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != GOODS_RECEIPT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Goods Receipt command receipt schema")


@dataclass(frozen=True, slots=True)
class GoodsReceiptPublication:
    record: GoodsReceiptRecord
    receipt: GoodsReceiptCommandReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.record, GoodsReceiptRecord):
            raise TypeError("record must be GoodsReceiptRecord")
        if not isinstance(self.receipt, GoodsReceiptCommandReceipt):
            raise TypeError("receipt must be GoodsReceiptCommandReceipt")
        if self.receipt.record_id != self.record.record_id:
            raise ValueError("command receipt must reference Goods Receipt Record")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class GoodsReceiptRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> GoodsReceiptPublication | None: ...
    def get_purchase_execution_record(self, record_id: str) -> PurchaseExecutionRecord | None: ...
    def get_cumulative_received_quantity(self, purchase_execution_record_id: str) -> int: ...
    def save(self, command, record, receipt) -> GoodsReceiptPublication: ...


def goods_receipt_manifest_from_purchase(
    purchase: PurchaseExecutionRecord,
) -> GoodsReceiptSourceManifest:
    source = purchase.source_manifest
    return GoodsReceiptSourceManifest(
        opportunity_identity=source.opportunity_identity,
        purchase_execution_record_id=purchase.record_id,
        real_money_execution_intent_id=source.real_money_execution_intent_id,
        sourcing_admission_id=source.sourcing_admission_id,
        sourcing_admission_revision=source.sourcing_admission_revision,
        supplier_id=source.supplier_id,
        source_platform=source.source_platform,
        external_supplier_reference=source.external_supplier_reference,
        sourcing_product_id=source.sourcing_product_id,
        external_product_reference=source.external_product_reference,
        option_reference=source.option_reference,
        sku_reference=source.sku_reference,
        quote_id=source.quote_id,
        quote_revision=source.quote_revision,
        executed_quantity=purchase.actual_quantity,
        executed_quantity_unit=purchase.actual_quantity_unit,
        external_order_reference=purchase.external_order_reference,
        founder_id=purchase.founder_id,
        purchase_executed_at=purchase.executed_at,
        purchase_policy_name=purchase.policy_name,
        purchase_policy_version=purchase.policy_version,
        purchase_record_schema_version=purchase.schema_version,
    )


class AdmitGoodsReceipt:
    def __init__(
        self,
        repository: GoodsReceiptRepository,
        *,
        record_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (record_id_generator, admitted_clock, committed_clock)):
            raise TypeError("Goods Receipt dependencies must be callable")
        self._repository = repository
        self._identity = record_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(self, command: AdmitGoodsReceiptCommand) -> GoodsReceiptPublication:
        if not isinstance(command, AdmitGoodsReceiptCommand):
            raise TypeError("command must be AdmitGoodsReceiptCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        purchase = self._repository.get_purchase_execution_record(
            command.purchase_execution_record_id
        )
        if purchase is None:
            raise GoodsReceiptSourceNotFoundError("exact Purchase Execution Record is missing")
        source = purchase.source_manifest
        if source.opportunity_identity.opportunity_id != command.opportunity_id:
            raise GoodsReceiptOpportunityConflictError(
                "Purchase Execution Record differs from route Opportunity"
            )
        if command.quantity_unit != purchase.actual_quantity_unit:
            raise GoodsReceiptUnitConflictError(
                "Goods Receipt quantity unit differs from Purchase Execution"
            )
        cumulative = self._repository.get_cumulative_received_quantity(purchase.record_id)
        if cumulative + command.received_quantity > purchase.actual_quantity:
            raise GoodsReceiptCumulativeQuantityConflictError(
                "Goods Receipt cumulative quantity exceeds Purchase Execution quantity"
            )
        record = GoodsReceiptRecord(
            record_id=_text(self._identity(), "record_id"),
            source_manifest=goods_receipt_manifest_from_purchase(purchase),
            received_quantity=command.received_quantity,
            quantity_unit=command.quantity_unit,
            sellable_quantity=command.sellable_quantity,
            damaged_quantity=command.damaged_quantity,
            evidence_references=command.evidence_references,
            delivery_reference=command.delivery_reference,
            operator_id=command.operator_id,
            received_at=command.received_at,
            inspected_at=command.inspected_at,
            requested_at=command.requested_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
            policy_name=command.policy_name,
            policy_version=command.policy_version,
        )
        receipt = GoodsReceiptCommandReceipt(
            command_id=command.command_id,
            record_id=record.record_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save(command, record, receipt)


__all__ = [
    name
    for name in globals()
    if name.startswith(("GoodsReceipt", "AdmitGoods", "GOODS_RECEIPT"))
    or name == "goods_receipt_manifest_from_purchase"
]
