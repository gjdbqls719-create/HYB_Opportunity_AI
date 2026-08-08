"""Immutable authoritative acquisition-cost normalization facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.landed_cost import CostAllocationBasis, LandedCostComponentKind
from app.domain.sourcing.models import CommercialFactAvailability
from app.domain.sourcing.shipping_allocation import (
    ShippingAllocationAuthorityDenominatorSource,
)


ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION = "acquisition-cost-normalization-v1"
ACQUISITION_COST_NORMALIZATION_POLICY_NAME = (
    "authoritative-acquisition-cost-normalization"
)
ACQUISITION_COST_NORMALIZATION_POLICY_VERSION = "1.0.0"
ACQUISITION_COST_NORMALIZATION_DECIMAL_PRECISION = 34
ACQUISITION_COST_NORMALIZATION_ROUNDING = ROUND_HALF_EVEN


class FXConversionDirection(StrEnum):
    NONE = "none"
    DIRECT = "direct"
    INVERSE = "inverse"


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


def normalization_decimal_context() -> Context:
    return Context(
        prec=ACQUISITION_COST_NORMALIZATION_DECIMAL_PRECISION,
        rounding=ACQUISITION_COST_NORMALIZATION_ROUNDING,
    )


def normalized_total(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext(normalization_decimal_context()):
        result = Decimal("0")
        for value in values:
            result += value
        return result


@dataclass(frozen=True, slots=True)
class NormalizedAcquisitionCostComponent:
    kind: LandedCostComponentKind
    original_availability: CommercialFactAvailability
    original_amount: Decimal | None
    original_currency: str | None
    original_allocation_basis: CostAllocationBasis
    effective_allocation_basis: CostAllocationBasis
    allocation_authority_id: str | None
    denominator_quantity: int | None
    denominator_source: ShippingAllocationAuthorityDenominatorSource | None
    fx_observation_id: str | None
    fx_direction: FXConversionDirection
    target_currency: str
    normalized_per_unit_amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", LandedCostComponentKind(self.kind))
        availability = CommercialFactAvailability(self.original_availability)
        object.__setattr__(self, "original_availability", availability)
        object.__setattr__(
            self,
            "original_allocation_basis",
            CostAllocationBasis(self.original_allocation_basis),
        )
        object.__setattr__(
            self,
            "effective_allocation_basis",
            CostAllocationBasis(self.effective_allocation_basis),
        )
        object.__setattr__(
            self,
            "target_currency",
            _currency(self.target_currency, "target_currency"),
        )
        object.__setattr__(
            self,
            "normalized_per_unit_amount",
            _money(self.normalized_per_unit_amount, "normalized_per_unit_amount"),
        )
        direction = FXConversionDirection(self.fx_direction)
        object.__setattr__(self, "fx_direction", direction)

        if availability is CommercialFactAvailability.UNKNOWN:
            raise ValueError("UNKNOWN component cannot be normalized")
        if availability is CommercialFactAvailability.NOT_APPLICABLE:
            if self.original_amount is not None or self.original_currency is not None:
                raise ValueError("NOT_APPLICABLE cannot carry source money")
            if self.normalized_per_unit_amount != Decimal("0"):
                raise ValueError("NOT_APPLICABLE must have zero normalized contribution")
            if any(
                value is not None
                for value in (
                    self.allocation_authority_id,
                    self.denominator_quantity,
                    self.denominator_source,
                    self.fx_observation_id,
                )
            ) or direction is not FXConversionDirection.NONE:
                raise ValueError("NOT_APPLICABLE cannot carry calculation sources")
            return

        if not isinstance(self.original_amount, Decimal):
            raise TypeError("known component original_amount must be Decimal")
        _money(self.original_amount, "original_amount")
        currency = _currency(self.original_currency, "original_currency")  # type: ignore[arg-type]
        object.__setattr__(self, "original_currency", currency)

        if self.kind is LandedCostComponentKind.UNIT_PURCHASE:
            if self.allocation_authority_id is not None:
                raise ValueError("unit purchase cannot carry allocation authority")
        else:
            object.__setattr__(
                self,
                "allocation_authority_id",
                _text(self.allocation_authority_id, "allocation_authority_id"),  # type: ignore[arg-type]
            )

        if self.effective_allocation_basis is CostAllocationBasis.PER_UNIT:
            if self.denominator_quantity is not None or self.denominator_source is not None:
                raise ValueError("PER_UNIT component cannot carry denominator")
        elif self.effective_allocation_basis in {
            CostAllocationBasis.PER_ORDER,
            CostAllocationBasis.PER_QUOTED_QUANTITY,
        }:
            if (
                isinstance(self.denominator_quantity, bool)
                or not isinstance(self.denominator_quantity, int)
                or self.denominator_quantity <= 0
            ):
                raise ValueError("allocated component requires positive denominator")
            object.__setattr__(
                self,
                "denominator_source",
                ShippingAllocationAuthorityDenominatorSource(self.denominator_source),
            )
        else:
            raise ValueError("unsupported component allocation basis")

        if direction is FXConversionDirection.NONE:
            if self.fx_observation_id is not None:
                raise ValueError("same-currency component cannot carry FX observation")
            if currency != self.target_currency:
                raise ValueError("cross-currency component requires FX direction")
        else:
            object.__setattr__(
                self,
                "fx_observation_id",
                _text(self.fx_observation_id, "fx_observation_id"),  # type: ignore[arg-type]
            )
            if currency == self.target_currency:
                raise ValueError("same-currency component cannot use FX conversion")


@dataclass(frozen=True, slots=True)
class AcquisitionCostNormalization:
    normalization_id: str
    opportunity_identity: OpportunityIdentity
    composition_id: str
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    target_currency: str
    components: tuple[NormalizedAcquisitionCostComponent, ...]
    total_per_unit_acquisition_cost: Decimal
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    normalized_at: datetime
    schema_version: str = ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "normalization_id",
            _text(self.normalization_id, "normalization_id"),
        )
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        for name in ("allocation_authority_ids", "fx_observation_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be tuple")
            normalized = tuple(_text(value, name) for value in values)
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, normalized)
        object.__setattr__(self, "target_currency", _currency(self.target_currency, "target_currency"))
        if not isinstance(self.components, tuple):
            raise TypeError("components must be tuple")
        if tuple(value.kind for value in self.components) != tuple(LandedCostComponentKind):
            raise ValueError("components must preserve canonical acquisition order")
        if any(value.target_currency != self.target_currency for value in self.components):
            raise ValueError("all components must use target currency")
        expected_allocations = tuple(
            value.allocation_authority_id
            for value in self.components
            if value.allocation_authority_id is not None
        )
        if expected_allocations != self.allocation_authority_ids:
            raise ValueError("allocation source manifest differs from components")
        expected_fx = tuple(
            dict.fromkeys(
                value.fx_observation_id
                for value in self.components
                if value.fx_observation_id is not None
            )
        )
        if expected_fx != self.fx_observation_ids:
            raise ValueError("FX source manifest differs from components")
        total = _money(
            self.total_per_unit_acquisition_cost,
            "total_per_unit_acquisition_cost",
        )
        if total != normalized_total(
            tuple(value.normalized_per_unit_amount for value in self.components)
        ):
            raise ValueError("total differs from normalized components")
        for name in ("policy_name", "policy_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if (
            self.policy_name != ACQUISITION_COST_NORMALIZATION_POLICY_NAME
            or self.policy_version != ACQUISITION_COST_NORMALIZATION_POLICY_VERSION
        ):
            raise ValueError("unsupported acquisition normalization policy")
        if self.policy_precision != ACQUISITION_COST_NORMALIZATION_DECIMAL_PRECISION:
            raise ValueError("unsupported normalization Decimal precision")
        if self.policy_rounding != ACQUISITION_COST_NORMALIZATION_ROUNDING:
            raise ValueError("unsupported normalization rounding")
        _aware(self.requested_at, "requested_at")
        _aware(self.normalized_at, "normalized_at")
        if self.schema_version != ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION:
            raise ValueError("unsupported acquisition normalization schema")


__all__ = [
    name
    for name in globals()
    if name.startswith("Acquisition")
    or name.startswith("Normalized")
    or name.startswith("FXConversion")
    or name.startswith("ACQUISITION")
    or name in {"normalization_decimal_context", "normalized_total"}
]
