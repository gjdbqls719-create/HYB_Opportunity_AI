"""Immutable authority that records one externally executed purchase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import OpportunityIdentity


PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION = "purchase-execution-record-v1"
PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "purchase-execution-source-manifest-v1"
)
PURCHASE_EXECUTION_EVIDENCE_SCHEMA_VERSION = "purchase-execution-evidence-v1"
PURCHASE_EXECUTION_POLICY_NAME = "exact-ready-intent-purchase-execution"
PURCHASE_EXECUTION_POLICY_VERSION = "1.0.0"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


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


def _positive_money(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _currency(value: str) -> str:
    result = _text(value, "currency").upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError("currency must be a three-letter code")
    return result


@dataclass(frozen=True, slots=True)
class PurchaseExecutionEvidenceReference:
    reference: str
    observed_at: datetime
    schema_version: str = PURCHASE_EXECUTION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _text(self.reference, "reference"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.schema_version != PURCHASE_EXECUTION_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported Purchase Execution evidence schema")


@dataclass(frozen=True, slots=True)
class PurchaseExecutionSourceManifest:
    opportunity_identity: OpportunityIdentity
    real_money_execution_intent_id: str
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
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
    current_deployable_capital_snapshot_id: str
    expected_quantity: int
    expected_quantity_unit: str
    expected_total_amount: Decimal
    currency: str
    founder_id: str
    execution_intent_evaluated_at: datetime
    execution_safety_policy_name: str
    execution_safety_policy_version: str
    schema_version: str = PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "real_money_execution_intent_id",
            "founder_capital_approval_id",
            "capital_gate_id",
            "capital_requirement_id",
            "intended_order_quantity_id",
            "sourcing_admission_id",
            "supplier_id",
            "source_platform",
            "sourcing_product_id",
            "external_product_reference",
            "quote_id",
            "current_deployable_capital_snapshot_id",
            "expected_quantity_unit",
            "founder_id",
            "execution_safety_policy_name",
            "execution_safety_policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "external_supplier_reference",
            "option_reference",
            "sku_reference",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision", "expected_quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_total_amount",
            _positive_money(self.expected_total_amount, "expected_total_amount"),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(
            self,
            "execution_intent_evaluated_at",
            _aware(self.execution_intent_evaluated_at, "execution_intent_evaluated_at"),
        )
        if self.schema_version != PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Purchase Execution source manifest schema")


@dataclass(frozen=True, slots=True)
class PurchaseExecutionRecord:
    record_id: str
    source_manifest: PurchaseExecutionSourceManifest
    actual_quantity: int
    actual_quantity_unit: str
    actual_total_committed_amount: Decimal
    currency: str
    external_order_reference: str
    founder_id: str
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceReference, ...]
    requested_at: datetime
    admitted_at: datetime
    policy_name: str = PURCHASE_EXECUTION_POLICY_NAME
    policy_version: str = PURCHASE_EXECUTION_POLICY_VERSION
    schema_version: str = PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _text(self.record_id, "record_id"))
        if not isinstance(self.source_manifest, PurchaseExecutionSourceManifest):
            raise TypeError("source_manifest must be PurchaseExecutionSourceManifest")
        object.__setattr__(
            self, "actual_quantity", _positive_integer(self.actual_quantity, "actual_quantity")
        )
        for name in ("actual_quantity_unit", "external_order_reference", "founder_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self,
            "actual_total_committed_amount",
            _positive_money(
                self.actual_total_committed_amount, "actual_total_committed_amount"
            ),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        for name in ("executed_at", "requested_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if not isinstance(self.evidence_references, tuple) or not self.evidence_references:
            raise ValueError("evidence_references must be a non-empty tuple")
        if any(
            not isinstance(value, PurchaseExecutionEvidenceReference)
            for value in self.evidence_references
        ):
            raise TypeError("evidence_references contains an unsupported value")
        references = tuple(value.reference for value in self.evidence_references)
        if len(set(references)) != len(references):
            raise ValueError("evidence references must be unique")
        source = self.source_manifest
        if (
            self.actual_quantity != source.expected_quantity
            or self.actual_quantity_unit != source.expected_quantity_unit
            or self.actual_total_committed_amount != source.expected_total_amount
            or self.currency != source.currency
            or self.founder_id != source.founder_id
        ):
            raise ValueError("actual purchase facts must exactly match READY intent")
        if self.executed_at < source.execution_intent_evaluated_at:
            raise ValueError("executed_at cannot precede READY intent evaluation")
        if self.admitted_at < self.executed_at:
            raise ValueError("admitted_at cannot precede executed_at")
        if (
            self.policy_name != PURCHASE_EXECUTION_POLICY_NAME
            or self.policy_version != PURCHASE_EXECUTION_POLICY_VERSION
        ):
            raise ValueError("unsupported Purchase Execution policy")
        if self.schema_version != PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported Purchase Execution Record schema")


__all__ = [
    name
    for name in globals()
    if name.startswith(("PurchaseExecution", "PURCHASE_EXECUTION"))
]
