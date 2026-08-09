"""Application owner for exact-source Real-Money Execution safety intent."""

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
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    REAL_MONEY_EXECUTION_SAFETY_POLICY_NAME,
    REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION,
    CapitalGateAssessment,
    DeployableCapitalSnapshot,
    FounderCapitalApproval,
    IntendedOrderQuantity,
    PlannedAcquisitionCapitalRequirement,
    RealMoneyExecutionIntent,
    RealMoneyExecutionIntentBlockingReasonCode,
    RealMoneyExecutionIntentState,
    RealMoneyExecutionSourceManifest,
)
from app.domain.sourcing import FounderSourcingAdmission


REAL_MONEY_EXECUTION_INTENT_COMMAND_SCHEMA_VERSION = (
    "real-money-execution-intent-command-v1"
)
REAL_MONEY_EXECUTION_INTENT_RECEIPT_SCHEMA_VERSION = (
    "real-money-execution-intent-receipt-v1"
)


class RealMoneyExecutionIntentError(RuntimeError):
    pass


class RealMoneyExecutionIntentSourceNotFoundError(RealMoneyExecutionIntentError):
    pass


class RealMoneyExecutionIntentPolicyError(RealMoneyExecutionIntentError):
    pass


class RealMoneyExecutionIntentReplayConflictError(RealMoneyExecutionIntentError):
    pass


class RealMoneyExecutionIntentReadyConflictError(RealMoneyExecutionIntentError):
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
class EvaluateRealMoneyExecutionIntentCommand:
    command_id: str
    founder_capital_approval_id: str
    quote_id: str
    quote_revision: int
    current_deployable_capital_snapshot_id: str
    execution_quantity: int
    execution_quantity_unit: str
    planned_execution_amount: Decimal
    currency: str
    founder_id: str
    requested_at: datetime
    confirmed_at: datetime
    current_execution_confirmed: bool
    policy_name: str = REAL_MONEY_EXECUTION_SAFETY_POLICY_NAME
    policy_version: str = REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION
    schema_version: str = REAL_MONEY_EXECUTION_INTENT_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "founder_capital_approval_id",
            "quote_id",
            "current_deployable_capital_snapshot_id",
            "execution_quantity_unit",
            "founder_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "quote_revision", _positive_integer(self.quote_revision, "quote_revision")
        )
        object.__setattr__(
            self,
            "execution_quantity",
            _positive_integer(self.execution_quantity, "execution_quantity"),
        )
        object.__setattr__(
            self,
            "planned_execution_amount",
            _positive_money(self.planned_execution_amount, "planned_execution_amount"),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        for name in ("requested_at", "confirmed_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if not isinstance(self.current_execution_confirmed, bool):
            raise TypeError("current_execution_confirmed must be bool")
        if (
            self.policy_name != REAL_MONEY_EXECUTION_SAFETY_POLICY_NAME
            or self.policy_version != REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION
        ):
            raise ValueError("unsupported Real-Money Execution safety policy")
        if self.schema_version != REAL_MONEY_EXECUTION_INTENT_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Real-Money Execution Intent command schema")

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
class RealMoneyExecutionIntentReceipt:
    command_id: str
    intent_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = REAL_MONEY_EXECUTION_INTENT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        object.__setattr__(
            self, "command_fingerprint", _fingerprint_text(self.command_fingerprint)
        )
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != REAL_MONEY_EXECUTION_INTENT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Real-Money Execution Intent receipt schema")


@dataclass(frozen=True, slots=True)
class RealMoneyExecutionIntentPublication:
    intent: RealMoneyExecutionIntent
    receipt: RealMoneyExecutionIntentReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.intent, RealMoneyExecutionIntent):
            raise TypeError("intent must be RealMoneyExecutionIntent")
        if not isinstance(self.receipt, RealMoneyExecutionIntentReceipt):
            raise TypeError("receipt must be RealMoneyExecutionIntentReceipt")
        if self.receipt.intent_id != self.intent.intent_id:
            raise ValueError("receipt must reference Real-Money Execution Intent")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class RealMoneyExecutionIntentRepository(Protocol):
    def get_founder_capital_approval(self, approval_id: str) -> FounderCapitalApproval | None: ...
    def get_capital_gate(self, gate_id: str) -> CapitalGateAssessment | None: ...
    def get_capital_requirement(self, requirement_id: str) -> PlannedAcquisitionCapitalRequirement | None: ...
    def get_intended_order_quantity(self, intent_id: str) -> IntendedOrderQuantity | None: ...
    def get_sourcing_admission(self, admission_id: str, revision: int) -> FounderSourcingAdmission | None: ...
    def get_deployable_capital_snapshot(self, snapshot_id: str) -> DeployableCapitalSnapshot | None: ...
    def validate_replay(self, command_id: str, fingerprint: str) -> RealMoneyExecutionIntentPublication | None: ...
    def find_ready_alias(self, approval_id: str, action_fingerprint: str) -> RealMoneyExecutionIntent | None: ...
    def save_alias(self, command, intent, receipt) -> RealMoneyExecutionIntentPublication: ...
    def save_intent(self, command, intent, receipt) -> RealMoneyExecutionIntentPublication: ...


class EvaluateRealMoneyExecutionIntent:
    def __init__(
        self,
        repository: RealMoneyExecutionIntentRepository,
        *,
        execution_intent_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(
            callable(value)
            for value in (
                execution_intent_id_generator,
                evaluated_clock,
                committed_clock,
            )
        ):
            raise TypeError("Real-Money Execution Intent dependencies must be callable")
        self._repository = repository
        self._identity = execution_intent_id_generator
        self._evaluated = evaluated_clock
        self._committed = committed_clock

    def execute(
        self, command: EvaluateRealMoneyExecutionIntentCommand
    ) -> RealMoneyExecutionIntentPublication:
        if not isinstance(command, EvaluateRealMoneyExecutionIntentCommand):
            raise TypeError("command must be EvaluateRealMoneyExecutionIntentCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        alias = self._repository.find_ready_alias(
            command.founder_capital_approval_id, command.action_fingerprint
        )
        if alias is not None:
            alias_receipt = RealMoneyExecutionIntentReceipt(
                command_id=command.command_id,
                intent_id=alias.intent_id,
                command_fingerprint=command.fingerprint,
                committed_at=_aware(self._committed(), "committed_at"),
            )
            return self._repository.save_alias(command, alias, alias_receipt)

        approval = self._required(
            self._repository.get_founder_capital_approval(
                command.founder_capital_approval_id
            ),
            "exact Founder Capital Approval",
        )
        gate = self._required(
            self._repository.get_capital_gate(approval.capital_gate_id),
            "exact Capital Gate",
        )
        requirement = self._required(
            self._repository.get_capital_requirement(approval.capital_requirement_id),
            "exact Planned Acquisition Capital Requirement",
        )
        intended = self._required(
            self._repository.get_intended_order_quantity(
                approval.intended_order_quantity_id
            ),
            "exact Intended Order Quantity",
        )
        gate_manifest = gate.source_manifest
        admission = self._required(
            self._repository.get_sourcing_admission(
                gate_manifest.sourcing_admission_id,
                gate_manifest.sourcing_admission_revision,
            ),
            "exact Sourcing Admission and Quote revision",
        )
        current_capital = self._required(
            self._repository.get_deployable_capital_snapshot(
                command.current_deployable_capital_snapshot_id
            ),
            "exact current Deployable Capital Snapshot",
        )
        evaluated_at = _aware(self._evaluated(), "evaluated_at")

        reasons = self.blocking_reasons(
            command,
            approval,
            gate,
            requirement,
            intended,
            admission,
            current_capital,
            evaluated_at,
        )
        state = (
            RealMoneyExecutionIntentState.BLOCKED
            if reasons
            else RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
        )
        source = gate.source_manifest
        manifest = RealMoneyExecutionSourceManifest(
            opportunity_identity=approval.opportunity_identity,
            founder_capital_approval_id=approval.approval_id,
            capital_gate_id=gate.gate_id,
            capital_requirement_id=requirement.requirement_id,
            intended_order_quantity_id=intended.intent_id,
            sourcing_admission_id=source.sourcing_admission_id,
            sourcing_admission_revision=source.sourcing_admission_revision,
            quote_id=command.quote_id,
            quote_revision=command.quote_revision,
            current_deployable_capital_snapshot_id=current_capital.snapshot_id,
            execution_quantity=command.execution_quantity,
            execution_quantity_unit=command.execution_quantity_unit,
            planned_execution_amount=command.planned_execution_amount,
            currency=command.currency,
            founder_id=command.founder_id,
            confirmed_at=command.confirmed_at,
            current_execution_confirmed=command.current_execution_confirmed,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
        )
        intent = RealMoneyExecutionIntent(
            intent_id=_text(self._identity(), "intent_id"),
            source_manifest=manifest,
            state=state,
            blocking_reasons=reasons,
            requested_at=command.requested_at,
            evaluated_at=evaluated_at,
        )
        receipt = RealMoneyExecutionIntentReceipt(
            command_id=command.command_id,
            intent_id=intent.intent_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save_intent(command, intent, receipt)

    @staticmethod
    def _required(value, name: str):
        if value is None:
            raise RealMoneyExecutionIntentSourceNotFoundError(f"{name} is missing")
        return value

    @staticmethod
    def blocking_reasons(
        command,
        approval,
        gate,
        requirement,
        intended,
        admission,
        current_capital,
        evaluated_at,
    ):
        reasons: set[RealMoneyExecutionIntentBlockingReasonCode] = set()
        source = gate.source_manifest
        quote = admission.quote_revision
        opportunity = approval.opportunity_identity
        if (
            gate.gate_id != approval.capital_gate_id
            or source.opportunity_identity != opportunity
            or source.capital_requirement_id != approval.capital_requirement_id
            or source.intended_order_quantity_id != approval.intended_order_quantity_id
            or requirement.requirement_id != approval.capital_requirement_id
            or requirement.opportunity_identity != opportunity
            or intended.intent_id != approval.intended_order_quantity_id
            or intended.opportunity_identity != opportunity
            or requirement.intended_order_quantity_id != intended.intent_id
            or requirement.sourcing_admission_id != source.sourcing_admission_id
            or requirement.sourcing_admission_revision
            != source.sourcing_admission_revision
            or requirement.quote_id != source.quote_id
            or requirement.quote_revision != source.quote_revision
            or intended.sourcing_admission_id != source.sourcing_admission_id
            or intended.sourcing_admission_revision != source.sourcing_admission_revision
            or intended.quote_id != source.quote_id
            or intended.quote_revision != source.quote_revision
            or admission.admission_id != source.sourcing_admission_id
            or admission.revision != source.sourcing_admission_revision
            or admission.selling_product_lineage.opportunity_identity != opportunity
            or quote.quote_id != source.quote_id
            or quote.revision != source.quote_revision
            or approval.approved_capital != requirement.planned_acquisition_capital
            or approval.currency != requirement.currency
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.APPROVAL_SOURCE_MISMATCH
            )
        if (
            approval.capital_gate_policy_name != CAPITAL_GATE_POLICY_NAME
            or approval.capital_gate_policy_version != CAPITAL_GATE_POLICY_VERSION
            or gate.policy_name != CAPITAL_GATE_POLICY_NAME
            or gate.policy_version != CAPITAL_GATE_POLICY_VERSION
            or current_capital.semantics_version
            != DEPLOYABLE_CAPITAL_SEMANTICS_VERSION
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.SOURCE_POLICY_UNSUPPORTED
            )
        if (
            command.quote_id != source.quote_id
            or command.quote_revision != source.quote_revision
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.QUOTE_REVISION_MISMATCH
            )
        if quote.valid_until is None:
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.QUOTE_VALIDITY_MISSING
            )
        elif quote.valid_until <= evaluated_at:
            reasons.add(RealMoneyExecutionIntentBlockingReasonCode.QUOTE_EXPIRED)
        if (
            command.planned_execution_amount != approval.approved_capital
            or command.planned_execution_amount
            != requirement.planned_acquisition_capital
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_AMOUNT_MISMATCH
            )
        if command.execution_quantity != intended.quantity:
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_QUANTITY_MISMATCH
            )
        if command.execution_quantity_unit != intended.quantity_unit:
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_UNIT_MISMATCH
            )
        if (
            command.currency != approval.currency
            or command.currency != requirement.currency
            or current_capital.currency != command.currency
        ):
            reasons.add(RealMoneyExecutionIntentBlockingReasonCode.CURRENCY_MISMATCH)
        if (
            current_capital.snapshot_id == approval.deployable_capital_snapshot_id
            or current_capital.operator_id != approval.founder_id
            or current_capital.as_of < approval.approved_at
            or current_capital.as_of > command.confirmed_at
            or current_capital.as_of > evaluated_at
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_SNAPSHOT_INVALID
            )
        if current_capital.amount < command.planned_execution_amount:
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_INSUFFICIENT
            )
        if (
            not command.current_execution_confirmed
            or command.founder_id != approval.founder_id
            or command.confirmed_at < approval.approved_at
            or command.confirmed_at > evaluated_at
        ):
            reasons.add(
                RealMoneyExecutionIntentBlockingReasonCode.CURRENT_EXECUTION_CONFIRMATION_MISMATCH
            )
        return tuple(sorted(reasons, key=lambda value: value.order))


__all__ = [
    name
    for name in globals()
    if name.startswith(("Evaluate", "RealMoney", "REAL_MONEY"))
]
