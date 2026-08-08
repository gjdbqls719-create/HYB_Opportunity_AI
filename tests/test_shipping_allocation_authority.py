from dataclasses import FrozenInstanceError, replace

import pytest

from app.application.sourcing import (
    AdmitShippingAllocationAuthority,
    ShippingAllocationOpportunityMismatchError,
    ShippingAllocationSourceNotFoundError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    LandedCostComponentKind,
    LandedCostComposition,
    ShippingAllocationAuthorityCode,
    ShippingAllocationAuthorityCommand,
)
from test_landed_cost_composition import prepare, composition_command
from test_sourcing_authority_contract import NOW


class MemoryCompositions:
    def __init__(self, composition: LandedCostComposition | None):
        self.composition = composition

    def get_composition(self, composition_id: str) -> LandedCostComposition | None:
        return self.composition if self.composition and self.composition.composition_id == composition_id else None


def build_composition():
    _, binding, _, use_case, *_ = prepare()
    return use_case.execute(composition_command(binding)).composition


def with_basis(composition: LandedCostComposition, component_kind: LandedCostComponentKind, basis: CostAllocationBasis):
    return replace(
        composition,
        components=tuple(
            replace(component, allocation_basis=basis)
            if component.kind is component_kind else component
            for component in composition.components
        ),
    )


def command(
    composition: LandedCostComposition,
    component_kind: LandedCostComponentKind,
    **changes,
):
    values = dict(
        command_id="shipping-allocation-command-1",
        composition_id=composition.composition_id,
        opportunity_identity=composition.opportunity_identity,
        component_kind=component_kind,
        requested_at=NOW,
    )
    values.update(changes)
    return ShippingAllocationAuthorityCommand(**values)


def test_per_unit_basis_is_resolved_without_denominator():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        CostAllocationBasis.PER_UNIT,
    )
    result = AdmitShippingAllocationAuthority(MemoryCompositions(composition)).execute(
        command(composition, LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING)
    )

    assert result.replayed is False
    assert result.authority.is_resolved is True
    assert result.authority.denominator is None
    assert result.authority.allocation_basis is CostAllocationBasis.PER_UNIT


def test_per_order_requires_explicit_founder_denominator_and_keeps_authority_source():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        CostAllocationBasis.PER_ORDER,
    )
    boundary = AdmitShippingAllocationAuthority(MemoryCompositions(composition))
    missing = boundary.execute(
        command(
            composition,
            LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            per_order_denominator=None,
        )
    )
    assert missing.authority.is_resolved is False
    assert missing.authority.unresolved_code is ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_MISSING

    invalid = boundary.execute(
        command(
            composition,
            LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            per_order_denominator=0,
        )
    )
    assert invalid.authority.unresolved_code is ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_INVALID

    with pytest.raises(TypeError):
        command(
            composition,
            LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            per_order_denominator=True,  # type: ignore[arg-type]
        )

    resolved = boundary.execute(
        command(
            composition,
            LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            per_order_denominator=777,
            per_order_denominator_unit="unit",
        )
    )
    assert resolved.authority.denominator is not None
    assert resolved.authority.denominator.quantity == 777
    assert resolved.authority.denominator.quantity_unit == "unit"
    assert resolved.authority.denominator.source.value == "founder_admitted"


def test_per_order_does_not_use_moq_for_denominator():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.DOMESTIC_INBOUND,
        CostAllocationBasis.PER_ORDER,
    )
    authority = AdmitShippingAllocationAuthority(MemoryCompositions(composition)).execute(
        command(
            composition,
            LandedCostComponentKind.DOMESTIC_INBOUND,
            per_order_denominator=120,
            per_order_denominator_unit="unit",
        )
    ).authority

    assert authority.denominator.quantity != composition.minimum_order_quantity.quantity


def test_per_quoted_quantity_uses_source_quoted_quantity_when_known():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.INTERNATIONAL_FREIGHT,
        CostAllocationBasis.PER_QUOTED_QUANTITY,
    )
    boundary = AdmitShippingAllocationAuthority(MemoryCompositions(composition))
    resolved = boundary.execute(
        command(composition, LandedCostComponentKind.INTERNATIONAL_FREIGHT)
    )
    assert resolved.authority.denominator is not None
    assert resolved.authority.denominator.quantity == composition.quoted_quantity.quantity
    assert resolved.authority.denominator.source.value == "source_derived"

    unknown_quoted = replace(
        composition,
        quoted_quantity=replace(
            composition.quoted_quantity,
            availability=CommercialFactAvailability.UNKNOWN,
            quantity=None,
        ),
    )
    unresolved = AdmitShippingAllocationAuthority(MemoryCompositions(unknown_quoted)).execute(
        command(unknown_quoted, LandedCostComponentKind.INTERNATIONAL_FREIGHT)
    )
    assert unresolved.authority.unresolved_code is ShippingAllocationAuthorityCode.PER_QUOTED_QUANTITY_DENOMINATOR_MISSING


def test_per_weight_is_unresolved_and_unspecified_is_unresolved():
    composition = build_composition()
    weight_basis = with_basis(
        composition, LandedCostComponentKind.DOMESTIC_INBOUND, CostAllocationBasis.PER_WEIGHT
    )
    weight = AdmitShippingAllocationAuthority(
        MemoryCompositions(weight_basis)
    ).execute(
        command(weight_basis, LandedCostComponentKind.DOMESTIC_INBOUND)
    )
    assert not weight.authority.is_resolved
    assert weight.authority.unresolved_code is ShippingAllocationAuthorityCode.PER_WEIGHT_UNSUPPORTED

    unspecified = with_basis(
        weight_basis,
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        CostAllocationBasis.UNSPECIFIED,
    )
    unresolved = AdmitShippingAllocationAuthority(MemoryCompositions(unspecified)).execute(
        command(unspecified, LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING)
    )
    assert unresolved.authority.unresolved_code is ShippingAllocationAuthorityCode.UNSPECIFIED_UNRESOLVED


def test_invalid_basis_component_is_not_supported_without_inference():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        CostAllocationBasis.UNSPECIFIED,
    )
    authority = AdmitShippingAllocationAuthority(MemoryCompositions(composition)).execute(
        command(composition, LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING)
    ).authority
    assert authority.denominator is None
    assert authority.unresolved_code is ShippingAllocationAuthorityCode.UNSPECIFIED_UNRESOLVED


def test_opportunity_mismatch_and_missing_composition_rejected_before_any_calculation():
    composition = build_composition()
    boundary = AdmitShippingAllocationAuthority(MemoryCompositions(composition))
    mismatch = command(
        composition,
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        opportunity_identity=OpportunityIdentity("opp-other", "discovery-1"),
    )
    with pytest.raises(ShippingAllocationOpportunityMismatchError):
        boundary.execute(mismatch)

    missing = AdmitShippingAllocationAuthority(MemoryCompositions(None))
    with pytest.raises(ShippingAllocationSourceNotFoundError):
        missing.execute(command(composition, LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING))


def test_application_contracts_do_not_convert_or_normalize_values():
    composition = with_basis(
        build_composition(),
        LandedCostComponentKind.INTERNATIONAL_FREIGHT,
        CostAllocationBasis.PER_WEIGHT,
    )
    value = AdmitShippingAllocationAuthority(MemoryCompositions(composition)).execute(
        command(composition, LandedCostComponentKind.INTERNATIONAL_FREIGHT)
    ).authority
    assert value.denominator is None
    component = next(
        value for value in composition.components
        if value.kind is LandedCostComponentKind.INTERNATIONAL_FREIGHT
    )
    assert component.availability.name.lower() in {"known", "unknown", "not_applicable"}


def test_contracts_are_immutable():
    composition = build_composition()
    issued = AdmitShippingAllocationAuthority(MemoryCompositions(composition)).execute(
        command(composition, LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING)
    )
    with pytest.raises(FrozenInstanceError):
        composition.quoted_quantity = replace(composition.quoted_quantity, quantity=999)
    with pytest.raises(FrozenInstanceError):
        issued.authority.denominator = None
