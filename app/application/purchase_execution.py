"""Application owner for immutable external Purchase Execution Records."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    PURCHASE_EXECUTION_POLICY_NAME,
    PURCHASE_EXECUTION_POLICY_VERSION,
    PURCHASE_EXECUTION_POLICY_VERSION_V2,
    PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2,
    PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2,
    PurchaseExecutionEvidenceReference,
    PurchaseExecutionRecord,
    PurchaseExecutionSourceManifest,
    RealMoneyExecutionIntent,
    RealMoneyExecutionIntentState,
)
from app.domain.sourcing import FounderSourcingAdmission


PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION = "purchase-execution-command-v1"
PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION = "purchase-execution-receipt-v1"
PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION_V2 = "purchase-execution-command-v2"
PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2 = "purchase-execution-receipt-v2"


class PurchaseExecutionError(RuntimeError):
    pass


class PurchaseExecutionSourceNotFoundError(PurchaseExecutionError):
    pass


class PurchaseExecutionIntentStateError(PurchaseExecutionError):
    pass


class PurchaseExecutionExactMatchError(PurchaseExecutionError):
    pass


class PurchaseExecutionReplayConflictError(PurchaseExecutionError):
    pass


class PurchaseExecutionCardinalityConflictError(PurchaseExecutionError):
    pass


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
class RecordPurchaseExecutionCommand:
    command_id: str
    real_money_execution_intent_id: str
    quote_id: str
    quote_revision: int
    actual_quantity: int
    actual_quantity_unit: str
    actual_total_committed_amount: Decimal
    currency: str
    external_order_reference: str
    founder_id: str
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceReference, ...]
    requested_at: datetime
    policy_name: str = PURCHASE_EXECUTION_POLICY_NAME
    policy_version: str = PURCHASE_EXECUTION_POLICY_VERSION
    schema_version: str = PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "real_money_execution_intent_id",
            "quote_id",
            "actual_quantity_unit",
            "external_order_reference",
            "founder_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("quote_revision", "actual_quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        object.__setattr__(
            self,
            "actual_total_committed_amount",
            _positive_money(
                self.actual_total_committed_amount, "actual_total_committed_amount"
            ),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        for name in ("executed_at", "requested_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if not isinstance(self.evidence_references, tuple) or not self.evidence_references:
            raise ValueError("evidence_references must be a non-empty tuple")
        if any(
            not isinstance(value, PurchaseExecutionEvidenceReference)
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
            raise ValueError("evidence references must be unique")
        object.__setattr__(self, "evidence_references", ordered)
        if (
            self.policy_name != PURCHASE_EXECUTION_POLICY_NAME
            or self.policy_version != PURCHASE_EXECUTION_POLICY_VERSION
        ):
            raise ValueError("unsupported Purchase Execution policy")
        if self.schema_version != PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Purchase Execution command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)

    @property
    def action_fingerprint(self) -> str:
        return _fingerprint(
            {
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name not in {"command_id", "requested_at"}
            }
        )


@dataclass(frozen=True, slots=True)
class RecordPurchaseExecutionCommandV2:
    command_id: str
    real_money_execution_intent_id: str
    quote_id: str
    quote_revision: int
    actual_quantity: int
    actual_quantity_unit: str
    supplier_order_committed_amount: Decimal
    supplier_order_currency: str
    external_order_reference: str
    founder_id: str
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceReference, ...]
    requested_at: datetime
    policy_name: str = PURCHASE_EXECUTION_POLICY_NAME
    policy_version: str = PURCHASE_EXECUTION_POLICY_VERSION_V2
    schema_version: str = PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION_V2

    def __post_init__(self) -> None:
        for name in (
            "command_id", "real_money_execution_intent_id", "quote_id",
            "actual_quantity_unit", "external_order_reference", "founder_id",
            "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("quote_revision", "actual_quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        object.__setattr__(self, "supplier_order_committed_amount", _positive_money(self.supplier_order_committed_amount, "supplier_order_committed_amount"))
        object.__setattr__(self, "supplier_order_currency", _currency(self.supplier_order_currency))
        for name in ("executed_at", "requested_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if not isinstance(self.evidence_references, tuple) or not self.evidence_references:
            raise ValueError("evidence_references must be a non-empty tuple")
        ordered = tuple(sorted(self.evidence_references, key=lambda value: (value.reference, value.observed_at.astimezone(timezone.utc).isoformat())))
        if any(not isinstance(value, PurchaseExecutionEvidenceReference) for value in ordered):
            raise TypeError("evidence_references contains an unsupported value")
        if len({value.reference for value in ordered}) != len(ordered):
            raise ValueError("evidence references must be unique")
        object.__setattr__(self, "evidence_references", ordered)
        if self.policy_name != PURCHASE_EXECUTION_POLICY_NAME or self.policy_version != PURCHASE_EXECUTION_POLICY_VERSION_V2:
            raise ValueError("unsupported Purchase Execution policy")
        if self.schema_version != PURCHASE_EXECUTION_COMMAND_SCHEMA_VERSION_V2:
            raise ValueError("unsupported Purchase Execution command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)

    @property
    def action_fingerprint(self) -> str:
        return _fingerprint({field.name: getattr(self, field.name) for field in fields(self) if field.name not in {"command_id", "requested_at"}})


@dataclass(frozen=True, slots=True)
class PurchaseExecutionReceipt:
    command_id: str
    record_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "record_id", _text(self.record_id, "record_id"))
        object.__setattr__(
            self, "command_fingerprint", _fingerprint_text(self.command_fingerprint)
        )
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version not in {
            PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION,
            PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2,
        }:
            raise ValueError("unsupported Purchase Execution receipt schema")


@dataclass(frozen=True, slots=True)
class PurchaseExecutionPublication:
    record: PurchaseExecutionRecord
    receipt: PurchaseExecutionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.record, PurchaseExecutionRecord):
            raise TypeError("record must be PurchaseExecutionRecord")
        if not isinstance(self.receipt, PurchaseExecutionReceipt):
            raise TypeError("receipt must be PurchaseExecutionReceipt")
        if self.receipt.record_id != self.record.record_id:
            raise ValueError("receipt must reference Purchase Execution Record")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class PurchaseExecutionRepository(Protocol):
    def get_execution_intent(self, intent_id: str) -> RealMoneyExecutionIntent | None: ...
    def get_sourcing_admission(self, admission_id: str, revision: int) -> FounderSourcingAdmission | None: ...
    def validate_replay(self, command_id: str, fingerprint: str) -> PurchaseExecutionPublication | None: ...
    def find_alias(self, intent_id: str, action_fingerprint: str) -> PurchaseExecutionRecord | None: ...
    def save_alias(self, command, record, receipt) -> PurchaseExecutionPublication: ...
    def save_record(self, command, record, receipt) -> PurchaseExecutionPublication: ...


class RecordPurchaseExecution:
    def __init__(
        self,
        repository: PurchaseExecutionRepository,
        *,
        record_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (record_id_generator, admitted_clock, committed_clock)):
            raise TypeError("Purchase Execution dependencies must be callable")
        self._repository = repository
        self._identity = record_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(self, command: RecordPurchaseExecutionCommand | RecordPurchaseExecutionCommandV2) -> PurchaseExecutionPublication:
        if not isinstance(command, (RecordPurchaseExecutionCommand, RecordPurchaseExecutionCommandV2)):
            raise TypeError("command must be a supported RecordPurchaseExecutionCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        alias = self._repository.find_alias(
            command.real_money_execution_intent_id, command.action_fingerprint
        )
        if alias is not None:
            is_v2 = isinstance(command, RecordPurchaseExecutionCommandV2)
            receipt = PurchaseExecutionReceipt(
                command.command_id,
                alias.record_id,
                command.fingerprint,
                _aware(self._committed(), "committed_at"),
                PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2 if is_v2 else PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION,
            )
            return self._repository.save_alias(command, alias, receipt)

        intent = self._repository.get_execution_intent(
            command.real_money_execution_intent_id
        )
        if intent is None:
            raise PurchaseExecutionSourceNotFoundError(
                "exact Real-Money Execution Intent is missing"
            )
        if intent.state is not RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION:
            raise PurchaseExecutionIntentStateError(
                "Purchase Execution requires READY_FOR_MANUAL_EXECUTION intent"
            )
        source = intent.source_manifest
        admission = self._repository.get_sourcing_admission(
            source.sourcing_admission_id, source.sourcing_admission_revision
        )
        if admission is None:
            raise PurchaseExecutionSourceNotFoundError(
                "exact Founder Sourcing Admission is missing"
            )
        is_v2 = isinstance(command, RecordPurchaseExecutionCommandV2)
        if (
            command.quote_id != source.quote_id
            or command.quote_revision != source.quote_revision
            or command.actual_quantity != source.execution_quantity
            or command.actual_quantity_unit != source.execution_quantity_unit
            or (
                command.supplier_order_committed_amount != source.proposed_supplier_order_committed_amount
                or command.supplier_order_currency != source.supplier_order_currency
                if is_v2
                else command.actual_total_committed_amount != source.planned_execution_amount
                or command.currency != source.currency
            )
            or command.founder_id != source.founder_id
        ):
            raise PurchaseExecutionExactMatchError(
                "actual purchase must exactly match READY intent quantity, unit, amount, currency, Quote, and Founder"
            )
        quote = admission.quote_revision
        supplier = admission.supplier_identity
        product = admission.sourcing_product_identity
        if (
            admission.selling_product_lineage.opportunity_identity
            != source.opportunity_identity
            or admission.admission_id != source.sourcing_admission_id
            or admission.revision != source.sourcing_admission_revision
            or quote.quote_id != source.quote_id
            or quote.revision != source.quote_revision
            or quote.sourcing_product_id != product.sourcing_product_id
            or product.supplier_id != supplier.supplier_id
        ):
            raise PurchaseExecutionExactMatchError(
                "READY intent differs from exact Sourcing authority"
            )
        manifest = PurchaseExecutionSourceManifest(
            opportunity_identity=source.opportunity_identity,
            real_money_execution_intent_id=intent.intent_id,
            founder_capital_approval_id=source.founder_capital_approval_id,
            capital_gate_id=source.capital_gate_id,
            capital_requirement_id=source.capital_requirement_id,
            intended_order_quantity_id=source.intended_order_quantity_id,
            sourcing_admission_id=source.sourcing_admission_id,
            sourcing_admission_revision=source.sourcing_admission_revision,
            supplier_id=supplier.supplier_id,
            source_platform=supplier.source_platform,
            external_supplier_reference=supplier.external_supplier_reference,
            sourcing_product_id=product.sourcing_product_id,
            external_product_reference=product.external_product_reference,
            option_reference=product.option_reference,
            sku_reference=product.sku_reference,
            quote_id=source.quote_id,
            quote_revision=source.quote_revision,
            current_deployable_capital_snapshot_id=(
                source.current_deployable_capital_snapshot_id
            ),
            expected_quantity=source.execution_quantity,
            expected_quantity_unit=source.execution_quantity_unit,
            expected_total_amount=None if is_v2 else source.planned_execution_amount,
            currency=None if is_v2 else source.currency,
            founder_id=source.founder_id,
            execution_intent_evaluated_at=intent.evaluated_at,
            execution_safety_policy_name=source.policy_name,
            execution_safety_policy_version=source.policy_version,
            schema_version=(PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2 if is_v2 else "purchase-execution-source-manifest-v1"),
            authorized_acquisition_capital_amount=(source.authorized_acquisition_capital_amount if is_v2 else None),
            authorized_acquisition_capital_currency=(source.authorized_acquisition_capital_currency if is_v2 else None),
            proposed_supplier_order_committed_amount=(source.proposed_supplier_order_committed_amount if is_v2 else None),
            supplier_order_currency=(source.supplier_order_currency if is_v2 else None),
        )
        record = PurchaseExecutionRecord(
            record_id=_text(self._identity(), "record_id"),
            source_manifest=manifest,
            actual_quantity=command.actual_quantity,
            actual_quantity_unit=command.actual_quantity_unit,
            actual_total_committed_amount=None if is_v2 else command.actual_total_committed_amount,
            currency=None if is_v2 else command.currency,
            external_order_reference=command.external_order_reference,
            founder_id=command.founder_id,
            executed_at=command.executed_at,
            evidence_references=command.evidence_references,
            requested_at=command.requested_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            schema_version=(PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2 if is_v2 else "purchase-execution-record-v1"),
            supplier_order_committed_amount=(command.supplier_order_committed_amount if is_v2 else None),
            supplier_order_currency=(command.supplier_order_currency if is_v2 else None),
        )
        receipt = PurchaseExecutionReceipt(
            command.command_id,
            record.record_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
            PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2 if is_v2 else PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION,
        )
        return self._repository.save_record(command, record, receipt)


__all__ = [
    name
    for name in globals()
    if name.startswith(("PurchaseExecution", "RecordPurchase", "PURCHASE_EXECUTION"))
]
