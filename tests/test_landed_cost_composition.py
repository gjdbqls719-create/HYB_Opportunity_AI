from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.sourcing import (
    ComposeLandedCost,
    ComposeLandedCostCommand,
    LandedCostCompositionOpportunityMismatchError,
    LandedCostCompositionReplayConflictError,
    SourcingEconomicsBindingNotFoundError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    LandedCostComponent,
    LandedCostComponentKind,
    SourcingMoneyFact,
)
from test_sourcing_authority_contract import NOW, command, service
from test_sourcing_economics_binding import (
    binding_command,
    prepare as prepare_binding,
)


class Counter:
    def __init__(self, value):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


class MemoryCompositions:
    def __init__(self, binding, admission):
        self.binding = binding
        self.admission = admission
        self.results = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is not None and result.receipt.command_fingerprint != fingerprint:
            raise LandedCostCompositionReplayConflictError("payload conflict")
        return result

    def get_binding(self, reference):
        return (
            self.binding
            if self.binding is not None and reference == self.binding.reference
            else None
        )

    def get_source_admission(self, reference):
        return self.admission if reference == self.admission.to_economics_source_reference() else None

    def save_composition(self, command, composition, receipt):
        from app.application.sourcing import LandedCostCompositionResult
        result = LandedCostCompositionResult(composition, receipt, False)
        self.results[command.command_id] = result
        return result


def prepare():
    admission, _, binding_use_case, *_ = prepare_binding()
    binding = binding_use_case.execute(binding_command(admission)).binding
    repository = MemoryCompositions(binding, admission)
    identity = Counter("landed-cost-opaque-1")
    composed = Counter(NOW + timedelta(minutes=3))
    committed = Counter(NOW + timedelta(minutes=4))
    use_case = ComposeLandedCost(
        repository,
        composition_id_generator=identity,
        composed_clock=composed,
        committed_clock=committed,
    )
    return admission, binding, repository, use_case, identity, composed, committed


def composition_command(binding, **changes):
    values = dict(
        command_id="landed-cost-command-1",
        opportunity_identity=OpportunityIdentity("opp-1", "discovery-1"),
        binding_reference=binding.reference,
        requested_at=NOW,
    )
    values.update(changes)
    return ComposeLandedCostCommand(**values)


def component(composition, kind):
    return next(value for value in composition.components if value.kind is kind)


def test_valid_composition_preserves_exact_binding_identity_quantity_and_evidence():
    admission, binding, _, use_case, identity, composed, committed = prepare()
    result = use_case.execute(composition_command(binding))
    value = result.composition
    assert value.composition_id == "landed-cost-opaque-1"
    assert value.opportunity_identity == binding.opportunity_identity
    assert value.binding_reference == binding.reference
    assert value.minimum_order_quantity == admission.quote_revision.minimum_order_quantity
    assert value.quoted_quantity == admission.quote_revision.quoted_quantity
    assert value.evidence_reference == admission.quote_revision.evidence
    assert value.requested_at == NOW
    assert value.composed_at == NOW + timedelta(minutes=3)
    assert result.receipt.committed_at == NOW + timedelta(minutes=4)
    assert identity.calls == composed.calls == committed.calls == 1


def test_unit_purchase_is_per_unit_and_is_not_multiplied_by_moq():
    admission, binding, _, use_case, *_ = prepare()
    value = use_case.execute(composition_command(binding)).composition
    purchase = component(value, LandedCostComponentKind.UNIT_PURCHASE)
    assert purchase.amount == admission.quote_revision.unit_price.amount
    assert purchase.amount != admission.quote_revision.unit_price.amount * admission.quote_revision.minimum_order_quantity.quantity
    assert purchase.allocation_basis is CostAllocationBasis.PER_UNIT


def test_shipping_scopes_remain_independent_without_aggregation_or_allocation_inference():
    admission, binding, _, use_case, *_ = prepare()
    value = use_case.execute(composition_command(binding)).composition
    for term, kind in zip(admission.quote_revision.shipping_terms, (
        LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING,
        LandedCostComponentKind.INTERNATIONAL_FREIGHT,
        LandedCostComponentKind.DOMESTIC_INBOUND,
    )):
        cost = component(value, kind)
        assert (cost.availability, cost.amount, cost.currency) == (
            term.cost.availability, term.cost.amount, term.cost.currency
        )
        assert cost.allocation_basis is CostAllocationBasis.UNSPECIFIED
    assert not hasattr(value, "shipping_cost")


def test_known_zero_unknown_and_not_applicable_are_distinct():
    admission, binding, repository, use_case, *_ = prepare()
    terms = admission.quote_revision.shipping_terms
    quote = replace(admission.quote_revision, shipping_terms=(
        replace(terms[0], cost=SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("0"), "CNY")),
        replace(terms[1], cost=SourcingMoneyFact(CommercialFactAvailability.UNKNOWN)),
        replace(terms[2], cost=SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE)),
    ))
    repository.admission = replace(admission, quote_revision=quote)
    value = use_case.execute(composition_command(binding)).composition
    values = value.components[1:]
    assert values[0].amount == Decimal("0") and values[0].currency == "CNY"
    assert values[1].amount is None and values[1].currency is None
    assert values[2].amount is None and values[2].currency is None
    assert len({item.availability for item in values}) == 3


def test_mixed_currencies_are_preserved_without_fx_conversion():
    admission, binding, repository, use_case, *_ = prepare()
    terms = admission.quote_revision.shipping_terms
    quote = replace(admission.quote_revision, shipping_terms=(
        replace(terms[0], cost=SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("2"), "CNY")),
        replace(terms[1], cost=SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("3"), "USD")),
        replace(terms[2], cost=SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("4"), "KRW")),
    ))
    repository.admission = replace(admission, quote_revision=quote)
    value = use_case.execute(composition_command(binding)).composition
    assert value.known_currencies == ("CNY", "USD", "KRW")
    assert not hasattr(value, "fx_rate")


def test_opportunity_mismatch_is_rejected_before_identity_or_clocks():
    _, binding, _, use_case, identity, composed, committed = prepare()
    with pytest.raises(LandedCostCompositionOpportunityMismatchError):
        use_case.execute(composition_command(
            binding, opportunity_identity=OpportunityIdentity("other", "discovery-1")
        ))
    assert identity.calls == composed.calls == committed.calls == 0


def test_missing_exact_binding_is_rejected():
    _, binding, repository, use_case, *_ = prepare()
    repository.binding = None
    with pytest.raises(SourcingEconomicsBindingNotFoundError):
        use_case.execute(composition_command(binding))


def test_exact_replay_does_not_reissue_identity_or_timestamps():
    _, binding, _, use_case, identity, composed, committed = prepare()
    cmd = composition_command(binding)
    first = use_case.execute(cmd)
    replay = use_case.execute(cmd)
    assert replay.composition == first.composition
    assert replay.receipt == first.receipt
    assert replay.replayed
    assert identity.calls == composed.calls == committed.calls == 1


def test_changed_payload_conflicts_and_composition_is_immutable():
    _, binding, _, use_case, *_ = prepare()
    result = use_case.execute(composition_command(binding))
    with pytest.raises(LandedCostCompositionReplayConflictError):
        use_case.execute(composition_command(binding, requested_at=NOW + timedelta(seconds=1)))
    with pytest.raises(FrozenInstanceError):
        result.composition.composition_id = "changed"


def test_component_allocation_and_availability_validation_rejects_lossy_states():
    with pytest.raises(ValueError, match="per-unit"):
        LandedCostComponent(
            LandedCostComponentKind.UNIT_PURCHASE,
            CommercialFactAvailability.KNOWN,
            Decimal("5"), "CNY", CostAllocationBasis.UNSPECIFIED,
        )
    with pytest.raises(ValueError, match="cannot carry money"):
        LandedCostComponent(
            LandedCostComponentKind.INTERNATIONAL_FREIGHT,
            CommercialFactAvailability.UNKNOWN,
            Decimal("0"), "CNY", CostAllocationBasis.UNSPECIFIED,
        )


def test_later_source_revision_cannot_mutate_existing_composition():
    admission, binding, repository, use_case, *_ = prepare()
    original = use_case.execute(composition_command(binding)).composition
    repository.admission = replace(
        admission,
        quote_revision=replace(
            admission.quote_revision,
            unit_price=SourcingMoneyFact(
                CommercialFactAvailability.KNOWN, Decimal("999"), "CNY"
            ),
        ),
    )
    assert component(original, LandedCostComponentKind.UNIT_PURCHASE).amount != Decimal("999")
