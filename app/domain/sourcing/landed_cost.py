"""Immutable acquisition-side landed-cost fact composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.economics_binding import SourcingEconomicsBindingReference
from app.domain.sourcing.models import (
    CommercialFactAvailability,
    SourcingEvidenceReference,
    SourcingQuantityFact,
)


LANDED_COST_COMPOSITION_SCHEMA_VERSION = "landed-cost-composition-v1"


class LandedCostComponentKind(StrEnum):
    UNIT_PURCHASE = "unit_purchase"
    SUPPLIER_SIDE_SHIPPING = "supplier_side_shipping"
    INTERNATIONAL_FREIGHT = "international_freight"
    DOMESTIC_INBOUND = "domestic_inbound"


class CostAllocationBasis(StrEnum):
    PER_UNIT = "per_unit"
    PER_ORDER = "per_order"
    PER_QUOTED_QUANTITY = "per_quoted_quantity"
    PER_WEIGHT = "per_weight"
    UNSPECIFIED = "unspecified"


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
class LandedCostComponent:
    kind: LandedCostComponentKind
    availability: CommercialFactAvailability
    amount: Decimal | None
    currency: str | None
    allocation_basis: CostAllocationBasis

    def __post_init__(self) -> None:
        try:
            kind = LandedCostComponentKind(self.kind)
            availability = CommercialFactAvailability(self.availability)
            basis = CostAllocationBasis(self.allocation_basis)
        except ValueError as error:
            raise ValueError("unsupported landed-cost component value") from error
        if availability is CommercialFactAvailability.KNOWN:
            if not isinstance(self.amount, Decimal):
                raise TypeError("known component amount must be Decimal")
            if not self.amount.is_finite() or self.amount < 0:
                raise ValueError("known component amount must be finite and non-negative")
            currency = _text(self.currency, "currency").upper()  # type: ignore[arg-type]
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError("currency must be a three-letter code")
            object.__setattr__(self, "currency", currency)
        elif self.amount is not None or self.currency is not None:
            raise ValueError("unknown/not-applicable component cannot carry money")
        if kind is LandedCostComponentKind.UNIT_PURCHASE and basis is not CostAllocationBasis.PER_UNIT:
            raise ValueError("unit purchase must use per-unit basis")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "allocation_basis", basis)


@dataclass(frozen=True, slots=True)
class LandedCostComposition:
    composition_id: str
    opportunity_identity: OpportunityIdentity
    binding_reference: SourcingEconomicsBindingReference
    components: tuple[LandedCostComponent, ...]
    minimum_order_quantity: SourcingQuantityFact
    quoted_quantity: SourcingQuantityFact
    evidence_reference: SourcingEvidenceReference
    requested_at: datetime
    composed_at: datetime
    schema_version: str = LANDED_COST_COMPOSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.binding_reference, SourcingEconomicsBindingReference):
            raise TypeError("binding_reference must be SourcingEconomicsBindingReference")
        if not isinstance(self.components, tuple):
            raise TypeError("components must be a tuple")
        expected = tuple(LandedCostComponentKind)
        if tuple(value.kind for value in self.components) != expected:
            raise ValueError("components must contain every kind in canonical order")
        if any(not isinstance(value, LandedCostComponent) for value in self.components):
            raise TypeError("components must contain LandedCostComponent values")
        if not isinstance(self.minimum_order_quantity, SourcingQuantityFact):
            raise TypeError("minimum_order_quantity must be SourcingQuantityFact")
        if not isinstance(self.quoted_quantity, SourcingQuantityFact):
            raise TypeError("quoted_quantity must be SourcingQuantityFact")
        if not isinstance(self.evidence_reference, SourcingEvidenceReference):
            raise TypeError("evidence_reference must be SourcingEvidenceReference")
        _aware(self.requested_at, "requested_at")
        _aware(self.composed_at, "composed_at")
        if self.schema_version != LANDED_COST_COMPOSITION_SCHEMA_VERSION:
            raise ValueError("unsupported Landed Cost Composition version")

    @property
    def known_currencies(self) -> tuple[str, ...]:
        values: list[str] = []
        for component in self.components:
            if component.currency is not None and component.currency not in values:
                values.append(component.currency)
        return tuple(values)


__all__ = [name for name in globals() if name.startswith("Landed") or name.startswith("Cost") or name.startswith("LANDED")]
