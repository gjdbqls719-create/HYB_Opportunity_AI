from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import re

import pytest

from app.application.capital_investment import (
    AdmitDeployableCapitalSnapshot,
    AdmitDeployableCapitalSnapshotCommand,
    AdmitIntendedOrderQuantity,
    AdmitIntendedOrderQuantityCommand,
    CapitalInvestmentLineageError,
    CapitalInvestmentReplayConflictError,
    CapitalInvestmentSourceNotFoundError,
)
from app.domain.capital import (
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    DeployableCapitalSnapshot,
    IntendedOrderQuantity,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.capital_investment import (
    ProductionDeployableCapitalSnapshotIdentityGenerator,
    ProductionIntendedOrderQuantityIdentityGenerator,
)
from test_sourcing_authority_contract import NOW, command as sourcing_command, service


class Calls:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class MemoryCapitalInvestmentFacts:
    def __init__(self, sourcing):
        self.sourcing = sourcing
        self.intent_results = {}
        self.intents = {}
        self.capital_results = {}
        self.snapshots = {}

    def get_sourcing_admission(self, admission_id, revision):
        return self.sourcing.get_admission_revision(admission_id, revision)

    def validate_intent_replay(self, command_id, fingerprint):
        result = self.intent_results.get(command_id)
        if result is None:
            return None
        if result.receipt.command_fingerprint != fingerprint:
            raise CapitalInvestmentReplayConflictError("intent payload conflicts")
        return result

    def save_intent(self, command, intent, receipt):
        from app.application.capital_investment import IntendedOrderQuantityPublication

        result = IntendedOrderQuantityPublication(intent, receipt, False)
        self.intent_results[command.command_id] = result
        self.intents[intent.intent_id] = intent
        return result

    def validate_capital_replay(self, command_id, fingerprint):
        result = self.capital_results.get(command_id)
        if result is None:
            return None
        if result.receipt.command_fingerprint != fingerprint:
            raise CapitalInvestmentReplayConflictError("capital payload conflicts")
        return result

    def save_deployable_capital(self, command, snapshot, receipt):
        from app.application.capital_investment import DeployableCapitalPublication

        result = DeployableCapitalPublication(snapshot, receipt, False)
        self.capital_results[command.command_id] = result
        self.snapshots[snapshot.snapshot_id] = snapshot
        return result


def prepare():
    sourcing_owner, sourcing, _ = service()
    admission = sourcing_owner.execute(sourcing_command()).admission
    repository = MemoryCapitalInvestmentFacts(sourcing)
    return admission, repository


def intent_command(admission, **changes):
    values = {
        "command_id": "intent-command-1",
        "opportunity_identity": admission.selling_product_lineage.opportunity_identity,
        "sourcing_admission_id": admission.admission_id,
        "sourcing_admission_revision": admission.revision,
        "quote_id": admission.quote_revision.quote_id,
        "quote_revision": admission.quote_revision.revision,
        "quantity": 25,
        "quantity_unit": "units",
        "operator_id": "founder-1",
        "requested_at": NOW,
        "declared_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return AdmitIntendedOrderQuantityCommand(**values)


def capital_command(**changes):
    values = {
        "command_id": "capital-command-1",
        "amount": Decimal("1500000.00"),
        "currency": "KRW",
        "as_of": NOW,
        "operator_id": "founder-1",
        "requested_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return AdmitDeployableCapitalSnapshotCommand(**values)


def intent_owner(repository, *, fail=False):
    identity = Calls(AssertionError("identity called on replay") if fail else "intent-opaque-1")
    admitted = Calls(AssertionError("admitted clock called on replay") if fail else NOW + timedelta(minutes=2))
    committed = Calls(AssertionError("committed clock called on replay") if fail else NOW + timedelta(minutes=3))
    return AdmitIntendedOrderQuantity(
        repository,
        intent_id_generator=identity,
        admitted_clock=admitted,
        committed_clock=committed,
    ), identity, admitted, committed


def capital_owner(repository, *, fail=False):
    identity = Calls(AssertionError("identity called on replay") if fail else "capital-opaque-1")
    admitted = Calls(AssertionError("admitted clock called on replay") if fail else NOW + timedelta(minutes=2))
    committed = Calls(AssertionError("committed clock called on replay") if fail else NOW + timedelta(minutes=3))
    return AdmitDeployableCapitalSnapshot(
        repository,
        snapshot_id_generator=identity,
        admitted_clock=admitted,
        committed_clock=committed,
    ), identity, admitted, committed


def test_explicit_intended_quantity_preserves_exact_sourcing_lineage_without_inference():
    admission, repository = prepare()
    owner, identity, admitted, committed = intent_owner(repository)
    result = owner.execute(intent_command(admission))

    assert result.intent == IntendedOrderQuantity(
        intent_id="intent-opaque-1",
        opportunity_identity=OpportunityIdentity("opp-1", "discovery-1"),
        sourcing_admission_id=admission.admission_id,
        sourcing_admission_revision=admission.revision,
        quote_id=admission.quote_revision.quote_id,
        quote_revision=admission.quote_revision.revision,
        quantity=25,
        quantity_unit="units",
        operator_id="founder-1",
        requested_at=NOW,
        declared_at=NOW + timedelta(minutes=1),
        admitted_at=NOW + timedelta(minutes=2),
    )
    assert result.intent.quantity not in {
        admission.quote_revision.minimum_order_quantity.quantity,
        admission.quote_revision.quoted_quantity.quantity,
    }
    assert identity.calls == admitted.calls == committed.calls == 1


@pytest.mark.parametrize(
    "changes",
    ({"quantity": 0}, {"quantity": -1}, {"quantity": True}, {"quantity": Decimal("1")}, {"quantity_unit": " "}),
)
def test_intended_quantity_requires_explicit_positive_integer_and_unit(changes):
    admission, _ = prepare()
    with pytest.raises((TypeError, ValueError)):
        intent_command(admission, **changes)


def test_intent_rejects_missing_wrong_opportunity_and_wrong_quote_before_server_authority():
    admission, repository = prepare()
    owner, identity, admitted, committed = intent_owner(repository)
    with pytest.raises(CapitalInvestmentSourceNotFoundError):
        owner.execute(intent_command(admission, sourcing_admission_revision=99, quote_revision=99))
    with pytest.raises(CapitalInvestmentLineageError):
        owner.execute(intent_command(
            admission,
            opportunity_identity=OpportunityIdentity("other", "discovery-1"),
        ))
    with pytest.raises(CapitalInvestmentLineageError):
        owner.execute(intent_command(admission, quote_id="other-quote"))
    assert identity.calls == admitted.calls == committed.calls == 0


def test_intent_exact_replay_skips_identity_and_clocks_and_changed_payload_conflicts():
    admission, repository = prepare()
    command = intent_command(admission)
    first = intent_owner(repository)[0].execute(command)
    replay = intent_owner(repository, fail=True)[0].execute(command)
    assert replay.replayed is True
    assert replay.intent == first.intent
    assert replay.receipt == first.receipt
    with pytest.raises(CapitalInvestmentReplayConflictError):
        intent_owner(repository, fail=True)[0].execute(replace(command, quantity=26))


def test_deployable_capital_is_reserve_adjusted_immutable_fact_and_zero_is_valid():
    _, repository = prepare()
    owner, identity, admitted, committed = capital_owner(repository)
    result = owner.execute(capital_command(amount=Decimal("0"), currency="usd"))
    assert result.snapshot == DeployableCapitalSnapshot(
        snapshot_id="capital-opaque-1",
        amount=Decimal("0"),
        currency="USD",
        as_of=NOW,
        operator_id="founder-1",
        requested_at=NOW + timedelta(minutes=1),
        admitted_at=NOW + timedelta(minutes=2),
    )
    assert result.snapshot.semantics_version == DEPLOYABLE_CAPITAL_SEMANTICS_VERSION
    assert not hasattr(result.snapshot, "reserve")
    assert not hasattr(result.snapshot, "bank_balance")
    assert identity.calls == admitted.calls == committed.calls == 1
    with pytest.raises(FrozenInstanceError):
        result.snapshot.amount = Decimal("1")


@pytest.mark.parametrize(
    "changes",
    (
        {"amount": Decimal("-1")},
        {"amount": 1},
        {"amount": Decimal("NaN")},
        {"currency": "US"},
        {"currency": "12A"},
        {"operator_id": " "},
    ),
)
def test_deployable_capital_rejects_malformed_caller_facts(changes):
    with pytest.raises((TypeError, ValueError)):
        capital_command(**changes)


def test_deployable_capital_exact_replay_and_changed_payload_conflict():
    _, repository = prepare()
    command = capital_command()
    first = capital_owner(repository)[0].execute(command)
    replay = capital_owner(repository, fail=True)[0].execute(command)
    assert replay.replayed is True
    assert replay.snapshot == first.snapshot
    assert replay.receipt == first.receipt
    for changed in (
        replace(command, amount=Decimal("1500001")),
        replace(command, as_of=NOW + timedelta(seconds=1)),
    ):
        with pytest.raises(CapitalInvestmentReplayConflictError):
            capital_owner(repository, fail=True)[0].execute(changed)


def test_facts_have_no_gate_requirement_or_approval_semantics():
    admission, repository = prepare()
    intent = intent_owner(repository)[0].execute(intent_command(admission)).intent
    capital = capital_owner(repository)[0].execute(capital_command()).snapshot
    forbidden = {
        "required_capital", "capital_sufficiency", "gate_state", "profit",
        "roi", "margin", "approved", "invest", "upfront_cost_complete",
    }
    assert forbidden.isdisjoint(intent.__dataclass_fields__)
    assert forbidden.isdisjoint(capital.__dataclass_fields__)


def test_production_identity_suppliers_are_dedicated_uuid4_hex_generators():
    intent_supplier = ProductionIntendedOrderQuantityIdentityGenerator()
    capital_supplier = ProductionDeployableCapitalSnapshotIdentityGenerator()
    values = {intent_supplier(), intent_supplier(), capital_supplier(), capital_supplier()}
    assert len(values) == 4
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values)
    assert intent_supplier.__slots__ == capital_supplier.__slots__ == ()
