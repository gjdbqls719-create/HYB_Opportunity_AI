"""Domain contract for shipping allocation authority metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.landed_cost import CostAllocationBasis, LandedCostComponentKind
from app.domain.sourcing.models import SourcingEvidenceReference


SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION = "shipping-allocation-authority-v1"
SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION = (
    "shipping-allocation-authority-command-v1"
)


class ShippingAllocationAuthorityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class ShippingAllocationAuthorityDenominatorSource(StrEnum):
    SOURCE_DERIVED = "source_derived"
    FOUNDER_ADMITTED = "founder_admitted"


class ShippingAllocationAuthorityCode(StrEnum):
    PER_QUOTED_QUANTITY_DENOMINATOR_MISSING = "per_quoted_quantity_denominator_missing"
    PER_ORDER_DENOMINATOR_MISSING = "per_order_denominator_missing"
    PER_ORDER_DENOMINATOR_INVALID = "per_order_denominator_invalid"
    PER_WEIGHT_UNSUPPORTED = "per_weight_unsupported"
    UNSPECIFIED_UNRESOLVED = "unspecified_unresolved"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class ShippingAllocationDenominator:
    quantity: int
    source: ShippingAllocationAuthorityDenominatorSource
    source_reference: str
    quantity_unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _positive(self.quantity, "quantity"))
        object.__setattr__(self, "source", ShippingAllocationAuthorityDenominatorSource(self.source))
        object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))
        if (
            self.quantity_unit is not None
            and (not isinstance(self.quantity_unit, str) or not self.quantity_unit.strip())
        ):
            raise ValueError("quantity_unit must be non-empty text or None")
        if self.quantity_unit is not None:
            object.__setattr__(self, "quantity_unit", self.quantity_unit.strip())


@dataclass(frozen=True, slots=True)
class ShippingAllocationAuthority:
    composition_id: str
    opportunity_identity: OpportunityIdentity
    component_kind: LandedCostComponentKind
    allocation_basis: CostAllocationBasis
    status: ShippingAllocationAuthorityStatus
    evidence_reference: SourcingEvidenceReference
    requested_at: datetime
    schema_version: str = SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION
    denominator: ShippingAllocationDenominator | None = None
    unresolved_code: ShippingAllocationAuthorityCode | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.component_kind, LandedCostComponentKind):
            raise TypeError("component_kind must be LandedCostComponentKind")
        object.__setattr__(self, "allocation_basis", CostAllocationBasis(self.allocation_basis))
        object.__setattr__(self, "status", ShippingAllocationAuthorityStatus(self.status))
        if not isinstance(self.evidence_reference, SourcingEvidenceReference):
            raise TypeError("evidence_reference must be SourcingEvidenceReference")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION:
            raise ValueError("unsupported shipping allocation authority schema")

        if self.denominator is not None and not isinstance(
            self.denominator, ShippingAllocationDenominator
        ):
            raise TypeError("denominator must be ShippingAllocationDenominator")

        if self.status is ShippingAllocationAuthorityStatus.RESOLVED:
            if (
                self.denominator is not None
                and self.allocation_basis is CostAllocationBasis.PER_UNIT
            ):
                raise ValueError("PER_UNIT authority cannot carry a denominator")
            if (
                self.allocation_basis is not CostAllocationBasis.PER_UNIT
                and self.denominator is None
            ):
                raise ValueError(
                    "resolved authority requires denominator for non-per-unit basis"
                )
            if self.unresolved_code is not None:
                raise ValueError("resolved authority cannot carry unresolved_code")
        else:
            if self.denominator is not None:
                raise ValueError("unresolved authority cannot carry a denominator")
            if self.unresolved_code is None:
                raise ValueError("unresolved authority requires unresolved_code")
            object.__setattr__(
                self,
                "unresolved_code",
                ShippingAllocationAuthorityCode(self.unresolved_code),
            )

    @property
    def is_resolved(self) -> bool:
        return self.status is ShippingAllocationAuthorityStatus.RESOLVED


@dataclass(frozen=True, slots=True)
class ShippingAllocationAuthorityCommand:
    command_id: str
    composition_id: str
    opportunity_identity: OpportunityIdentity
    component_kind: LandedCostComponentKind
    requested_at: datetime
    per_order_denominator: int | None = None
    per_order_denominator_unit: str | None = None
    schema_version: str = SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.component_kind, LandedCostComponentKind):
            raise TypeError("component_kind must be LandedCostComponentKind")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.per_order_denominator is not None and not isinstance(
            self.per_order_denominator, int
        ):
            raise TypeError("per_order_denominator must be int if provided")
        if isinstance(self.per_order_denominator, bool):
            raise TypeError("per_order_denominator must be an int")
        if (
            self.per_order_denominator is None
            and self.per_order_denominator_unit is not None
        ):
            raise ValueError(
                "per_order_denominator_unit requires per_order_denominator"
            )
        if self.per_order_denominator_unit is not None and (
            not isinstance(self.per_order_denominator_unit, str)
            or not self.per_order_denominator_unit.strip()
        ):
            raise ValueError("per_order_denominator_unit must be non-empty text or None")
        if self.per_order_denominator_unit is not None:
            object.__setattr__(
                self,
                "per_order_denominator_unit",
                self.per_order_denominator_unit.strip(),
            )
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported shipping allocation authority command schema")


@dataclass(frozen=True, slots=True)
class ShippingAllocationAuthorityResult:
    authority: ShippingAllocationAuthority
    replayed: bool


class ShippingAllocationAuthorityValidationError(ValueError):
    pass


__all__ = [
    "SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION",
    "SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION",
    "ShippingAllocationAuthority",
    "ShippingAllocationAuthorityCode",
    "ShippingAllocationAuthorityCommand",
    "ShippingAllocationDenominator",
    "ShippingAllocationAuthorityDenominatorSource",
    "ShippingAllocationAuthorityResult",
    "ShippingAllocationAuthorityStatus",
    "ShippingAllocationAuthorityValidationError",
]
