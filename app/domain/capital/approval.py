"""Immutable Founder authorization for one exact Capital Gate PASS result."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import OpportunityIdentity


FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION = "founder-capital-approval-v1"


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


@dataclass(frozen=True, slots=True)
class FounderCapitalApproval:
    approval_id: str
    opportunity_identity: OpportunityIdentity
    capital_gate_id: str
    capital_gate_policy_name: str
    capital_gate_policy_version: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    intended_order_quantity_id: str
    capital_gate_evaluated_at: datetime
    approved_capital: Decimal
    currency: str
    founder_id: str
    requested_at: datetime
    approved_at: datetime
    admitted_at: datetime
    schema_version: str = FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "approval_id",
            "capital_gate_id",
            "capital_gate_policy_name",
            "capital_gate_policy_version",
            "capital_requirement_id",
            "deployable_capital_snapshot_id",
            "intended_order_quantity_id",
            "founder_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(
            self, "approved_capital", _positive_money(self.approved_capital, "approved_capital")
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        for name in (
            "capital_gate_evaluated_at",
            "requested_at",
            "approved_at",
            "admitted_at",
        ):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.schema_version != FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION:
            raise ValueError("unsupported Founder Capital Approval schema")


__all__ = ["FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION", "FounderCapitalApproval"]
