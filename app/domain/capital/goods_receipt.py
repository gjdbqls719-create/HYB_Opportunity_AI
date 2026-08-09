"""Immutable physical Goods Receipt event authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.decision_engine import OpportunityIdentity


GOODS_RECEIPT_RECORD_SCHEMA_VERSION = "goods-receipt-record-v1"
GOODS_RECEIPT_SOURCE_MANIFEST_SCHEMA_VERSION = "goods-receipt-source-manifest-v1"
GOODS_RECEIPT_EVIDENCE_SCHEMA_VERSION = "goods-receipt-evidence-v1"
GOODS_RECEIPT_POLICY_NAME = "exact-purchase-execution-goods-receipt"
GOODS_RECEIPT_POLICY_VERSION = "1.0.0"


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


@dataclass(frozen=True, slots=True)
class GoodsReceiptEvidenceReference:
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str = GOODS_RECEIPT_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("reference", "operator_id", "collection_method"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.schema_version != GOODS_RECEIPT_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported Goods Receipt evidence schema")


@dataclass(frozen=True, slots=True)
class GoodsReceiptSourceManifest:
    opportunity_identity: OpportunityIdentity
    purchase_execution_record_id: str
    real_money_execution_intent_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quote_id: str
    quote_revision: int
    executed_quantity: int
    executed_quantity_unit: str
    external_order_reference: str
    founder_id: str
    purchase_executed_at: datetime
    purchase_policy_name: str
    purchase_policy_version: str
    purchase_record_schema_version: str
    schema_version: str = GOODS_RECEIPT_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "purchase_execution_record_id",
            "real_money_execution_intent_id",
            "sourcing_admission_id",
            "supplier_id",
            "source_platform",
            "sourcing_product_id",
            "external_product_reference",
            "quote_id",
            "executed_quantity_unit",
            "external_order_reference",
            "founder_id",
            "purchase_policy_name",
            "purchase_policy_version",
            "purchase_record_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("external_supplier_reference", "option_reference", "sku_reference"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision", "executed_quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        object.__setattr__(
            self, "purchase_executed_at", _aware(self.purchase_executed_at, "purchase_executed_at")
        )
        if self.schema_version != GOODS_RECEIPT_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Goods Receipt source manifest schema")


@dataclass(frozen=True, slots=True)
class GoodsReceiptRecord:
    record_id: str
    source_manifest: GoodsReceiptSourceManifest
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
    admitted_at: datetime
    policy_name: str = GOODS_RECEIPT_POLICY_NAME
    policy_version: str = GOODS_RECEIPT_POLICY_VERSION
    schema_version: str = GOODS_RECEIPT_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _text(self.record_id, "record_id"))
        if not isinstance(self.source_manifest, GoodsReceiptSourceManifest):
            raise TypeError("source_manifest must be GoodsReceiptSourceManifest")
        object.__setattr__(
            self, "received_quantity", _positive_integer(self.received_quantity, "received_quantity")
        )
        object.__setattr__(self, "quantity_unit", _text(self.quantity_unit, "quantity_unit"))
        object.__setattr__(
            self, "sellable_quantity", _non_negative_integer(self.sellable_quantity, "sellable_quantity")
        )
        object.__setattr__(
            self, "damaged_quantity", _non_negative_integer(self.damaged_quantity, "damaged_quantity")
        )
        if self.sellable_quantity + self.damaged_quantity != self.received_quantity:
            raise ValueError("sellable_quantity plus damaged_quantity must equal received_quantity")
        if self.quantity_unit != self.source_manifest.executed_quantity_unit:
            raise ValueError("Goods Receipt quantity unit must equal Purchase Execution unit")
        if not isinstance(self.evidence_references, tuple) or not self.evidence_references:
            raise ValueError("evidence_references must be a non-empty tuple")
        if any(
            not isinstance(value, GoodsReceiptEvidenceReference)
            for value in self.evidence_references
        ):
            raise TypeError("evidence_references contains an unsupported value")
        references = tuple(value.reference for value in self.evidence_references)
        if len(set(references)) != len(references):
            raise ValueError("Goods Receipt evidence references must be unique")
        object.__setattr__(
            self, "delivery_reference", _optional_text(self.delivery_reference, "delivery_reference")
        )
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        if any(value.operator_id != self.operator_id for value in self.evidence_references):
            raise ValueError("all Goods Receipt evidence must belong to command operator")
        for name in ("received_at", "inspected_at", "requested_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.received_at < self.source_manifest.purchase_executed_at:
            raise ValueError("received_at cannot precede Purchase Execution")
        if self.inspected_at < self.received_at:
            raise ValueError("inspected_at cannot precede received_at")
        if self.admitted_at < self.inspected_at:
            raise ValueError("admitted_at cannot precede inspection")
        if (
            self.policy_name != GOODS_RECEIPT_POLICY_NAME
            or self.policy_version != GOODS_RECEIPT_POLICY_VERSION
        ):
            raise ValueError("unsupported Goods Receipt policy")
        if self.schema_version != GOODS_RECEIPT_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported Goods Receipt Record schema")


__all__ = [name for name in globals() if name.startswith(("GoodsReceipt", "GOODS_RECEIPT"))]
