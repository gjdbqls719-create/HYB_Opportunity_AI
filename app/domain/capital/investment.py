"""Immutable Founder-declared Capital investment facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import OpportunityIdentity


INTENDED_ORDER_QUANTITY_SCHEMA_VERSION = "intended-order-quantity-v1"
DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION = "deployable-capital-snapshot-v1"
DEPLOYABLE_CAPITAL_SEMANTICS_VERSION = "founder-declared-reserve-adjusted-v1"


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


@dataclass(frozen=True, slots=True)
class IntendedOrderQuantity:
    intent_id: str
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
    admitted_at: datetime
    schema_version: str = INTENDED_ORDER_QUANTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in ("sourcing_admission_id", "quote_id", "quantity_unit", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision", "quantity"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if self.sourcing_admission_revision != self.quote_revision:
            raise ValueError("Sourcing Admission and Quote revisions must match")
        for name in ("requested_at", "declared_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.schema_version != INTENDED_ORDER_QUANTITY_SCHEMA_VERSION:
            raise ValueError("unsupported Intended Order Quantity schema")


@dataclass(frozen=True, slots=True)
class DeployableCapitalSnapshot:
    snapshot_id: str
    amount: Decimal
    currency: str
    as_of: datetime
    operator_id: str
    requested_at: datetime
    admitted_at: datetime
    semantics_version: str = DEPLOYABLE_CAPITAL_SEMANTICS_VERSION
    schema_version: str = DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text(self.snapshot_id, "snapshot_id"))
        object.__setattr__(self, "amount", _amount(self.amount))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        for name in ("as_of", "requested_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.semantics_version != DEPLOYABLE_CAPITAL_SEMANTICS_VERSION:
            raise ValueError("unsupported Deployable Capital semantics")
        if self.schema_version != DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported Deployable Capital schema")


__all__ = [
    "DEPLOYABLE_CAPITAL_SEMANTICS_VERSION",
    "DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION",
    "DeployableCapitalSnapshot",
    "INTENDED_ORDER_QUANTITY_SCHEMA_VERSION",
    "IntendedOrderQuantity",
]
