"""Foundation application contracts for shipping allocation authority."""

from __future__ import annotations

from typing import Protocol

from app.domain.sourcing.landed_cost import (
    CostAllocationBasis,
    LandedCostComponent,
    LandedCostComponentKind,
    LandedCostComposition,
)
from app.domain.sourcing.models import CommercialFactAvailability
from app.domain.sourcing.shipping_allocation import (
    ShippingAllocationAuthority,
    ShippingAllocationAuthorityCode,
    ShippingAllocationAuthorityCommand,
    ShippingAllocationAuthorityDenominatorSource,
    ShippingAllocationAuthorityResult,
    ShippingAllocationAuthorityStatus,
    ShippingAllocationDenominator,
)


class ShippingAllocationAuthorityError(RuntimeError):
    pass


class ShippingAllocationSourceNotFoundError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationOpportunityMismatchError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationComponentNotFoundError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationAuthorityRepository(Protocol):
    def get_composition(
        self,
        composition_id: str,
    ) -> LandedCostComposition | None: ...


def _source_component(
    composition: LandedCostComposition,
    component_kind: LandedCostComponentKind,
) -> LandedCostComponent:
    for value in composition.components:
        if value.kind is component_kind:
            return value
    raise ShippingAllocationComponentNotFoundError("component is missing")


class AdmitShippingAllocationAuthority:
    def __init__(
        self,
        repository: ShippingAllocationAuthorityRepository,
    ) -> None:
        self._repository = repository

    def execute(
        self,
        command: ShippingAllocationAuthorityCommand,
    ) -> ShippingAllocationAuthorityResult:
        if not isinstance(command, ShippingAllocationAuthorityCommand):
            raise TypeError(
                "command must be ShippingAllocationAuthorityCommand"
            )

        composition = self._repository.get_composition(command.composition_id)
        if composition is None:
            raise ShippingAllocationSourceNotFoundError(
                "composition is missing"
            )

        if composition.opportunity_identity != command.opportunity_identity:
            raise ShippingAllocationOpportunityMismatchError(
                "composition opportunity differs from command"
            )

        component = _source_component(
            composition,
            command.component_kind,
        )

        authority = self._admit(
            command,
            composition,
            component,
        )

        return ShippingAllocationAuthorityResult(
            authority=authority,
            replayed=False,
        )

    @staticmethod
    def _admit(
        command: ShippingAllocationAuthorityCommand,
        composition: LandedCostComposition,
        component: LandedCostComponent,
    ) -> ShippingAllocationAuthority:
        basis = component.allocation_basis

        if basis is CostAllocationBasis.PER_UNIT:
            return ShippingAllocationAuthority(
                composition_id=composition.composition_id,
                opportunity_identity=composition.opportunity_identity,
                component_kind=component.kind,
                allocation_basis=basis,
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                evidence_reference=composition.evidence_reference,
                requested_at=command.requested_at,
            )

        if basis is CostAllocationBasis.PER_QUOTED_QUANTITY:
            if (
                composition.quoted_quantity.availability
                is not CommercialFactAvailability.KNOWN
                or composition.quoted_quantity.quantity is None
            ):
                return ShippingAllocationAuthority(
                    composition_id=composition.composition_id,
                    opportunity_identity=composition.opportunity_identity,
                    component_kind=component.kind,
                    allocation_basis=basis,
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    evidence_reference=composition.evidence_reference,
                    requested_at=command.requested_at,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode
                        .PER_QUOTED_QUANTITY_DENOMINATOR_MISSING
                    ),
                )

            return ShippingAllocationAuthority(
                composition_id=composition.composition_id,
                opportunity_identity=composition.opportunity_identity,
                component_kind=component.kind,
                allocation_basis=basis,
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                evidence_reference=composition.evidence_reference,
                requested_at=command.requested_at,
                denominator=ShippingAllocationDenominator(
                    quantity=composition.quoted_quantity.quantity,
                    source=(
                        ShippingAllocationAuthorityDenominatorSource
                        .SOURCE_DERIVED
                    ),
                    source_reference=(
                        f"composition:{composition.composition_id}:"
                        "quoted_quantity"
                    ),
                    quantity_unit="unit",
                ),
            )

        if basis is CostAllocationBasis.PER_ORDER:
            if command.per_order_denominator is None:
                return ShippingAllocationAuthority(
                    composition_id=composition.composition_id,
                    opportunity_identity=composition.opportunity_identity,
                    component_kind=component.kind,
                    allocation_basis=basis,
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    evidence_reference=composition.evidence_reference,
                    requested_at=command.requested_at,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode
                        .PER_ORDER_DENOMINATOR_MISSING
                    ),
                )

            if command.per_order_denominator <= 0:
                return ShippingAllocationAuthority(
                    composition_id=composition.composition_id,
                    opportunity_identity=composition.opportunity_identity,
                    component_kind=component.kind,
                    allocation_basis=basis,
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    evidence_reference=composition.evidence_reference,
                    requested_at=command.requested_at,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode
                        .PER_ORDER_DENOMINATOR_INVALID
                    ),
                )

            return ShippingAllocationAuthority(
                composition_id=composition.composition_id,
                opportunity_identity=composition.opportunity_identity,
                component_kind=component.kind,
                allocation_basis=basis,
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                evidence_reference=composition.evidence_reference,
                requested_at=command.requested_at,
                denominator=ShippingAllocationDenominator(
                    quantity=command.per_order_denominator,
                    source=(
                        ShippingAllocationAuthorityDenominatorSource
                        .FOUNDER_ADMITTED
                    ),
                    source_reference=(
                        f"composition:{composition.composition_id}:"
                        "per-order-denominator"
                    ),
                    quantity_unit=command.per_order_denominator_unit,
                ),
            )

        if basis is CostAllocationBasis.PER_WEIGHT:
            return ShippingAllocationAuthority(
                composition_id=composition.composition_id,
                opportunity_identity=composition.opportunity_identity,
                component_kind=component.kind,
                allocation_basis=basis,
                status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                evidence_reference=composition.evidence_reference,
                requested_at=command.requested_at,
                unresolved_code=(
                    ShippingAllocationAuthorityCode.PER_WEIGHT_UNSUPPORTED
                ),
            )

        return ShippingAllocationAuthority(
            composition_id=composition.composition_id,
            opportunity_identity=composition.opportunity_identity,
            component_kind=component.kind,
            allocation_basis=basis,
            status=ShippingAllocationAuthorityStatus.UNRESOLVED,
            evidence_reference=composition.evidence_reference,
            requested_at=command.requested_at,
            unresolved_code=(
                ShippingAllocationAuthorityCode.UNSPECIFIED_UNRESOLVED
            ),
        )


__all__ = [
    "AdmitShippingAllocationAuthority",
    "ShippingAllocationAuthorityRepository",
    "ShippingAllocationAuthorityError",
    "ShippingAllocationComponentNotFoundError",
    "ShippingAllocationSourceNotFoundError",
    "ShippingAllocationOpportunityMismatchError",
]