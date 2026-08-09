from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.sourcing import (
    CriticalCostSourceMismatchError,
    CriticalCostSourceNotFoundError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
    EvaluateCriticalCostCompleteness,
    NormalizeAcquisitionCosts,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    LandedCostComponentKind,
    ShippingAllocationAuthorityStatus,
    SourcingMoneyFact,
)
from app.domain.decision_engine import OpportunityIdentity
from test_acquisition_cost_normalization import (
    Calls,
    MemoryNormalizationRepository,
    command as normalization_command,
    fx,
)
from test_critical_cost_completeness import economics, scenario
from test_shipping_allocation_authority_reconciliation import (
    MemoryAllocationRepository,
    boundary as allocation_boundary,
    command as allocation_command,
)
from test_sourcing_authority_contract import NOW


class ExactCriticalCostSources:
    def __init__(self, sources, normalization, authorities=(), observations=()):
        self._sources = sources
        self.normalization = normalization
        self.authorities = {value.authority_id: value for value in authorities}
        self.observations = {value.observation_id: value for value in observations}
        self.normalization_reads = []
        self.allocation_reads = []
        self.fx_reads = []

    def get_composition(self, composition_id):
        return self._sources.get_composition(composition_id)

    def get_binding(self, reference):
        return self._sources.get_binding(reference)

    def get_source_admission(self, reference):
        return self._sources.get_source_admission(reference)

    def get_verified_economics_snapshot(self, opportunity_id):
        return self._sources.get_verified_economics_snapshot(opportunity_id)

    def get_acquisition_normalization(self, normalization_id):
        self.normalization_reads.append(normalization_id)
        if self.normalization is None:
            return None
        return self.normalization if normalization_id == self.normalization.normalization_id else None

    def get_allocation_authority(self, authority_id):
        self.allocation_reads.append(authority_id)
        return self.authorities.get(authority_id)

    def get_fx_observation(self, observation_id):
        self.fx_reads.append(observation_id)
        return self.observations.get(observation_id)


def reconciled_sources(*, economics_currency="KRW", target_currency="KRW"):
    shipping = (
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("120"), "CNY"),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
    )
    _, sources = scenario(
        shipping=shipping,
        verified=economics(currency=economics_currency),
    )
    composition = sources.composition
    allocation_repository = MemoryAllocationRepository(composition)
    allocation = allocation_boundary(
        allocation_repository,
        identity=Calls("allocation-supplier"),
    )[0].execute(
        allocation_command(
            composition,
            component_kind=LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
            effective_allocation_basis=CostAllocationBasis.PER_QUOTED_QUANTITY,
            per_order_denominator=None,
            per_order_denominator_unit=None,
        )
    ).authority
    observations = (
        ()
        if target_currency == "CNY"
        else (fx("fx-cny-krw", "CNY", "KRW", "190"),)
    )
    normalization_repository = MemoryNormalizationRepository(
        composition,
        (allocation,),
        observations,
    )
    normalization = NormalizeAcquisitionCosts(
        normalization_repository,
        normalization_id_generator=lambda: "normalization-1",
        normalized_clock=lambda: NOW + timedelta(minutes=2),
        committed_clock=lambda: NOW + timedelta(minutes=3),
    ).execute(
        normalization_command(
            composition,
            (allocation,),
            observations,
            target_currency=target_currency,
        )
    ).normalization
    repository = ExactCriticalCostSources(
        sources,
        normalization,
        (allocation,),
        observations,
    )
    evaluator = EvaluateCriticalCostCompleteness(
        repository,
        repository,
        policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        evaluated_clock=lambda: NOW,
    )
    return evaluator, repository, composition, normalization, allocation, observations


def reason_codes(assessment):
    return tuple(value.code for value in assessment.blocking_reasons)


def test_exact_normalization_resolves_original_shipping_and_fx_without_recalculation():
    evaluator, repository, composition, normalization, allocation, observations = (
        reconciled_sources()
    )

    assessment = evaluator.execute(composition.composition_id, normalization.normalization_id)

    assert assessment.state is CriticalCostCompletenessState.COMPLETE
    assert assessment.acquisition_normalization_id == normalization.normalization_id
    assert assessment.allocation_authority_ids == (allocation.authority_id,)
    assert assessment.fx_observation_ids == (observations[0].observation_id,)
    assert CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN not in reason_codes(assessment)
    assert CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING not in reason_codes(assessment)
    assert repository.normalization_reads == [normalization.normalization_id]
    assert repository.allocation_reads == [allocation.authority_id]
    assert repository.fx_reads == [observations[0].observation_id] * 2
    assert not hasattr(assessment, "total_per_unit_acquisition_cost")
    with pytest.raises(FrozenInstanceError):
        assessment.acquisition_normalization_id = "changed"


def test_same_currency_complete_requires_no_fake_fx():
    evaluator, repository, composition, normalization, _, _ = reconciled_sources(
        economics_currency="CNY",
        target_currency="CNY",
    )

    assessment = evaluator.execute(composition.composition_id, normalization.normalization_id)

    assert assessment.is_complete
    assert assessment.fx_observation_ids == ()
    assert repository.fx_reads == []


def test_normalization_target_must_equal_verified_economics_currency():
    evaluator, _, composition, normalization, _, _ = reconciled_sources(
        economics_currency="KRW",
        target_currency="CNY",
    )

    assessment = evaluator.execute(composition.composition_id, normalization.normalization_id)

    assert assessment.state is CriticalCostCompletenessState.INCOMPLETE
    assert reason_codes(assessment) == (CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING,)


def test_missing_or_mismatched_exact_normalization_is_rejected():
    evaluator, repository, composition, normalization, _, _ = reconciled_sources()
    repository.normalization = None
    with pytest.raises(CriticalCostSourceNotFoundError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)

    repository.normalization = replace(normalization, composition_id="other-composition")
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)

    repository.normalization = replace(
        normalization,
        opportunity_identity=OpportunityIdentity("source-opportunity", "source:foreign"),
    )
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)


def test_missing_unresolved_or_mismatched_allocation_authority_is_rejected():
    evaluator, repository, composition, normalization, allocation, _ = reconciled_sources()
    repository.authorities = {}
    with pytest.raises(CriticalCostSourceNotFoundError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)

    repository.authorities = {
        allocation.authority_id: replace(
            allocation,
            status=ShippingAllocationAuthorityStatus.UNRESOLVED,
            denominator=None,
            unresolved_code="per_quoted_quantity_denominator_missing",
        )
    }
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)

    repository.authorities = {
        allocation.authority_id: replace(allocation, composition_id="other-composition")
    }
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)


def test_missing_or_wrong_exact_fx_observation_is_rejected():
    evaluator, repository, composition, normalization, _, observations = reconciled_sources()
    repository.observations = {}
    with pytest.raises(CriticalCostSourceNotFoundError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)

    repository.observations = {
        observations[0].observation_id: fx("fx-cny-krw", "USD", "KRW", "1400")
    }
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(composition.composition_id, normalization.normalization_id)


def test_quote_validity_semantics_are_unchanged_for_v2():
    _, repository, composition, normalization, _, _ = reconciled_sources()
    evaluator = EvaluateCriticalCostCompleteness(
        repository,
        repository,
        policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        evaluated_clock=lambda: NOW + timedelta(days=2),
    )

    assessment = evaluator.execute(composition.composition_id, normalization.normalization_id)

    assert assessment.state is CriticalCostCompletenessState.INCOMPLETE
    assert reason_codes(assessment) == (CriticalCostReasonCode.QUOTE_EXPIRED,)
