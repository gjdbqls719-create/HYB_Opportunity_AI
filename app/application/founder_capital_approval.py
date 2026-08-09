"""Application authority for explicit Founder Capital Approval."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    CAPITAL_GATE_POLICY_NAME,
    CAPITAL_GATE_POLICY_VERSION,
    CapitalGateAssessment,
    CapitalGateState,
    FounderCapitalApproval,
)


FOUNDER_CAPITAL_APPROVAL_COMMAND_SCHEMA_VERSION = (
    "founder-capital-approval-command-v1"
)
FOUNDER_CAPITAL_APPROVAL_RECEIPT_SCHEMA_VERSION = (
    "founder-capital-approval-receipt-v1"
)


class FounderCapitalApprovalError(RuntimeError):
    pass


class FounderCapitalApprovalSourceNotFoundError(FounderCapitalApprovalError):
    pass


class FounderCapitalApprovalGateStateError(FounderCapitalApprovalError):
    pass


class FounderCapitalApprovalAmountError(FounderCapitalApprovalError):
    pass


class FounderCapitalApprovalCurrencyError(FounderCapitalApprovalError):
    pass


class FounderCapitalApprovalPolicyError(FounderCapitalApprovalError):
    pass


class FounderCapitalApprovalReplayConflictError(FounderCapitalApprovalError):
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
        return {
            field.name: _canonical(getattr(value, field.name)) for field in fields(value)
        }
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


@dataclass(frozen=True, slots=True)
class ApproveFounderCapitalCommand:
    command_id: str
    capital_gate_id: str
    founder_id: str
    approved_capital: Decimal
    currency: str
    requested_at: datetime
    approved_at: datetime
    schema_version: str = FOUNDER_CAPITAL_APPROVAL_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "capital_gate_id", "founder_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "approved_capital", _positive_money(self.approved_capital, "approved_capital")
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "approved_at", _aware(self.approved_at, "approved_at"))
        if self.schema_version != FOUNDER_CAPITAL_APPROVAL_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Founder Capital Approval command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class FounderCapitalApprovalReceipt:
    command_id: str
    approval_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = FOUNDER_CAPITAL_APPROVAL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "approval_id", _text(self.approval_id, "approval_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != FOUNDER_CAPITAL_APPROVAL_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Founder Capital Approval receipt schema")


@dataclass(frozen=True, slots=True)
class FounderCapitalApprovalPublication:
    approval: FounderCapitalApproval
    receipt: FounderCapitalApprovalReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.approval, FounderCapitalApproval):
            raise TypeError("approval must be FounderCapitalApproval")
        if not isinstance(self.receipt, FounderCapitalApprovalReceipt):
            raise TypeError("receipt must be FounderCapitalApprovalReceipt")
        if self.receipt.approval_id != self.approval.approval_id:
            raise ValueError("receipt must reference Founder Capital Approval")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class FounderCapitalApprovalRepository(Protocol):
    def get_capital_gate(self, gate_id: str) -> CapitalGateAssessment | None: ...

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> FounderCapitalApprovalPublication | None: ...

    def save_approval(
        self, command, approval, receipt
    ) -> FounderCapitalApprovalPublication: ...


class ApproveFounderCapital:
    def __init__(
        self,
        repository: FounderCapitalApprovalRepository,
        *,
        approval_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(
            callable(value)
            for value in (approval_id_generator, admitted_clock, committed_clock)
        ):
            raise TypeError("Founder Capital Approval dependencies must be callable")
        self._repository = repository
        self._identity = approval_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(
        self, command: ApproveFounderCapitalCommand
    ) -> FounderCapitalApprovalPublication:
        if not isinstance(command, ApproveFounderCapitalCommand):
            raise TypeError("command must be ApproveFounderCapitalCommand")
        replay = self._repository.validate_replay(
            command.command_id, command.fingerprint
        )
        if replay is not None:
            return replace(replay, replayed=True)
        gate = self._repository.get_capital_gate(command.capital_gate_id)
        if gate is None:
            raise FounderCapitalApprovalSourceNotFoundError(
                "exact Capital Gate assessment is missing"
            )
        if gate.state is not CapitalGateState.PASS:
            raise FounderCapitalApprovalGateStateError(
                "only an exact Capital Gate PASS can be approved"
            )
        if (
            gate.policy_name != CAPITAL_GATE_POLICY_NAME
            or gate.policy_version != CAPITAL_GATE_POLICY_VERSION
        ):
            raise FounderCapitalApprovalPolicyError(
                "unsupported Capital Gate policy"
            )
        facts = gate.evaluated_facts
        required = facts.planned_acquisition_capital
        if required is None:
            raise FounderCapitalApprovalAmountError(
                "Capital Gate does not preserve an authoritative requirement amount"
            )
        if command.currency != facts.requirement_currency or command.currency != facts.deployable_currency:
            raise FounderCapitalApprovalCurrencyError(
                "approved currency must match the exact Capital Gate currency"
            )
        if command.approved_capital != required:
            raise FounderCapitalApprovalAmountError(
                "v1 approval must equal the exact planned acquisition capital requirement"
            )
        if command.approved_capital > facts.deployable_capital:
            raise FounderCapitalApprovalAmountError(
                "approved capital exceeds the exact Gate deployable capital"
            )
        manifest = gate.source_manifest
        approval = FounderCapitalApproval(
            approval_id=_text(self._identity(), "approval_id"),
            opportunity_identity=manifest.opportunity_identity,
            capital_gate_id=gate.gate_id,
            capital_gate_policy_name=gate.policy_name,
            capital_gate_policy_version=gate.policy_version,
            capital_requirement_id=manifest.capital_requirement_id,
            deployable_capital_snapshot_id=manifest.deployable_capital_snapshot_id,
            intended_order_quantity_id=manifest.intended_order_quantity_id,
            capital_gate_evaluated_at=gate.evaluated_at,
            approved_capital=command.approved_capital,
            currency=command.currency,
            founder_id=command.founder_id,
            requested_at=command.requested_at,
            approved_at=command.approved_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
        )
        receipt = FounderCapitalApprovalReceipt(
            command_id=command.command_id,
            approval_id=approval.approval_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save_approval(command, approval, receipt)


__all__ = [
    name
    for name in globals()
    if name.startswith(("Approve", "Founder", "FOUNDER"))
]
