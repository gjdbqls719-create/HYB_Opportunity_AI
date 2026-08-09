from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import re

import pytest

from app.application.founder_capital_approval import (
    ApproveFounderCapital,
    ApproveFounderCapitalCommand,
    FounderCapitalApprovalAmountError,
    FounderCapitalApprovalCurrencyError,
    FounderCapitalApprovalGateStateError,
    FounderCapitalApprovalPublication,
    FounderCapitalApprovalReplayConflictError,
    FounderCapitalApprovalSourceNotFoundError,
)
from app.domain.capital import (
    CapitalGateBlockingReasonCode,
    CapitalGateRejectionReasonCode,
    CapitalGateState,
)
from app.infrastructure.founder_capital_approval import (
    ProductionFounderCapitalApprovalIdentityGenerator,
)
from test_capital_gate import Calls, evaluate, prepared
from test_sourcing_authority_contract import NOW


class MemoryFounderCapitalApprovalRepository:
    def __init__(self, gate):
        self.gate = gate
        self.results = {}
        self.gate_reads = 0

    def get_capital_gate(self, gate_id):
        self.gate_reads += 1
        return self.gate if self.gate.gate_id == gate_id else None

    def validate_replay(self, command_id, fingerprint):
        value = self.results.get(command_id)
        if value is not None and value.receipt.command_fingerprint != fingerprint:
            raise FounderCapitalApprovalReplayConflictError("payload conflict")
        return value

    def save_approval(self, command, approval, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        value = FounderCapitalApprovalPublication(approval, receipt, False)
        self.results[command.command_id] = value
        return value


def approval_sources():
    gate_repository, opportunity = prepared()
    gate = evaluate(gate_repository, opportunity).assessment
    return MemoryFounderCapitalApprovalRepository(gate), gate


def approval_command(repository, **changes):
    amount = repository.gate.evaluated_facts.planned_acquisition_capital
    values = {
        "command_id": "founder-capital-approval-command-1",
        "capital_gate_id": repository.gate.gate_id,
        "founder_id": "founder-1",
        "approved_capital": amount,
        "currency": repository.gate.evaluated_facts.requirement_currency,
        "requested_at": NOW + timedelta(minutes=20),
        "approved_at": NOW + timedelta(minutes=21),
    }
    values.update(changes)
    return ApproveFounderCapitalCommand(**values)


def approval_owner(repository, *, identity="approval-1", fail=False):
    identity_call = Calls(AssertionError("identity called on replay") if fail else identity)
    admitted = Calls(
        AssertionError("admitted clock called on replay")
        if fail
        else NOW + timedelta(minutes=22)
    )
    committed = Calls(
        AssertionError("committed clock called on replay")
        if fail
        else NOW + timedelta(minutes=23)
    )
    return (
        ApproveFounderCapital(
            repository,
            approval_id_generator=identity_call,
            admitted_clock=admitted,
            committed_clock=committed,
        ),
        identity_call,
        admitted,
        committed,
    )


def test_exact_gate_pass_creates_immutable_human_approval_without_execution():
    repository, gate = approval_sources()
    result = approval_owner(repository)[0].execute(approval_command(repository))
    approval = result.approval
    assert approval.opportunity_identity == gate.source_manifest.opportunity_identity
    assert approval.capital_gate_id == gate.gate_id
    assert approval.capital_gate_policy_name == gate.policy_name
    assert approval.capital_gate_policy_version == gate.policy_version
    assert approval.capital_requirement_id == gate.source_manifest.capital_requirement_id
    assert approval.deployable_capital_snapshot_id == gate.source_manifest.deployable_capital_snapshot_id
    assert approval.intended_order_quantity_id == gate.source_manifest.intended_order_quantity_id
    assert approval.capital_gate_evaluated_at == gate.evaluated_at
    assert approval.approved_capital == gate.evaluated_facts.planned_acquisition_capital
    assert approval.currency == gate.evaluated_facts.requirement_currency
    assert approval.founder_id == "founder-1"
    assert not hasattr(approval, "purchase")
    assert not hasattr(approval, "transferred")
    assert not hasattr(approval, "founder_decision")
    with pytest.raises(FrozenInstanceError):
        approval.currency = "USD"


@pytest.mark.parametrize("state", [CapitalGateState.REJECTED, CapitalGateState.BLOCKED])
def test_non_pass_gate_cannot_be_approved(state):
    repository, _ = approval_sources()
    if state is CapitalGateState.REJECTED:
        repository.gate = replace(
            repository.gate,
            state=state,
            rejection_reasons=(CapitalGateRejectionReasonCode.INSUFFICIENT_DEPLOYABLE_CAPITAL,),
        )
    else:
        repository.gate = replace(
            repository.gate,
            state=state,
            blocking_reasons=(CapitalGateBlockingReasonCode.CURRENCY_MISMATCH,),
        )
    use_case, identity, admitted, committed = approval_owner(repository)
    with pytest.raises(FounderCapitalApprovalGateStateError):
        use_case.execute(approval_command(repository))
    assert identity.calls == admitted.calls == committed.calls == 0
    assert repository.results == {}


def test_missing_exact_gate_is_explicit_source_error():
    repository, _ = approval_sources()
    use_case, identity, admitted, committed = approval_owner(repository)
    with pytest.raises(FounderCapitalApprovalSourceNotFoundError):
        use_case.execute(approval_command(repository, capital_gate_id="missing"))
    assert identity.calls == admitted.calls == committed.calls == 0


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1")])
def test_non_positive_amount_is_rejected_by_command(amount):
    repository, _ = approval_sources()
    with pytest.raises(ValueError):
        approval_command(repository, approved_capital=amount)


@pytest.mark.parametrize("offset", [Decimal("-0.01"), Decimal("0.01")])
def test_partial_or_excess_approval_is_rejected(offset):
    repository, gate = approval_sources()
    required = gate.evaluated_facts.planned_acquisition_capital
    with pytest.raises(FounderCapitalApprovalAmountError):
        approval_owner(repository)[0].execute(
            approval_command(repository, approved_capital=required + offset)
        )
    assert repository.results == {}


def test_approval_currency_must_equal_exact_gate_currency():
    repository, _ = approval_sources()
    with pytest.raises(FounderCapitalApprovalCurrencyError):
        approval_owner(repository)[0].execute(
            approval_command(repository, currency="USD")
        )


def test_gate_pass_does_not_auto_create_approval():
    repository, gate = approval_sources()
    assert gate.state is CapitalGateState.PASS
    assert repository.results == {}


def test_exact_replay_skips_gate_read_identity_and_clocks_and_changed_payload_conflicts():
    repository, _ = approval_sources()
    request = approval_command(repository)
    first = approval_owner(repository)[0].execute(request)
    reads = repository.gate_reads
    replay = approval_owner(repository, fail=True)[0].execute(request)
    assert replay.replayed is True
    assert replay.approval == first.approval
    assert replay.receipt == first.receipt
    assert repository.gate_reads == reads
    for changed in (
        replace(request, capital_gate_id="other"),
        replace(request, approved_capital=request.approved_capital + Decimal("1")),
        replace(request, founder_id="founder-2"),
        replace(request, currency="USD"),
        replace(request, approved_at=request.approved_at + timedelta(seconds=1)),
    ):
        with pytest.raises(FounderCapitalApprovalReplayConflictError):
            approval_owner(repository, fail=True)[0].execute(changed)


def test_production_approval_identity_supplier_is_stateless_uuid4_hex():
    supplier = ProductionFounderCapitalApprovalIdentityGenerator()
    values = {supplier() for _ in range(32)}
    assert len(values) == 32
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
