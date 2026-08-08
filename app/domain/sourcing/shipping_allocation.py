"""Domain contract for shipping allocation authority metadata."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.landed_cost import CostAllocationBasis, LandedCostComponentKind
from app.domain.sourcing.models import SourcingEvidenceReference


SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION = "shipping-allocation-authority-v2"
SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION = (
    "shipping-allocation-authority-command-v2"
)


class ShippingAllocationAuthorityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class ShippingAllocationAuthorityDenominatorSource(StrEnum):
    SOURCE_DERIVED = "source_derived"
    FOUNDER_ADMITTED = "founder_admitted"


class ShippingAllocationBasisAuthoritySource(StrEnum):
    SOURCE_DECLARED = "source_declared"
    OPERATOR_ADMITTED = "operator_admitted"


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


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
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
    authority_id: str
    composition_id: str
    opportunity_identity: OpportunityIdentity
    component_kind: LandedCostComponentKind
    original_allocation_basis: CostAllocationBasis
    allocation_basis: CostAllocationBasis
    basis_authority_source: ShippingAllocationBasisAuthoritySource
    status: ShippingAllocationAuthorityStatus
    evidence_reference: SourcingEvidenceReference
    requested_at: datetime
    admitted_at: datetime
    operator_id: str | None = None
    verified_at: datetime | None = None
    schema_version: str = SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION
    denominator: ShippingAllocationDenominator | None = None
    unresolved_code: ShippingAllocationAuthorityCode | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority_id", _text(self.authority_id, "authority_id"))
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.component_kind, LandedCostComponentKind):
            raise TypeError("component_kind must be LandedCostComponentKind")
        object.__setattr__(
            self,
            "original_allocation_basis",
            CostAllocationBasis(self.original_allocation_basis),
        )
        object.__setattr__(self, "allocation_basis", CostAllocationBasis(self.allocation_basis))
        object.__setattr__(
            self,
            "basis_authority_source",
            ShippingAllocationBasisAuthoritySource(self.basis_authority_source),
        )
        object.__setattr__(self, "status", ShippingAllocationAuthorityStatus(self.status))
        if not isinstance(self.evidence_reference, SourcingEvidenceReference):
            raise TypeError("evidence_reference must be SourcingEvidenceReference")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "admitted_at", _aware(self.admitted_at, "admitted_at"))
        if self.operator_id is not None:
            object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        if self.verified_at is not None:
            object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION:
            raise ValueError("unsupported shipping allocation authority schema")

        if self.denominator is not None and not isinstance(
            self.denominator, ShippingAllocationDenominator
        ):
            raise TypeError("denominator must be ShippingAllocationDenominator")

        if self.original_allocation_basis is not CostAllocationBasis.UNSPECIFIED:
            if self.allocation_basis is not self.original_allocation_basis:
                raise ValueError("explicit source allocation basis cannot be overridden")
            if self.basis_authority_source is not ShippingAllocationBasisAuthoritySource.SOURCE_DECLARED:
                raise ValueError("explicit source basis must remain source-declared")
        elif self.allocation_basis is not CostAllocationBasis.UNSPECIFIED:
            if self.basis_authority_source is not ShippingAllocationBasisAuthoritySource.OPERATOR_ADMITTED:
                raise ValueError("UNSPECIFIED source requires operator-admitted basis")
            if self.operator_id is None or self.verified_at is None:
                raise ValueError("operator-admitted basis requires operator and verified_at")

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
            if self.allocation_basis in {
                CostAllocationBasis.PER_WEIGHT,
                CostAllocationBasis.UNSPECIFIED,
            }:
                raise ValueError("unsupported allocation basis cannot be resolved")
            if (
                self.allocation_basis is CostAllocationBasis.PER_ORDER
                and self.denominator is not None
                and self.denominator.source
                is not ShippingAllocationAuthorityDenominatorSource.FOUNDER_ADMITTED
            ):
                raise ValueError("PER_ORDER denominator must be founder-admitted")
            if (
                self.allocation_basis is CostAllocationBasis.PER_QUOTED_QUANTITY
                and self.denominator is not None
                and self.denominator.source
                is not ShippingAllocationAuthorityDenominatorSource.SOURCE_DERIVED
            ):
                raise ValueError(
                    "PER_QUOTED_QUANTITY denominator must be source-derived"
                )
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
            expected_code = {
                CostAllocationBasis.PER_ORDER: {
                    ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_MISSING,
                    ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_INVALID,
                },
                CostAllocationBasis.PER_QUOTED_QUANTITY: {
                    ShippingAllocationAuthorityCode.PER_QUOTED_QUANTITY_DENOMINATOR_MISSING,
                },
                CostAllocationBasis.PER_WEIGHT: {
                    ShippingAllocationAuthorityCode.PER_WEIGHT_UNSUPPORTED,
                },
                CostAllocationBasis.UNSPECIFIED: {
                    ShippingAllocationAuthorityCode.UNSPECIFIED_UNRESOLVED,
                },
            }.get(self.allocation_basis, set())
            if self.unresolved_code not in expected_code:
                raise ValueError("unresolved code must match allocation basis")

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
    effective_allocation_basis: CostAllocationBasis | None = None
    per_order_denominator: int | None = None
    per_order_denominator_unit: str | None = None
    operator_id: str | None = None
    verified_at: datetime | None = None
    evidence_reference: SourcingEvidenceReference | None = None
    schema_version: str = SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.component_kind, LandedCostComponentKind):
            raise TypeError("component_kind must be LandedCostComponentKind")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.effective_allocation_basis is not None:
            object.__setattr__(
                self,
                "effective_allocation_basis",
                CostAllocationBasis(self.effective_allocation_basis),
            )
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
        if self.operator_id is not None:
            object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        if self.verified_at is not None:
            object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        if self.evidence_reference is not None and not isinstance(
            self.evidence_reference,
            SourcingEvidenceReference,
        ):
            raise TypeError("evidence_reference must be SourcingEvidenceReference")
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported shipping allocation authority command schema")

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            _canonical(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ShippingAllocationAuthorityValidationError(ValueError):
    pass


__all__ = [
    "SHIPPING_ALLOCATION_AUTHORITY_COMMAND_SCHEMA_VERSION",
    "SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION",
    "ShippingAllocationAuthority",
    "ShippingAllocationAuthorityCode",
    "ShippingAllocationAuthorityCommand",
    "ShippingAllocationBasisAuthoritySource",
    "ShippingAllocationDenominator",
    "ShippingAllocationAuthorityDenominatorSource",
    "ShippingAllocationAuthorityStatus",
    "ShippingAllocationAuthorityValidationError",
]
