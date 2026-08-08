from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.sourcing import (
    AcquisitionCostNormalizationSourceError,
    NormalizeAcquisitionCosts,
    NormalizeAcquisitionCostsCommand,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    FXConversionDirection,
    FXObservation,
    FXObservationProvenance,
    LandedCostComponentKind,
)
from test_shipping_allocation_authority_reconciliation import (
    MemoryAllocationRepository,
    boundary as allocation_boundary,
    command as allocation_command,
    production_composition,
)
from test_sourcing_authority_contract import NOW
from app.infrastructure.sourcing import (
    ProductionAcquisitionCostNormalizationIdentityGenerator,
)


class MemoryNormalizationRepository:
    def __init__(self, composition, authorities=(), observations=()):
        self.composition = composition
        self.authorities = {value.authority_id: value for value in authorities}
        self.observations = {value.observation_id: value for value in observations}
        self.saved = None

    def get_composition(self, composition_id):
        return self.composition if self.composition.composition_id == composition_id else None

    def get_allocation_authority(self, authority_id):
        return self.authorities.get(authority_id)

    def get_fx_observation(self, observation_id):
        return self.observations.get(observation_id)

    def validate_replay(self, command_id, fingerprint):
        return None

    def save_normalization(self, command, normalization, receipt):
        from app.application.sourcing import AcquisitionCostNormalizationResult

        self.saved = AcquisitionCostNormalizationResult(normalization, receipt, False)
        return self.saved


class Calls:
    def __init__(self, value):
        self.value = value
        self.count = 0

    def __call__(self):
        self.count += 1
        return self.value


def complete_composition():
    composition = production_composition()
    replacements = {
        LandedCostComponentKind.INTERNATIONAL_FREIGHT: (Decimal("10"), "USD"),
        LandedCostComponentKind.DOMESTIC_INBOUND: (Decimal("5000"), "KRW"),
    }
    return replace(
        composition,
        components=tuple(
            replace(
                component,
                availability=CommercialFactAvailability.KNOWN,
                amount=replacements[component.kind][0],
                currency=replacements[component.kind][1],
            )
            if component.kind in replacements
            else component
            for component in composition.components
        ),
    )


def allocations(composition):
    values = []
    specifications = (
        (LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING, CostAllocationBasis.PER_ORDER, 100),
        (LandedCostComponentKind.INTERNATIONAL_FREIGHT, CostAllocationBasis.PER_ORDER, 100),
        (LandedCostComponentKind.DOMESTIC_INBOUND, CostAllocationBasis.PER_UNIT, None),
    )
    for index, (kind, basis, denominator) in enumerate(specifications, start=1):
        repository = MemoryAllocationRepository(composition)
        owner, *_ = allocation_boundary(repository, identity=Calls(f"allocation-{index}"))
        values.append(
            owner.execute(
                allocation_command(
                    composition,
                    command_id=f"allocation-command-{index}",
                    component_kind=kind,
                    effective_allocation_basis=basis,
                    per_order_denominator=denominator,
                    per_order_denominator_unit=("unit" if denominator else None),
                )
            ).authority
        )
    return tuple(values)


def fx(observation_id, base, quote, rate):
    return FXObservation(
        observation_id=observation_id,
        base_currency=base,
        quote_currency=quote,
        rate=Decimal(rate),
        observed_at=NOW,
        admitted_at=NOW + timedelta(minutes=1),
        provenance=FXObservationProvenance("provider", f"source:{observation_id}"),
    )


def command(composition, authorities, observations, **changes):
    values = {
        "command_id": "normalization-command-1",
        "opportunity_identity": composition.opportunity_identity,
        "composition_id": composition.composition_id,
        "allocation_authority_ids": tuple(value.authority_id for value in authorities),
        "fx_observation_ids": tuple(value.observation_id for value in observations),
        "target_currency": "KRW",
        "requested_at": NOW,
        "policy_name": "authoritative-acquisition-cost-normalization",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    return NormalizeAcquisitionCostsCommand(**values)


def normalize(composition, authorities, observations):
    repository = MemoryNormalizationRepository(composition, authorities, observations)
    identity = Calls("normalization-1")
    normalized = Calls(NOW + timedelta(minutes=2))
    committed = Calls(NOW + timedelta(minutes=3))
    owner = NormalizeAcquisitionCosts(
        repository,
        normalization_id_generator=identity,
        normalized_clock=normalized,
        committed_clock=committed,
    )
    return owner.execute(command(composition, authorities, observations)), repository


def test_exact_allocation_and_direct_fx_normalize_fixed_component_set():
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (
        fx("fx-cny-krw", "CNY", "KRW", "190"),
        fx("fx-usd-krw", "USD", "KRW", "1400"),
    )
    result, _ = normalize(composition, authorities, observations)
    normalized = result.normalization

    assert tuple(value.kind for value in normalized.components) == tuple(LandedCostComponentKind)
    assert tuple(value.normalized_per_unit_amount for value in normalized.components) == (
        Decimal("2344.6000"),
        Decimal("38.950"),
        Decimal("140"),
        Decimal("5000"),
    )
    assert normalized.total_per_unit_acquisition_cost == Decimal("7523.5500")
    assert normalized.target_currency == "KRW"
    assert normalized.policy_precision == 34
    assert normalized.policy_rounding == "ROUND_HALF_EVEN"


def test_component_provenance_preserves_allocation_fx_and_original_facts():
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (fx("fx-cny-krw", "CNY", "KRW", "190"), fx("fx-usd-krw", "USD", "KRW", "1400"))
    normalized = normalize(composition, authorities, observations)[0].normalization

    purchase, supplier, international, domestic = normalized.components
    assert purchase.allocation_authority_id is None
    assert purchase.fx_observation_id == "fx-cny-krw"
    assert purchase.fx_direction is FXConversionDirection.DIRECT
    assert supplier.allocation_authority_id == "allocation-1"
    assert supplier.denominator_quantity == 100
    assert supplier.fx_observation_id == "fx-cny-krw"
    assert international.fx_observation_id == "fx-usd-krw"
    assert domestic.fx_observation_id is None
    assert domestic.fx_direction is FXConversionDirection.NONE


def test_inverse_fx_uses_same_exact_observation_without_fabrication():
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (
        fx("fx-krw-cny", "KRW", "CNY", "0.005"),
        fx("fx-krw-usd", "KRW", "USD", "0.0007142857142857142857142857142857"),
    )
    normalized = normalize(composition, authorities, observations)[0].normalization

    assert normalized.components[0].fx_direction is FXConversionDirection.INVERSE
    assert normalized.components[0].fx_observation_id == "fx-krw-cny"
    assert normalized.components[0].normalized_per_unit_amount == Decimal("2468.00")


@pytest.mark.parametrize(
    "change",
    [
        lambda authorities, observations: (authorities[1:], observations),
        lambda authorities, observations: ((authorities[2], authorities[1], authorities[0]), observations),
        lambda authorities, observations: (authorities, observations[1:]),
        lambda authorities, observations: (authorities, (fx("wrong", "EUR", "GBP", "1.2"), observations[1])),
    ],
)
def test_missing_or_wrong_exact_allocation_and_fx_sources_are_rejected(change):
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (fx("fx-cny-krw", "CNY", "KRW", "190"), fx("fx-usd-krw", "USD", "KRW", "1400"))
    changed_authorities, changed_observations = change(authorities, observations)
    repository = MemoryNormalizationRepository(composition, changed_authorities, changed_observations)
    owner = NormalizeAcquisitionCosts(
        repository,
        normalization_id_generator=lambda: "normalization-1",
        normalized_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    )
    with pytest.raises(AcquisitionCostNormalizationSourceError):
        owner.execute(command(composition, changed_authorities, changed_observations))


def test_unknown_blocks_while_not_applicable_and_known_zero_remain_distinct():
    composition = complete_composition()
    unknown = replace(
        composition,
        components=tuple(
            replace(value, availability=CommercialFactAvailability.UNKNOWN, amount=None, currency=None)
            if value.kind is LandedCostComponentKind.INTERNATIONAL_FREIGHT else value
            for value in composition.components
        ),
    )
    with pytest.raises(AcquisitionCostNormalizationSourceError):
        normalize(unknown, allocations(unknown), (fx("fx-cny-krw", "CNY", "KRW", "190"),))[0]

    preserved = replace(
        composition,
        components=tuple(
            replace(value, availability=CommercialFactAvailability.NOT_APPLICABLE, amount=None, currency=None)
            if value.kind is LandedCostComponentKind.INTERNATIONAL_FREIGHT
            else replace(value, amount=Decimal("0"))
            if value.kind is LandedCostComponentKind.DOMESTIC_INBOUND
            else value
            for value in composition.components
        ),
    )
    applicable_authorities = tuple(
        value for value in allocations(preserved)
        if value.component_kind is not LandedCostComponentKind.INTERNATIONAL_FREIGHT
    )
    normalized = normalize(
        preserved,
        applicable_authorities,
        (fx("fx-cny-krw", "CNY", "KRW", "190"),),
    )[0].normalization
    assert normalized.components[2].original_availability is CommercialFactAvailability.NOT_APPLICABLE
    assert normalized.components[2].normalized_per_unit_amount == Decimal("0")
    assert normalized.components[3].original_availability is CommercialFactAvailability.KNOWN
    assert normalized.components[3].normalized_per_unit_amount == Decimal("0")


def test_result_has_no_sale_side_or_capital_judgment():
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (fx("fx-cny-krw", "CNY", "KRW", "190"), fx("fx-usd-krw", "USD", "KRW", "1400"))
    normalized = normalize(composition, authorities, observations)[0].normalization

    for forbidden in ("roi", "profit", "marketplace_fee", "payment_fee", "capital_ready"):
        assert not hasattr(normalized, forbidden)


def test_production_identity_supplier_issues_opaque_uuid4_hex():
    supplier = ProductionAcquisitionCostNormalizationIdentityGenerator()
    values = {supplier() for _ in range(128)}

    assert len(values) == 128
    assert all(len(value) == 32 for value in values)
    assert all(value == value.lower() for value in values)
    assert all(set(value) <= set("0123456789abcdef") for value in values)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")


@pytest.mark.parametrize(
    "basis",
    [CostAllocationBasis.PER_WEIGHT, CostAllocationBasis.UNSPECIFIED],
)
def test_unresolved_weight_and_unspecified_allocation_never_normalize(basis):
    composition = complete_composition()
    valid = list(allocations(composition))
    repository = MemoryAllocationRepository(composition)
    boundary, *_ = allocation_boundary(repository, identity=Calls("unresolved"))
    unresolved = boundary.execute(
        allocation_command(
            composition,
            command_id="unresolved-command",
            component_kind=LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            effective_allocation_basis=(
                basis if basis is CostAllocationBasis.PER_WEIGHT else None
            ),
            per_order_denominator=None,
            per_order_denominator_unit=None,
            operator_id=(None if basis is CostAllocationBasis.UNSPECIFIED else "founder"),
            verified_at=(None if basis is CostAllocationBasis.UNSPECIFIED else NOW),
            evidence_reference=(
                None if basis is CostAllocationBasis.UNSPECIFIED else composition.evidence_reference
            ),
        )
    ).authority
    valid[0] = unresolved
    observations = (
        fx("fx-cny-krw", "CNY", "KRW", "190"),
        fx("fx-usd-krw", "USD", "KRW", "1400"),
    )

    with pytest.raises(AcquisitionCostNormalizationSourceError):
        normalize(composition, tuple(valid), observations)


@pytest.mark.parametrize("mismatch", ["composition", "opportunity"])
def test_allocation_authority_from_wrong_lineage_is_rejected(mismatch):
    composition = complete_composition()
    authorities = list(allocations(composition))
    if mismatch == "composition":
        authorities[0] = replace(authorities[0], composition_id="other-composition")
    else:
        from app.domain.decision_engine import OpportunityIdentity

        authorities[0] = replace(
            authorities[0],
            opportunity_identity=OpportunityIdentity("other-opportunity", "other-discovery"),
        )
    observations = (
        fx("fx-cny-krw", "CNY", "KRW", "190"),
        fx("fx-usd-krw", "USD", "KRW", "1400"),
    )

    with pytest.raises(AcquisitionCostNormalizationSourceError):
        normalize(composition, tuple(authorities), observations)
