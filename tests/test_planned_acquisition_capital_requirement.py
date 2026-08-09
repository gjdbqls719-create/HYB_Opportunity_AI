from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import re

import pytest

from app.application.capital_requirement import (
    CalculatePlannedAcquisitionCapitalRequirement,
    CalculatePlannedAcquisitionCapitalRequirementCommand,
    PlannedAcquisitionCapitalRequirementLineageError,
    PlannedAcquisitionCapitalRequirementPolicyError,
    PlannedAcquisitionCapitalRequirementPublication,
    PlannedAcquisitionCapitalRequirementReplayConflictError,
)
from app.domain.capital import (
    PlannedAcquisitionCapitalRequirementState,
    UpfrontCostScopeStatus,
)
from app.domain.sourcing import (
    SourcingEconomicsBinding,
    SourcingEconomicsSourceReference,
)
from test_acquisition_cost_normalization import (
    allocations,
    complete_composition,
    fx,
    normalize,
)
from test_capital_investment_facts import Calls
from test_sourcing_authority_contract import NOW
from app.infrastructure.capital_requirement import (
    ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator,
)


class MemoryRequirementRepository:
    def __init__(self, intent, normalization, composition, binding):
        self.intent = intent
        self.normalization = normalization
        self.composition = composition
        self.binding = binding
        self.results = {}

    def get_intent(self, identity):
        return self.intent if self.intent.intent_id == identity else None

    def get_normalization(self, identity):
        return self.normalization if self.normalization.normalization_id == identity else None

    def get_composition(self, identity):
        return self.composition if self.composition.composition_id == identity else None

    def get_binding(self, reference):
        return self.binding if self.binding.reference == reference else None

    def validate_replay(self, command_id, fingerprint):
        value = self.results.get(command_id)
        if value is not None and value.receipt.command_fingerprint != fingerprint:
            raise PlannedAcquisitionCapitalRequirementReplayConflictError("payload conflicts")
        return value

    def save_requirement(self, command, requirement, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        result = PlannedAcquisitionCapitalRequirementPublication(requirement, receipt, False)
        self.results[command.command_id] = result
        return result


def sources():
    from app.domain.capital import IntendedOrderQuantity

    composition = complete_composition()
    binding = SourcingEconomicsBinding(
        composition.binding_reference.binding_id,
        composition.opportunity_identity,
        SourcingEconomicsSourceReference("admission-1", 1, "quote-1", 1),
        NOW,
        NOW + timedelta(minutes=1),
    )
    authorities = allocations(composition)
    observations = (
        fx("fx-cny-krw", "CNY", "KRW", "190"),
        fx("fx-usd-krw", "USD", "KRW", "1400"),
    )
    normalization = normalize(composition, authorities, observations)[0].normalization
    intent = IntendedOrderQuantity(
        "intent-1",
        composition.opportunity_identity,
        "admission-1",
        1,
        "quote-1",
        1,
        25,
        "units",
        "founder-1",
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
    )
    return intent, normalization, composition, binding


def command(intent, normalization, **changes):
    values = {
        "command_id": "requirement-command-1",
        "opportunity_identity": intent.opportunity_identity,
        "intended_order_quantity_id": intent.intent_id,
        "acquisition_normalization_id": normalization.normalization_id,
        "scope_status": UpfrontCostScopeStatus.COMPLETE,
        "operator_id": "founder-1",
        "verified_at": NOW + timedelta(minutes=11),
        "requested_at": NOW + timedelta(minutes=12),
        "policy_name": "planned-acquisition-capital-requirement",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    return CalculatePlannedAcquisitionCapitalRequirementCommand(**values)


def owner(repository, *, fail=False):
    identity = Calls(AssertionError("identity called on replay") if fail else "requirement-1")
    calculated = Calls(AssertionError("calculated clock called on replay") if fail else NOW + timedelta(minutes=13))
    committed = Calls(AssertionError("committed clock called on replay") if fail else NOW + timedelta(minutes=14))
    return (
        CalculatePlannedAcquisitionCapitalRequirement(
            repository,
            requirement_id_generator=identity,
            calculated_clock=calculated,
            committed_clock=committed,
        ),
        identity,
        calculated,
        committed,
    )


def prepared():
    values = sources()
    return values, MemoryRequirementRepository(*values)


def test_complete_scope_calculates_exact_decimal_requirement_from_exact_sources():
    (intent, normalization, composition, binding), repository = prepared()
    result = owner(repository)[0].execute(command(intent, normalization))
    requirement = result.requirement

    assert requirement.state is PlannedAcquisitionCapitalRequirementState.CALCULABLE
    assert requirement.planned_acquisition_capital == Decimal("188088.7500")
    assert requirement.normalized_acquisition_cost_per_unit == Decimal("7523.5500")
    assert requirement.quantity == 25
    assert requirement.currency == "KRW"
    assert requirement.intended_order_quantity_id == intent.intent_id
    assert requirement.acquisition_normalization_id == normalization.normalization_id
    assert requirement.sourcing_binding_id == binding.binding_id
    assert requirement.sourcing_admission_id == "admission-1"
    assert requirement.quote_id == "quote-1"
    assert requirement.scope_verification.operator_id == "founder-1"
    assert requirement.scope_verification.verified_at == NOW + timedelta(minutes=11)
    assert requirement.blocking_reasons == ()
    assert requirement.policy_name == "planned-acquisition-capital-requirement"
    assert requirement.policy_version == "1.0.0"
    assert result.replayed is False
    with pytest.raises(FrozenInstanceError):
        requirement.quantity = 1


def test_unresolved_scope_is_authoritative_blocked_result_without_numeric_amount():
    (intent, normalization, *_), repository = prepared()
    result = owner(repository)[0].execute(
        command(intent, normalization, scope_status=UpfrontCostScopeStatus.UNRESOLVED)
    )
    assert result.requirement.state is PlannedAcquisitionCapitalRequirementState.BLOCKED
    assert result.requirement.planned_acquisition_capital is None
    assert tuple(value.value for value in result.requirement.blocking_reasons) == (
        "upfront_cost_scope_unverified",
    )


def test_requirement_never_uses_moq_quoted_quantity_or_shipping_denominator():
    (intent, normalization, composition, _), repository = prepared()
    value = owner(repository)[0].execute(command(intent, normalization)).requirement
    assert value.quantity == intent.quantity
    assert value.quantity != composition.minimum_order_quantity.quantity
    assert value.quantity != composition.quoted_quantity.quantity
    assert value.quantity not in {
        item.denominator_quantity
        for item in normalization.components
        if item.denominator_quantity is not None
    }


@pytest.mark.parametrize("field", ["opportunity", "admission", "quote", "binding"])
def test_exact_opportunity_and_sourcing_lineage_mismatch_is_rejected(field):
    (intent, normalization, composition, binding), repository = prepared()
    if field == "opportunity":
        from app.domain.decision_engine import OpportunityIdentity
        repository.intent = replace(intent, opportunity_identity=OpportunityIdentity("other", "discovery-1"))
    elif field == "admission":
        repository.intent = replace(intent, sourcing_admission_id="other")
    elif field == "quote":
        repository.intent = replace(intent, quote_id="other")
    else:
        repository.binding = replace(
            binding,
            source_reference=replace(binding.source_reference, quote_id="other"),
        )
    use_case, identity, calculated, committed = owner(repository)
    with pytest.raises(PlannedAcquisitionCapitalRequirementLineageError):
        use_case.execute(command(intent, normalization))
    assert identity.calls == calculated.calls == committed.calls == 0


def test_exact_replay_skips_identity_clocks_and_recalculation_and_changed_payload_conflicts():
    (intent, normalization, *_), repository = prepared()
    request = command(intent, normalization)
    first = owner(repository)[0].execute(request)
    replay = owner(repository, fail=True)[0].execute(request)
    assert replay.replayed is True
    assert replay.requirement == first.requirement
    assert replay.receipt == first.receipt
    for changed in (
        replace(request, intended_order_quantity_id="other"),
        replace(request, acquisition_normalization_id="other"),
        replace(request, scope_status=UpfrontCostScopeStatus.UNRESOLVED),
        replace(request, operator_id="other"),
        replace(request, verified_at=request.verified_at + timedelta(seconds=1)),
    ):
        with pytest.raises(PlannedAcquisitionCapitalRequirementReplayConflictError):
            owner(repository, fail=True)[0].execute(changed)


def test_unsupported_policy_is_rejected_before_identity_and_clocks():
    (intent, normalization, *_), repository = prepared()
    use_case, identity, calculated, committed = owner(repository)
    with pytest.raises(PlannedAcquisitionCapitalRequirementPolicyError):
        use_case.execute(command(intent, normalization, policy_version="2.0.0"))
    assert identity.calls == calculated.calls == committed.calls == 0


def test_requirement_has_no_deployable_capital_gate_profit_or_miscellaneous_cost_semantics():
    (intent, normalization, *_), repository = prepared()
    value = owner(repository)[0].execute(command(intent, normalization)).requirement
    forbidden = {
        "deployable_capital", "capital_sufficiency", "gate_state", "profit",
        "roi", "margin", "approved", "miscellaneous_upfront_cost",
    }
    assert forbidden.isdisjoint(value.__dataclass_fields__)


def test_command_rejects_malformed_scope_operator_time_and_policy_facts():
    (intent, normalization, *_), _ = prepared()
    for changes in (
        {"operator_id": " "},
        {"verified_at": NOW.replace(tzinfo=None)},
        {"requested_at": NOW.replace(tzinfo=None)},
        {"scope_status": "fabricated"},
        {"policy_name": " "},
    ):
        with pytest.raises((TypeError, ValueError)):
            command(intent, normalization, **changes)


def test_production_identity_supplier_is_dedicated_stateless_uuid4_hex():
    supplier = ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator()
    values = {supplier() for _ in range(16)}
    assert len(values) == 16
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
