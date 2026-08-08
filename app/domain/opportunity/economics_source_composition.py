"""Immutable exact-source manifest for future Economics calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.opportunity.economics import MoneyInput, RateInput

if TYPE_CHECKING:
    from app.domain.decision_engine import OpportunityIdentity


ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION = "economics-source-composition-v1"
ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME = (
    "authoritative-economics-source-composition"
)
ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION = "1.0.0"


class EconomicsSourceCompositionState(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class EconomicsSourceBlockingCode(StrEnum):
    EXPECTED_SALE_PRICE_MISSING = "expected_sale_price_missing"
    MARKETPLACE_FEE_MISSING = "marketplace_fee_missing"
    PAYMENT_FEE_MISSING = "payment_fee_missing"
    FIXED_FEE_MISSING = "fixed_fee_missing"
    TAX_MISSING = "tax_missing"
    DUTY_MISSING = "duty_missing"
    OTHER_COST_MISSING = "other_cost_missing"
    EVIDENCE_NOT_VERIFIED = "evidence_not_verified"
    EVIDENCE_REFERENCE_MISSING = "evidence_reference_missing"
    OTHER_COST_SCOPE_UNRESOLVED = "other_cost_scope_unresolved"
    CURRENCY_MISMATCH = "currency_mismatch"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _currency(value: str, name: str) -> str:
    result = _text(value, name).upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError(f"{name} must be a three-letter currency code")
    return result


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _money(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


@dataclass(frozen=True, slots=True)
class EconomicsSourceBlockingReason:
    code: EconomicsSourceBlockingCode
    category: str
    source_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", EconomicsSourceBlockingCode(self.code))
        object.__setattr__(self, "category", _text(self.category, "category"))
        if self.source_reference is not None:
            object.__setattr__(
                self,
                "source_reference",
                _text(self.source_reference, "source_reference"),
            )


@dataclass(frozen=True, slots=True)
class EconomicsSourceComposition:
    composition_id: str
    opportunity_identity: OpportunityIdentity
    acquisition_normalization_id: str
    acquisition_policy_name: str
    acquisition_policy_version: str
    acquisition_cost_per_unit: Decimal
    economics_currency: str
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    expected_sale_price: MoneyInput
    marketplace_fee_rate: RateInput
    payment_fee_rate: RateInput
    fixed_fee: MoneyInput
    tax_rate: RateInput
    duty_cost: MoneyInput
    other_cost: MoneyInput
    state: EconomicsSourceCompositionState
    blocking_reasons: tuple[EconomicsSourceBlockingReason, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    composed_at: datetime
    schema_version: str = ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "composition_id",
            "acquisition_normalization_id",
            "acquisition_policy_name",
            "acquisition_policy_version",
            "verified_economics_opportunity_id",
            "verified_economics_schema_version",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        # Import locally because decision_engine itself imports the opportunity
        # package while defining OpportunityIdentity.
        from app.domain.decision_engine import OpportunityIdentity

        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if (
            self.verified_economics_opportunity_id
            != self.opportunity_identity.opportunity_id
        ):
            raise ValueError("Verified Economics Opportunity differs")
        object.__setattr__(
            self,
            "acquisition_cost_per_unit",
            _money(self.acquisition_cost_per_unit, "acquisition_cost_per_unit"),
        )
        object.__setattr__(
            self,
            "economics_currency",
            _currency(self.economics_currency, "economics_currency"),
        )
        _aware(self.verified_economics_snapshot_at, "verified_economics_snapshot_at")
        _aware(self.requested_at, "requested_at")
        _aware(self.composed_at, "composed_at")
        for name, expected in (
            ("expected_sale_price", MoneyInput),
            ("marketplace_fee_rate", RateInput),
            ("payment_fee_rate", RateInput),
            ("fixed_fee", MoneyInput),
            ("tax_rate", RateInput),
            ("duty_cost", MoneyInput),
            ("other_cost", MoneyInput),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} must be {expected.__name__}")
        state = EconomicsSourceCompositionState(self.state)
        object.__setattr__(self, "state", state)
        if not isinstance(self.blocking_reasons, tuple) or any(
            not isinstance(value, EconomicsSourceBlockingReason)
            for value in self.blocking_reasons
        ):
            raise TypeError("blocking_reasons must be reason tuple")
        if state is EconomicsSourceCompositionState.READY and self.blocking_reasons:
            raise ValueError("READY composition cannot have blockers")
        if state is EconomicsSourceCompositionState.BLOCKED and not self.blocking_reasons:
            raise ValueError("BLOCKED composition requires blockers")
        if (
            self.policy_name != ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME
            or self.policy_version != ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION
        ):
            raise ValueError("unsupported Economics Source Composition policy")
        if self.schema_version != ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION:
            raise ValueError("unsupported Economics Source Composition schema")

    @property
    def is_ready(self) -> bool:
        return self.state is EconomicsSourceCompositionState.READY


__all__ = [
    name
    for name in globals()
    if name.startswith("EconomicsSource") or name.startswith("ECONOMICS_SOURCE")
]
