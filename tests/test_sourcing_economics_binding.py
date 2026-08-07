from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from app.application.sourcing import (
    BindSourcingEconomicsSource,
    BindSourcingEconomicsSourceCommand,
    SourcingEconomicsBindingOpportunityMismatchError,
    SourcingEconomicsBindingReplayConflictError,
    SourcingEconomicsSourceNotFoundError,
    SourcingEconomicsExactRevisionError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
)
from test_sourcing_authority_contract import NOW, command, service


class MemoryBindings:
    def __init__(self, sourcing):
        self.sourcing = sourcing
        self.results = {}
        self.bindings = {}

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is None:
            return None
        if result.receipt.command_fingerprint != fingerprint:
            raise SourcingEconomicsBindingReplayConflictError("payload conflicts")
        return result

    def get_source_admission(self, reference):
        return self.sourcing.get_admission_revision(
            reference.admission_id, reference.admission_revision
        )

    def save_binding(self, command, binding, receipt):
        from app.application.sourcing import SourcingEconomicsBindingResult
        result = SourcingEconomicsBindingResult(binding, receipt, False)
        self.results[command.command_id] = result
        self.bindings[binding.binding_id] = binding
        return result

    def get_binding(self, binding_id): return self.bindings.get(binding_id)
    def get_receipt(self, command_id):
        result = self.results.get(command_id)
        return None if result is None else result.receipt


class Counter:
    def __init__(self, value): self.value, self.calls = value, 0
    def __call__(self): self.calls += 1; return self.value


def prepare():
    sourcing_service, sourcing, _ = service()
    admission = sourcing_service.execute(command()).admission
    repository = MemoryBindings(sourcing)
    identity = Counter("binding-opaque-1")
    bound = Counter(NOW + timedelta(minutes=1))
    committed = Counter(NOW + timedelta(minutes=2))
    use_case = BindSourcingEconomicsSource(
        repository, binding_id_generator=identity,
        bound_clock=bound, committed_clock=committed,
    )
    return admission, repository, use_case, identity, bound, committed


def binding_command(admission, **changes):
    values = {
        "command_id": "binding-command-1",
        "opportunity_identity": OpportunityIdentity("opp-1", "discovery-1"),
        "source_reference": admission.to_economics_source_reference(),
        "requested_at": NOW,
    }
    values.update(changes)
    return BindSourcingEconomicsSourceCommand(**values)


def test_valid_exact_binding_preserves_opaque_identity_lineage_and_timestamps():
    admission, repository, use_case, identity, bound, committed = prepare()
    result = use_case.execute(binding_command(admission))
    assert result.binding == SourcingEconomicsBinding(
        "binding-opaque-1", OpportunityIdentity("opp-1", "discovery-1"),
        admission.to_economics_source_reference(), NOW,
        NOW + timedelta(minutes=1),
    )
    assert result.reference == SourcingEconomicsBindingReference("binding-opaque-1")
    assert result.receipt.committed_at == NOW + timedelta(minutes=2)
    assert identity.calls == bound.calls == committed.calls == 1
    assert repository.get_binding("binding-opaque-1") == result.binding


def test_binding_is_immutable():
    admission, _, use_case, *_ = prepare()
    result = use_case.execute(binding_command(admission))
    with pytest.raises(FrozenInstanceError):
        result.binding.binding_id = "changed"


def test_missing_exact_admission_revision_is_rejected_without_issuing_identity():
    admission, _, use_case, identity, bound, committed = prepare()
    source = replace(
        admission.to_economics_source_reference(),
        admission_revision=99, quote_revision=99,
    )
    with pytest.raises(SourcingEconomicsSourceNotFoundError):
        use_case.execute(binding_command(admission, source_reference=source))
    assert identity.calls == bound.calls == committed.calls == 0


def test_wrong_quote_identity_is_rejected_without_latest_substitution():
    admission, _, use_case, *_ = prepare()
    source = replace(admission.to_economics_source_reference(), quote_id="quote-other")
    with pytest.raises(SourcingEconomicsExactRevisionError):
        use_case.execute(binding_command(admission, source_reference=source))


def test_opportunity_lineage_mismatch_is_rejected():
    admission, _, use_case, *_ = prepare()
    with pytest.raises(SourcingEconomicsBindingOpportunityMismatchError):
        use_case.execute(binding_command(
            admission, opportunity_identity=OpportunityIdentity("opp-other", "discovery-1")
        ))


def test_exact_replay_returns_committed_fact_without_identity_or_clock_calls():
    admission, _, use_case, identity, bound, committed = prepare()
    command_value = binding_command(admission)
    first = use_case.execute(command_value)
    replay = use_case.execute(command_value)
    assert replay.binding == first.binding
    assert replay.receipt == first.receipt
    assert replay.replayed is True
    assert identity.calls == bound.calls == committed.calls == 1


def test_same_command_changed_payload_is_conflict():
    admission, _, use_case, identity, bound, committed = prepare()
    use_case.execute(binding_command(admission))
    with pytest.raises(SourcingEconomicsBindingReplayConflictError):
        use_case.execute(binding_command(admission, requested_at=NOW + timedelta(seconds=1)))
    assert identity.calls == bound.calls == committed.calls == 1
