"""Immutable exact-source planned acquisition capital requirements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity


PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_SCHEMA_VERSION = (
    "planned-acquisition-capital-requirement-v1"
)
PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME = (
    "planned-acquisition-capital-requirement"
)
PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION = "1.0.0"
PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_DECIMAL_PRECISION = 34
PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_ROUNDING = ROUND_HALF_EVEN
UPFRONT_COST_SCOPE_VERIFICATION_SEMANTICS_VERSION = (
    "exact-normalization-additional-upfront-cost-scope-v1"
)


class UpfrontCostScopeStatus(StrEnum):
    COMPLETE = "complete"
    UNRESOLVED = "unresolved"


class PlannedAcquisitionCapitalRequirementState(StrEnum):
    CALCULABLE = "calculable"
    BLOCKED = "blocked"


class PlannedAcquisitionCapitalRequirementBlockingReason(StrEnum):
    UPFRONT_COST_SCOPE_UNVERIFIED = "upfront_cost_scope_unverified"


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


def _money(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def planned_acquisition_capital_decimal_context() -> Context:
    return Context(
        prec=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_DECIMAL_PRECISION,
        rounding=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_ROUNDING,
    )


def planned_acquisition_capital_amount(
    normalized_cost_per_unit: Decimal,
    quantity: int,
) -> Decimal:
    _money(normalized_cost_per_unit, "normalized_cost_per_unit")
    _positive_integer(quantity, "quantity")
    with localcontext(planned_acquisition_capital_decimal_context()):
        return normalized_cost_per_unit * Decimal(quantity)


@dataclass(frozen=True, slots=True)
class UpfrontCostScopeVerification:
    status: UpfrontCostScopeStatus
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    operator_id: str
    verified_at: datetime
    semantics_version: str = UPFRONT_COST_SCOPE_VERIFICATION_SEMANTICS_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", UpfrontCostScopeStatus(self.status))
        for name in (
            "intended_order_quantity_id",
            "acquisition_normalization_id",
            "operator_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        if self.semantics_version != UPFRONT_COST_SCOPE_VERIFICATION_SEMANTICS_VERSION:
            raise ValueError("unsupported upfront-cost scope verification semantics")


@dataclass(frozen=True, slots=True)
class PlannedAcquisitionCapitalRequirement:
    requirement_id: str
    opportunity_identity: OpportunityIdentity
    state: PlannedAcquisitionCapitalRequirementState
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    quantity: int
    quantity_unit: str
    normalized_acquisition_cost_per_unit: Decimal
    currency: str
    planned_acquisition_capital: Decimal | None
    scope_verification: UpfrontCostScopeVerification
    blocking_reasons: tuple[PlannedAcquisitionCapitalRequirementBlockingReason, ...]
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    calculated_at: datetime
    schema_version: str = PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _text(self.requirement_id, "requirement_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        state = PlannedAcquisitionCapitalRequirementState(self.state)
        object.__setattr__(self, "state", state)
        for name in (
            "intended_order_quantity_id",
            "acquisition_normalization_id",
            "sourcing_binding_id",
            "sourcing_admission_id",
            "quote_id",
            "quantity_unit",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "sourcing_admission_revision",
            "quote_revision",
            "quantity",
        ):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if self.sourcing_admission_revision != self.quote_revision:
            raise ValueError("Sourcing Admission and Quote revisions must match")
        object.__setattr__(
            self,
            "normalized_acquisition_cost_per_unit",
            _money(
                self.normalized_acquisition_cost_per_unit,
                "normalized_acquisition_cost_per_unit",
            ),
        )
        object.__setattr__(self, "currency", _currency(self.currency))
        if not isinstance(self.scope_verification, UpfrontCostScopeVerification):
            raise TypeError("scope_verification must be UpfrontCostScopeVerification")
        if (
            self.scope_verification.intended_order_quantity_id
            != self.intended_order_quantity_id
            or self.scope_verification.acquisition_normalization_id
            != self.acquisition_normalization_id
        ):
            raise ValueError("scope verification must bind exact requirement sources")
        if not isinstance(self.blocking_reasons, tuple):
            raise TypeError("blocking_reasons must be tuple")
        reasons = tuple(
            PlannedAcquisitionCapitalRequirementBlockingReason(value)
            for value in self.blocking_reasons
        )
        if len(set(reasons)) != len(reasons):
            raise ValueError("blocking reasons must not contain duplicates")
        object.__setattr__(self, "blocking_reasons", reasons)

        if state is PlannedAcquisitionCapitalRequirementState.CALCULABLE:
            if self.scope_verification.status is not UpfrontCostScopeStatus.COMPLETE:
                raise ValueError("CALCULABLE requires complete upfront-cost scope")
            if reasons:
                raise ValueError("CALCULABLE cannot carry blocking reasons")
            amount = _money(
                self.planned_acquisition_capital,  # type: ignore[arg-type]
                "planned_acquisition_capital",
            )
            expected = planned_acquisition_capital_amount(
                self.normalized_acquisition_cost_per_unit,
                self.quantity,
            )
            if amount != expected:
                raise ValueError("planned acquisition capital differs from exact arithmetic")
        else:
            if self.scope_verification.status is not UpfrontCostScopeStatus.UNRESOLVED:
                raise ValueError("BLOCKED requires unresolved upfront-cost scope")
            if self.planned_acquisition_capital is not None:
                raise ValueError("BLOCKED cannot carry authoritative capital amount")
            if reasons != (
                PlannedAcquisitionCapitalRequirementBlockingReason.UPFRONT_COST_SCOPE_UNVERIFIED,
            ):
                raise ValueError("BLOCKED reasons differ from policy order")

        if (
            self.policy_name != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME
            or self.policy_version != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION
        ):
            raise ValueError("unsupported planned acquisition capital policy")
        if self.policy_precision != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_DECIMAL_PRECISION:
            raise ValueError("unsupported planned acquisition capital precision")
        if self.policy_rounding != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_ROUNDING:
            raise ValueError("unsupported planned acquisition capital rounding")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "calculated_at", _aware(self.calculated_at, "calculated_at"))
        if self.schema_version != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_SCHEMA_VERSION:
            raise ValueError("unsupported planned acquisition capital requirement schema")


__all__ = [
    name
    for name in globals()
    if name.startswith(("Planned", "Upfront", "PLANNED", "UPFRONT"))
    or name.startswith("planned_acquisition")
]
