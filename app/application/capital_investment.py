"""Application owners for Founder-declared Capital investment facts."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import DeployableCapitalSnapshot, IntendedOrderQuantity
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import FounderSourcingAdmission


INTENDED_ORDER_QUANTITY_COMMAND_SCHEMA_VERSION = "intended-order-quantity-command-v1"
INTENDED_ORDER_QUANTITY_RECEIPT_SCHEMA_VERSION = "intended-order-quantity-receipt-v1"
DEPLOYABLE_CAPITAL_COMMAND_SCHEMA_VERSION = "deployable-capital-command-v1"
DEPLOYABLE_CAPITAL_RECEIPT_SCHEMA_VERSION = "deployable-capital-receipt-v1"


class CapitalInvestmentFactsError(RuntimeError):
    pass


class CapitalInvestmentSourceNotFoundError(CapitalInvestmentFactsError):
    pass


class CapitalInvestmentLineageError(CapitalInvestmentFactsError):
    pass


class CapitalInvestmentReplayConflictError(CapitalInvestmentFactsError):
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


def _currency(value: str) -> str:
    result = _text(value, "currency").upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError("currency must be a three-letter code")
    return result


def _amount(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError("amount must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError("amount must be finite and non-negative")
    return value


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
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
class AdmitIntendedOrderQuantityCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    quantity: int
    quantity_unit: str
    operator_id: str
    requested_at: datetime
    declared_at: datetime
    schema_version: str = INTENDED_ORDER_QUANTITY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in ("sourcing_admission_id", "quote_id", "quantity_unit", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision", "quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if self.sourcing_admission_revision != self.quote_revision:
            raise ValueError("Sourcing Admission and Quote revisions must match")
        for name in ("requested_at", "declared_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.schema_version != INTENDED_ORDER_QUANTITY_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Intended Order Quantity command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class AdmitDeployableCapitalSnapshotCommand:
    command_id: str
    amount: Decimal
    currency: str
    as_of: datetime
    operator_id: str
    requested_at: datetime
    schema_version: str = DEPLOYABLE_CAPITAL_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "amount", _amount(self.amount))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        for name in ("as_of", "requested_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.schema_version != DEPLOYABLE_CAPITAL_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Deployable Capital command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class IntendedOrderQuantityReceipt:
    command_id: str
    intent_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = INTENDED_ORDER_QUANTITY_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != INTENDED_ORDER_QUANTITY_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Intended Order Quantity receipt schema")


@dataclass(frozen=True, slots=True)
class DeployableCapitalSnapshotReceipt:
    command_id: str
    snapshot_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = DEPLOYABLE_CAPITAL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "snapshot_id", _text(self.snapshot_id, "snapshot_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != DEPLOYABLE_CAPITAL_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Deployable Capital receipt schema")


@dataclass(frozen=True, slots=True)
class IntendedOrderQuantityPublication:
    intent: IntendedOrderQuantity
    receipt: IntendedOrderQuantityReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.intent, IntendedOrderQuantity):
            raise TypeError("intent must be IntendedOrderQuantity")
        if not isinstance(self.receipt, IntendedOrderQuantityReceipt):
            raise TypeError("receipt must be IntendedOrderQuantityReceipt")
        if self.receipt.intent_id != self.intent.intent_id:
            raise ValueError("receipt must reference intent")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


@dataclass(frozen=True, slots=True)
class DeployableCapitalPublication:
    snapshot: DeployableCapitalSnapshot
    receipt: DeployableCapitalSnapshotReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, DeployableCapitalSnapshot):
            raise TypeError("snapshot must be DeployableCapitalSnapshot")
        if not isinstance(self.receipt, DeployableCapitalSnapshotReceipt):
            raise TypeError("receipt must be DeployableCapitalSnapshotReceipt")
        if self.receipt.snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("receipt must reference snapshot")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class IntendedOrderQuantityRepository(Protocol):
    def get_sourcing_admission(self, admission_id: str, revision: int) -> FounderSourcingAdmission | None: ...
    def validate_intent_replay(self, command_id: str, fingerprint: str) -> IntendedOrderQuantityPublication | None: ...
    def save_intent(self, command, intent, receipt) -> IntendedOrderQuantityPublication: ...


class DeployableCapitalRepository(Protocol):
    def validate_capital_replay(self, command_id: str, fingerprint: str) -> DeployableCapitalPublication | None: ...
    def save_deployable_capital(self, command, snapshot, receipt) -> DeployableCapitalPublication: ...


class AdmitIntendedOrderQuantity:
    def __init__(
        self,
        repository: IntendedOrderQuantityRepository,
        *,
        intent_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (intent_id_generator, admitted_clock, committed_clock)):
            raise TypeError("Intended Order Quantity dependencies must be callable")
        self._repository = repository
        self._identity = intent_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(self, command: AdmitIntendedOrderQuantityCommand) -> IntendedOrderQuantityPublication:
        if not isinstance(command, AdmitIntendedOrderQuantityCommand):
            raise TypeError("command must be AdmitIntendedOrderQuantityCommand")
        replay = self._repository.validate_intent_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        admission = self._repository.get_sourcing_admission(
            command.sourcing_admission_id, command.sourcing_admission_revision
        )
        if admission is None:
            raise CapitalInvestmentSourceNotFoundError("exact Sourcing Admission revision is missing")
        quote = admission.quote_revision
        if admission.selling_product_lineage.opportunity_identity != command.opportunity_identity:
            raise CapitalInvestmentLineageError("Opportunity differs from Sourcing Admission")
        if (
            admission.admission_id != command.sourcing_admission_id
            or admission.revision != command.sourcing_admission_revision
            or quote.quote_id != command.quote_id
            or quote.revision != command.quote_revision
        ):
            raise CapitalInvestmentLineageError("exact Admission and Quote lineage differs")
        intent = IntendedOrderQuantity(
            intent_id=_text(self._identity(), "intent_id"),
            opportunity_identity=command.opportunity_identity,
            sourcing_admission_id=command.sourcing_admission_id,
            sourcing_admission_revision=command.sourcing_admission_revision,
            quote_id=command.quote_id,
            quote_revision=command.quote_revision,
            quantity=command.quantity,
            quantity_unit=command.quantity_unit,
            operator_id=command.operator_id,
            requested_at=command.requested_at,
            declared_at=command.declared_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
        )
        receipt = IntendedOrderQuantityReceipt(
            command.command_id,
            intent.intent_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_intent(command, intent, receipt)


class AdmitDeployableCapitalSnapshot:
    def __init__(
        self,
        repository: DeployableCapitalRepository,
        *,
        snapshot_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (snapshot_id_generator, admitted_clock, committed_clock)):
            raise TypeError("Deployable Capital dependencies must be callable")
        self._repository = repository
        self._identity = snapshot_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(self, command: AdmitDeployableCapitalSnapshotCommand) -> DeployableCapitalPublication:
        if not isinstance(command, AdmitDeployableCapitalSnapshotCommand):
            raise TypeError("command must be AdmitDeployableCapitalSnapshotCommand")
        replay = self._repository.validate_capital_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        snapshot = DeployableCapitalSnapshot(
            snapshot_id=_text(self._identity(), "snapshot_id"),
            amount=command.amount,
            currency=command.currency,
            as_of=command.as_of,
            operator_id=command.operator_id,
            requested_at=command.requested_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
        )
        receipt = DeployableCapitalSnapshotReceipt(
            command.command_id,
            snapshot.snapshot_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_deployable_capital(command, snapshot, receipt)


__all__ = [name for name in globals() if name.startswith(("Admit", "Capital", "Deployable", "Intended", "DEPLOYABLE", "INTENDED"))]
