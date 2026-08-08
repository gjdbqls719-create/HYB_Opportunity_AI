from dataclasses import replace
from datetime import timedelta

import pytest

from app.application.sourcing import (
    AdmitShippingAllocationAuthority,
    ShippingAllocationAuthorityReplayConflictError,
    ShippingAllocationBasisConflictError,
    ShippingAllocationProvenanceError,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    LandedCostComponentKind,
    ShippingAllocationAuthorityCommand,
    ShippingAllocationAuthorityDenominatorSource,
    ShippingAllocationAuthorityStatus,
)
from app.infrastructure.sourcing import (
    ProductionShippingAllocationAuthorityIdentityGenerator,
)
from test_landed_cost_composition import composition_command, prepare
from test_sourcing_authority_contract import NOW


class MemoryAllocationRepository:
    def __init__(self, composition):
        self.composition = composition
        self.saved = None

    def get_composition(self, composition_id):
        if self.composition.composition_id == composition_id:
            return self.composition
        return None

    def validate_replay(self, command_id, fingerprint):
        if self.saved is None or self.saved.receipt.command_id != command_id:
            return None
        if self.saved.receipt.command_fingerprint != fingerprint:
            raise ShippingAllocationAuthorityReplayConflictError("conflict")
        return replace(self.saved, replayed=True)

    def save_authority(self, command, authority, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        from app.application.sourcing import ShippingAllocationAuthorityResult

        self.saved = ShippingAllocationAuthorityResult(authority, receipt, False)
        return self.saved


class Calls:
    def __init__(self, value):
        self.value = value
        self.count = 0

    def __call__(self):
        self.count += 1
        return self.value


def production_composition():
    _, binding, _, use_case, *_ = prepare()
    return use_case.execute(composition_command(binding)).composition


def command(composition, **changes):
    values = {
        "command_id": "allocation-command-1",
        "composition_id": composition.composition_id,
        "opportunity_identity": composition.opportunity_identity,
        "component_kind": LandedCostComponentKind.INTERNATIONAL_FREIGHT,
        "requested_at": NOW,
        "effective_allocation_basis": CostAllocationBasis.PER_ORDER,
        "per_order_denominator": 100,
        "per_order_denominator_unit": "unit",
        "operator_id": "founder-1",
        "verified_at": NOW - timedelta(minutes=1),
        "evidence_reference": composition.evidence_reference,
    }
    values.update(changes)
    return ShippingAllocationAuthorityCommand(**values)


def boundary(repository, *, identity=None, admitted=None, committed=None):
    identity = identity or Calls("allocation-authority-1")
    admitted = admitted or Calls(NOW + timedelta(minutes=1))
    committed = committed or Calls(NOW + timedelta(minutes=2))
    return (
        AdmitShippingAllocationAuthority(
            repository,
            authority_id_generator=identity,
            admitted_clock=admitted,
            committed_clock=committed,
        ),
        identity,
        admitted,
        committed,
    )


def test_production_unspecified_shipping_accepts_explicit_per_order_authority():
    composition = production_composition()
    source = next(
        value
        for value in composition.components
        if value.kind is LandedCostComponentKind.INTERNATIONAL_FREIGHT
    )
    assert source.allocation_basis is CostAllocationBasis.UNSPECIFIED

    use_case, *_ = boundary(MemoryAllocationRepository(composition))
    result = use_case.execute(command(composition))

    authority = result.authority
    assert authority.authority_id == "allocation-authority-1"
    assert authority.original_allocation_basis is CostAllocationBasis.UNSPECIFIED
    assert authority.allocation_basis is CostAllocationBasis.PER_ORDER
    assert authority.status is ShippingAllocationAuthorityStatus.RESOLVED
    assert authority.denominator.quantity == 100
    assert authority.denominator.source is ShippingAllocationAuthorityDenominatorSource.FOUNDER_ADMITTED
    assert authority.operator_id == "founder-1"
    assert authority.evidence_reference == composition.evidence_reference
    assert authority.admitted_at == NOW + timedelta(minutes=1)
    assert result.receipt.committed_at == NOW + timedelta(minutes=2)


def test_unspecified_shipping_accepts_explicit_quoted_quantity_only_from_exact_source():
    composition = production_composition()
    use_case, *_ = boundary(MemoryAllocationRepository(composition))
    result = use_case.execute(
        command(
            composition,
            effective_allocation_basis=CostAllocationBasis.PER_QUOTED_QUANTITY,
            per_order_denominator=None,
            per_order_denominator_unit=None,
        )
    )

    assert result.authority.is_resolved
    assert result.authority.denominator.quantity == composition.quoted_quantity.quantity
    assert result.authority.denominator.source is ShippingAllocationAuthorityDenominatorSource.SOURCE_DERIVED

    unknown = replace(
        composition,
        quoted_quantity=replace(
            composition.quoted_quantity,
            availability=CommercialFactAvailability.UNKNOWN,
            quantity=None,
        ),
    )
    unresolved, *_ = boundary(MemoryAllocationRepository(unknown))
    result = unresolved.execute(
        command(
            unknown,
            command_id="allocation-command-2",
            effective_allocation_basis=CostAllocationBasis.PER_QUOTED_QUANTITY,
            per_order_denominator=None,
            per_order_denominator_unit=None,
        )
    )
    assert not result.authority.is_resolved


def test_existing_explicit_basis_cannot_be_overridden():
    composition = production_composition()
    explicit = replace(
        composition,
        components=tuple(
            replace(value, allocation_basis=CostAllocationBasis.PER_UNIT)
            if value.kind is LandedCostComponentKind.INTERNATIONAL_FREIGHT
            else value
            for value in composition.components
        ),
    )
    use_case, *_ = boundary(MemoryAllocationRepository(explicit))

    with pytest.raises(ShippingAllocationBasisConflictError):
        use_case.execute(command(explicit))


def test_exact_replay_precedes_identity_and_server_clocks():
    composition = production_composition()
    repository = MemoryAllocationRepository(composition)
    identity = Calls("allocation-authority-1")
    admitted = Calls(NOW + timedelta(minutes=1))
    committed = Calls(NOW + timedelta(minutes=2))
    use_case, *_ = boundary(
        repository,
        identity=identity,
        admitted=admitted,
        committed=committed,
    )
    first = use_case.execute(command(composition))
    replay = use_case.execute(command(composition))

    assert replay.replayed is True
    assert replay.authority == first.authority
    assert replay.receipt == first.receipt
    assert (identity.count, admitted.count, committed.count) == (1, 1, 1)


def test_changed_basis_denominator_or_provenance_conflicts_before_new_identity():
    composition = production_composition()
    repository = MemoryAllocationRepository(composition)
    use_case, identity, *_ = boundary(repository)
    use_case.execute(command(composition))

    for changed in (
        {"effective_allocation_basis": CostAllocationBasis.PER_UNIT, "per_order_denominator": None, "per_order_denominator_unit": None},
        {"per_order_denominator": 101},
        {"operator_id": "founder-2"},
    ):
        with pytest.raises(ShippingAllocationAuthorityReplayConflictError):
            use_case.execute(command(composition, **changed))
    assert identity.count == 1


def test_contract_does_not_divide_convert_or_make_capital_judgment():
    composition = production_composition()
    use_case, *_ = boundary(MemoryAllocationRepository(composition))
    authority = use_case.execute(command(composition)).authority

    assert not hasattr(authority, "per_unit_amount")
    assert not hasattr(authority, "fx_observation")
    assert not hasattr(authority, "capital_ready")


def test_explicit_basis_requires_operator_evidence_and_factual_time():
    composition = production_composition()
    use_case, *_ = boundary(MemoryAllocationRepository(composition))

    for missing in (
        {"operator_id": None},
        {"verified_at": None},
        {"evidence_reference": None},
    ):
        with pytest.raises(ShippingAllocationProvenanceError):
            use_case.execute(command(composition, **missing))


def test_production_unspecified_per_unit_and_per_weight_remain_explicit():
    composition = production_composition()
    per_unit, *_ = boundary(MemoryAllocationRepository(composition))
    unit = per_unit.execute(
        command(
            composition,
            effective_allocation_basis=CostAllocationBasis.PER_UNIT,
            per_order_denominator=None,
            per_order_denominator_unit=None,
        )
    ).authority
    assert unit.is_resolved
    assert unit.denominator is None

    per_weight, *_ = boundary(MemoryAllocationRepository(composition))
    weight = per_weight.execute(
        command(
            composition,
            command_id="allocation-command-weight",
            effective_allocation_basis=CostAllocationBasis.PER_WEIGHT,
            per_order_denominator=None,
            per_order_denominator_unit=None,
        )
    ).authority
    assert not weight.is_resolved
    assert weight.denominator is None


def test_unspecified_stays_unresolved_and_denominator_never_infers_basis():
    composition = production_composition()
    unresolved, *_ = boundary(MemoryAllocationRepository(composition))
    value = unresolved.execute(
        command(
            composition,
            effective_allocation_basis=None,
            per_order_denominator=None,
            per_order_denominator_unit=None,
            operator_id=None,
            verified_at=None,
            evidence_reference=None,
        )
    ).authority
    assert value.allocation_basis is CostAllocationBasis.UNSPECIFIED
    assert not value.is_resolved

    inferred, *_ = boundary(MemoryAllocationRepository(composition))
    with pytest.raises(ShippingAllocationProvenanceError):
        inferred.execute(
            command(
                composition,
                command_id="allocation-command-inference",
                effective_allocation_basis=None,
            )
        )


def test_production_identity_supplier_is_dedicated_uuid4_opaque_text():
    supplier = ProductionShippingAllocationAuthorityIdentityGenerator()
    values = {supplier() for _ in range(128)}

    assert len(values) == 128
    assert supplier.__slots__ == ()
    assert all(
        len(value) == 32
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
        for value in values
    )
