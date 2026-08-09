"""Capital-facing critical-cost source completeness facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.economics_binding import SourcingEconomicsBindingReference
from app.domain.sourcing.models import SourcingEconomicsSourceReference


CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION = "critical-cost-completeness-v1"
CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION_V2 = "critical-cost-completeness-v2"


class CriticalCostCompletenessState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class CriticalCostReasonSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class CriticalCostReasonCode(StrEnum):
    PURCHASE_COST_UNKNOWN = "purchase_cost_unknown"
    SHIPPING_SCOPE_UNKNOWN = "shipping_scope_unknown"
    SHIPPING_ALLOCATION_UNKNOWN = "shipping_allocation_unknown"
    SHIPPING_ALLOCATION_DENOMINATOR_MISSING = "shipping_allocation_denominator_missing"
    EXPECTED_SALE_PRICE_MISSING = "expected_sale_price_missing"
    MARKETPLACE_FEE_MISSING = "marketplace_fee_missing"
    PAYMENT_FEE_MISSING = "payment_fee_missing"
    FIXED_FEE_MISSING = "fixed_fee_missing"
    TAX_MISSING = "tax_missing"
    DUTY_MISSING = "duty_missing"
    OTHER_COST_MISSING = "other_cost_missing"
    EVIDENCE_NOT_VERIFIED = "evidence_not_verified"
    EVIDENCE_REFERENCE_MISSING = "evidence_reference_missing"
    CROSS_CURRENCY_FX_MISSING = "cross_currency_fx_missing"
    QUOTE_VALIDITY_UNKNOWN = "quote_validity_unknown"
    QUOTE_EXPIRED = "quote_expired"
    ADVERTISING_ALLOWANCE_DEFERRED = "advertising_allowance_deferred"
    RETURNS_ALLOWANCE_DEFERRED = "returns_allowance_deferred"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CriticalCostCompletenessPolicy:
    name: str
    version: str
    expected_sale_evidence_statuses: tuple[str, ...]
    required_evidence_statuses: tuple[str, ...]
    require_evidence_reference: bool
    require_quote_valid_until: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        for field_name in ("expected_sale_evidence_statuses", "required_evidence_statuses"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or not values:
                raise ValueError(f"{field_name} must be a non-empty tuple")
            normalized = tuple(_text(value, field_name) for value in values)
            supported = {"verified", "estimated", "default", "calculated", "missing", "unsupported"}
            if any(value not in supported for value in normalized):
                raise ValueError(f"{field_name} contains unsupported evidence status")
            object.__setattr__(self, field_name, normalized)
        for field_name in ("require_evidence_reference", "require_quote_valid_until"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be bool")


@dataclass(frozen=True, slots=True)
class CriticalCostCompletenessReason:
    code: CriticalCostReasonCode
    severity: CriticalCostReasonSeverity
    category: str
    source_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", CriticalCostReasonCode(self.code))
        object.__setattr__(self, "severity", CriticalCostReasonSeverity(self.severity))
        object.__setattr__(self, "category", _text(self.category, "category"))
        if self.source_reference is not None:
            object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))


@dataclass(frozen=True, slots=True)
class CriticalCostCompleteness:
    opportunity_identity: OpportunityIdentity
    composition_id: str
    binding_reference: SourcingEconomicsBindingReference
    source_reference: SourcingEconomicsSourceReference
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    policy_name: str
    policy_version: str
    evaluated_at: datetime
    state: CriticalCostCompletenessState
    blocking_reasons: tuple[CriticalCostCompletenessReason, ...]
    warning_reasons: tuple[CriticalCostCompletenessReason, ...]
    schema_version: str = CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION
    acquisition_normalization_id: str | None = None
    allocation_authority_ids: tuple[str, ...] = ()
    fx_observation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.binding_reference, SourcingEconomicsBindingReference):
            raise TypeError("binding_reference must be SourcingEconomicsBindingReference")
        if not isinstance(self.source_reference, SourcingEconomicsSourceReference):
            raise TypeError("source_reference must be SourcingEconomicsSourceReference")
        for name in (
            "verified_economics_opportunity_id", "verified_economics_schema_version",
            "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.verified_economics_snapshot_at, "verified_economics_snapshot_at")
        _aware(self.evaluated_at, "evaluated_at")
        state = CriticalCostCompletenessState(self.state)
        if not isinstance(self.blocking_reasons, tuple) or not isinstance(self.warning_reasons, tuple):
            raise TypeError("reasons must be tuples")
        if any(value.severity is not CriticalCostReasonSeverity.BLOCKING for value in self.blocking_reasons):
            raise ValueError("blocking reasons must have blocking severity")
        if any(value.severity is not CriticalCostReasonSeverity.WARNING for value in self.warning_reasons):
            raise ValueError("warning reasons must have warning severity")
        expected = CriticalCostCompletenessState.COMPLETE if not self.blocking_reasons else CriticalCostCompletenessState.INCOMPLETE
        if state is not expected:
            raise ValueError("state must match blocking reasons")
        if self.schema_version not in {
            CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION,
            CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION_V2,
        }:
            raise ValueError("unsupported Critical Cost Completeness version")
        for name in ("allocation_authority_ids", "fx_observation_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be tuple")
            normalized = tuple(_text(value, name) for value in values)
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, normalized)
        if self.schema_version == CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION:
            if (
                self.acquisition_normalization_id is not None
                or self.allocation_authority_ids
                or self.fx_observation_ids
            ):
                raise ValueError("v1 assessment cannot carry normalization provenance")
        else:
            object.__setattr__(
                self,
                "acquisition_normalization_id",
                _text(
                    self.acquisition_normalization_id,  # type: ignore[arg-type]
                    "acquisition_normalization_id",
                ),
            )
        object.__setattr__(self, "state", state)

    @property
    def is_complete(self) -> bool:
        return self.state is CriticalCostCompletenessState.COMPLETE


__all__ = [
    name for name in globals()
    if name.startswith("CriticalCost") or name.startswith("CRITICAL_COST")
]
