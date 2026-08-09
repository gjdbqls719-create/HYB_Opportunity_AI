"""Immutable safety authority for one exact proposed manual purchase action."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity


REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION = "real-money-execution-intent-v1"
REAL_MONEY_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "real-money-execution-source-manifest-v1"
)
REAL_MONEY_EXECUTION_SAFETY_POLICY_NAME = (
    "domestic-commerce-real-money-execution-safety"
)
REAL_MONEY_EXECUTION_SAFETY_POLICY_VERSION = "1.0.0"


class RealMoneyExecutionIntentState(StrEnum):
    READY_FOR_MANUAL_EXECUTION = "ready_for_manual_execution"
    BLOCKED = "blocked"


class RealMoneyExecutionIntentBlockingReasonCode(StrEnum):
    APPROVAL_SOURCE_MISMATCH = "approval_source_mismatch"
    SOURCE_POLICY_UNSUPPORTED = "source_policy_unsupported"
    QUOTE_REVISION_MISMATCH = "quote_revision_mismatch"
    QUOTE_VALIDITY_MISSING = "quote_validity_missing"
    QUOTE_EXPIRED = "quote_expired"
    EXECUTION_AMOUNT_MISMATCH = "execution_amount_mismatch"
    EXECUTION_QUANTITY_MISMATCH = "execution_quantity_mismatch"
    EXECUTION_UNIT_MISMATCH = "execution_unit_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    CURRENT_CAPITAL_SNAPSHOT_INVALID = "current_capital_snapshot_invalid"
    CURRENT_CAPITAL_INSUFFICIENT = "current_capital_insufficient"
    CURRENT_EXECUTION_CONFIRMATION_MISMATCH = (
        "current_execution_confirmation_mismatch"
    )

    @property
    def order(self) -> int:
        return tuple(RealMoneyExecutionIntentBlockingReasonCode).index(self)


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


@dataclass(frozen=True, slots=True)
class RealMoneyExecutionSourceManifest:
    opportunity_identity: OpportunityIdentity
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    current_deployable_capital_snapshot_id: str
    execution_quantity: int
    execution_quantity_unit: str
    planned_execution_amount: Decimal
    currency: str
    founder_id: str
    confirmed_at: datetime
    current_execution_confirmed: bool
    policy_name: str
    policy_version: str
    schema_version: str = REAL_MONEY_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "founder_capital_approval_id",
            "capital_gate_id",
            "capital_requirement_id",
            "intended_order_quantity_id",
            "sourcing_admission_id",
            "quote_id",
            "current_deployable_capital_snapshot_id",
            "execution_quantity_unit",
            "founder_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "sourcing_admission_revision",
            "quote_revision",
            "execution_quantity",
        ):
            object.__setattr__(
                self, name, _positive_integer(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "planned_execution_amount",
            _positive_money(self.planned_execution_amount, "planned_execution_amount"),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "confirmed_at", _aware(self.confirmed_at, "confirmed_at"))
        if not isinstance(self.current_execution_confirmed, bool):
            raise TypeError("current_execution_confirmed must be bool")
        if self.schema_version != REAL_MONEY_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Real-Money Execution source manifest schema")


@dataclass(frozen=True, slots=True)
class RealMoneyExecutionIntent:
    intent_id: str
    source_manifest: RealMoneyExecutionSourceManifest
    state: RealMoneyExecutionIntentState
    blocking_reasons: tuple[RealMoneyExecutionIntentBlockingReasonCode, ...]
    requested_at: datetime
    evaluated_at: datetime
    schema_version: str = REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        if not isinstance(self.source_manifest, RealMoneyExecutionSourceManifest):
            raise TypeError("source_manifest must be RealMoneyExecutionSourceManifest")
        state = RealMoneyExecutionIntentState(self.state)
        object.__setattr__(self, "state", state)
        if not isinstance(self.blocking_reasons, tuple):
            raise TypeError("blocking_reasons must be tuple")
        reasons = tuple(
            RealMoneyExecutionIntentBlockingReasonCode(value)
            for value in self.blocking_reasons
        )
        if len(set(reasons)) != len(reasons):
            raise ValueError("blocking reasons must be unique")
        if reasons != tuple(sorted(reasons, key=lambda value: value.order)):
            raise ValueError("blocking reasons must use deterministic policy order")
        if state is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION:
            if reasons:
                raise ValueError("READY intent cannot carry blocking reasons")
        elif not reasons:
            raise ValueError("BLOCKED intent requires at least one blocking reason")
        object.__setattr__(self, "blocking_reasons", reasons)
        for name in ("requested_at", "evaluated_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.schema_version != REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION:
            raise ValueError("unsupported Real-Money Execution Intent schema")

    @property
    def blocking_reason_codes(
        self,
    ) -> tuple[RealMoneyExecutionIntentBlockingReasonCode, ...]:
        return self.blocking_reasons


__all__ = [
    name
    for name in globals()
    if name.startswith(("RealMoney", "REAL_MONEY"))
]
