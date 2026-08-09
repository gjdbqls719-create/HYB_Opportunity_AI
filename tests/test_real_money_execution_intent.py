from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.real_money_execution_intent import (
    EvaluateRealMoneyExecutionIntent,
    EvaluateRealMoneyExecutionIntentCommand,
    RealMoneyExecutionIntentPublication,
    RealMoneyExecutionIntentReplayConflictError,
    RealMoneyExecutionIntentSourceNotFoundError,
)
from app.domain.capital import (
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    DeployableCapitalSnapshot,
    RealMoneyExecutionIntentBlockingReasonCode,
    RealMoneyExecutionIntentState,
)
from app.infrastructure.real_money_execution_intent import (
    ProductionRealMoneyExecutionIntentIdentityGenerator,
)
from test_capital_gate import Calls, evaluate as evaluate_gate, prepared
from test_founder_capital_approval import (
    MemoryFounderCapitalApprovalRepository,
    approval_command,
    approval_owner,
)
from test_sourcing_authority_contract import NOW


class MemoryRealMoneyExecutionIntentRepository:
    def __init__(self, approval, gate_repository, current_capital):
        self.approval = approval
        self.gate = gate_repository.gate
        self.requirement = gate_repository.requirement
        self.intended = gate_repository.intent
        self.admission = gate_repository.admission
        self.current_capital = current_capital
        self.results = {}
        self.intents = {}
        self.action_fingerprints = {}
        self.source_reads = 0

    def _read(self, value, identity, attribute):
        self.source_reads += 1
        return value if getattr(value, attribute) == identity else None

    def get_founder_capital_approval(self, approval_id):
        return self._read(self.approval, approval_id, "approval_id")

    def get_capital_gate(self, gate_id):
        return self._read(self.gate, gate_id, "gate_id")

    def get_capital_requirement(self, requirement_id):
        return self._read(self.requirement, requirement_id, "requirement_id")

    def get_intended_order_quantity(self, intent_id):
        return self._read(self.intended, intent_id, "intent_id")

    def get_sourcing_admission(self, admission_id, revision):
        self.source_reads += 1
        if self.admission.admission_id == admission_id and self.admission.revision == revision:
            return self.admission
        return None

    def get_deployable_capital_snapshot(self, snapshot_id):
        return self._read(self.current_capital, snapshot_id, "snapshot_id")

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is not None and result.receipt.command_fingerprint != fingerprint:
            raise RealMoneyExecutionIntentReplayConflictError("payload conflict")
        return result

    def find_ready_alias(self, approval_id, action_fingerprint):
        for intent_id, current in self.intents.items():
            if (
                current.state
                is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
                and current.source_manifest.founder_capital_approval_id == approval_id
                and self.action_fingerprints[intent_id] == action_fingerprint
            ):
                return current
        return None

    def save_alias(self, command, intent, receipt):
        result = RealMoneyExecutionIntentPublication(intent, receipt, True)
        self.results[command.command_id] = result
        return result

    def save_intent(self, command, intent, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        result = RealMoneyExecutionIntentPublication(intent, receipt, False)
        self.results[command.command_id] = result
        self.intents[intent.intent_id] = intent
        self.action_fingerprints[intent.intent_id] = command.action_fingerprint
        return result


def sources():
    gate_repository, opportunity = prepared()
    gate = evaluate_gate(gate_repository, opportunity).assessment
    approval_repository = MemoryFounderCapitalApprovalRepository(gate)
    approval = approval_owner(approval_repository)[0].execute(
        approval_command(approval_repository)
    ).approval
    capital = DeployableCapitalSnapshot(
        "current-capital-1",
        approval.approved_capital,
        approval.currency,
        NOW + timedelta(days=1),
        approval.founder_id,
        NOW + timedelta(days=1),
        NOW + timedelta(days=1, minutes=1),
    )
    gate_repository.gate = gate
    return MemoryRealMoneyExecutionIntentRepository(
        approval, gate_repository, capital
    )


def command(repository, **changes):
    approval = repository.approval
    quote = repository.admission.quote_revision
    intended = repository.intended
    values = {
        "command_id": "execution-intent-command-1",
        "founder_capital_approval_id": approval.approval_id,
        "quote_id": quote.quote_id,
        "quote_revision": quote.revision,
        "current_deployable_capital_snapshot_id": repository.current_capital.snapshot_id,
        "execution_quantity": intended.quantity,
        "execution_quantity_unit": intended.quantity_unit,
        "planned_execution_amount": approval.approved_capital,
        "currency": approval.currency,
        "founder_id": approval.founder_id,
        "requested_at": NOW + timedelta(days=2),
        "confirmed_at": NOW + timedelta(days=2, minutes=1),
        "current_execution_confirmed": True,
        "policy_name": "domestic-commerce-real-money-execution-safety",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    return EvaluateRealMoneyExecutionIntentCommand(**values)


def owner(repository, identity="execution-intent-1", *, fail=False, evaluated_at=None):
    identity_call = Calls(AssertionError("identity called on replay") if fail else identity)
    evaluated = Calls(
        AssertionError("evaluated clock called on replay")
        if fail
        else evaluated_at or NOW + timedelta(days=2, minutes=2)
    )
    committed = Calls(
        AssertionError("committed clock called on replay")
        if fail
        else NOW + timedelta(days=2, minutes=3)
    )
    return (
        EvaluateRealMoneyExecutionIntent(
            repository,
            execution_intent_id_generator=identity_call,
            evaluated_clock=evaluated,
            committed_clock=committed,
        ),
        identity_call,
        evaluated,
        committed,
    )


def evaluate(repository=None, request=None, **owner_changes):
    repository = repository or sources()
    request = request or command(repository)
    return owner(repository, **owner_changes)[0].execute(request)


def test_exact_safe_action_creates_immutable_ready_intent_and_exact_manifest():
    repository = sources()
    result = evaluate(repository)
    intent = result.intent
    manifest = intent.source_manifest
    assert intent.state is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
    assert intent.blocking_reasons == ()
    assert manifest.opportunity_identity == repository.approval.opportunity_identity
    assert manifest.founder_capital_approval_id == repository.approval.approval_id
    assert manifest.capital_gate_id == repository.gate.gate_id
    assert manifest.capital_requirement_id == repository.requirement.requirement_id
    assert manifest.intended_order_quantity_id == repository.intended.intent_id
    assert manifest.sourcing_admission_id == repository.admission.admission_id
    assert manifest.quote_id == repository.admission.quote_revision.quote_id
    assert manifest.current_deployable_capital_snapshot_id == repository.current_capital.snapshot_id
    assert manifest.planned_execution_amount == repository.approval.approved_capital
    assert manifest.current_execution_confirmed is True
    assert not hasattr(intent, "purchase")
    assert not hasattr(intent, "payment")
    with pytest.raises(FrozenInstanceError):
        intent.state = RealMoneyExecutionIntentState.BLOCKED


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"quote_id": "other"}, RealMoneyExecutionIntentBlockingReasonCode.QUOTE_REVISION_MISMATCH),
        ({"planned_execution_amount": Decimal("1")}, RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_AMOUNT_MISMATCH),
        ({"execution_quantity": 1}, RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_QUANTITY_MISMATCH),
        ({"execution_quantity_unit": "cases"}, RealMoneyExecutionIntentBlockingReasonCode.EXECUTION_UNIT_MISMATCH),
        ({"currency": "USD"}, RealMoneyExecutionIntentBlockingReasonCode.CURRENCY_MISMATCH),
        ({"founder_id": "other-founder"}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_EXECUTION_CONFIRMATION_MISMATCH),
        ({"current_execution_confirmed": False}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_EXECUTION_CONFIRMATION_MISMATCH),
    ],
)
def test_structurally_valid_unsafe_actions_are_blocked(change, reason):
    repository = sources()
    result = evaluate(repository, command(repository, **change)).intent
    assert result.state is RealMoneyExecutionIntentState.BLOCKED
    assert reason in result.blocking_reasons
    assert result.blocking_reasons == tuple(
        sorted(result.blocking_reasons, key=lambda value: value.order)
    )


def test_quote_missing_or_expired_validity_is_blocked_without_latest_substitution():
    repository = sources()
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(repository.admission.quote_revision, valid_until=None),
    )
    missing = evaluate(repository).intent
    assert missing.blocking_reasons == (
        RealMoneyExecutionIntentBlockingReasonCode.QUOTE_VALIDITY_MISSING,
    )

    repository = sources()
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(
            repository.admission.quote_revision,
            valid_until=NOW + timedelta(days=2, minutes=2),
        ),
    )
    expired = evaluate(repository).intent
    assert expired.blocking_reasons == (
        RealMoneyExecutionIntentBlockingReasonCode.QUOTE_EXPIRED,
    )


@pytest.mark.parametrize(
    ("capital_change", "reason"),
    [
        ({"snapshot_id": "deployable-1"}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_SNAPSHOT_INVALID),
        ({"amount": Decimal("0")}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_INSUFFICIENT),
        ({"currency": "USD"}, RealMoneyExecutionIntentBlockingReasonCode.CURRENCY_MISMATCH),
        ({"operator_id": "other-founder"}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_SNAPSHOT_INVALID),
        ({"as_of": NOW}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_SNAPSHOT_INVALID),
        ({"as_of": NOW + timedelta(days=3)}, RealMoneyExecutionIntentBlockingReasonCode.CURRENT_CAPITAL_SNAPSHOT_INVALID),
    ],
)
def test_current_capital_is_exact_post_approval_reserve_adjusted_fact(capital_change, reason):
    repository = sources()
    repository.current_capital = replace(repository.current_capital, **capital_change)
    request = command(
        repository,
        current_deployable_capital_snapshot_id=repository.current_capital.snapshot_id,
    )
    result = evaluate(repository, request).intent
    assert reason in result.blocking_reasons
    assert repository.current_capital.semantics_version == DEPLOYABLE_CAPITAL_SEMANTICS_VERSION


def test_missing_exact_source_is_explicit_error_before_identity_and_clocks():
    repository = sources()
    repository.approval = replace(repository.approval, approval_id="other")
    use_case, identity, evaluated, committed = owner(repository)
    with pytest.raises(RealMoneyExecutionIntentSourceNotFoundError):
        use_case.execute(command(repository, founder_capital_approval_id="missing"))
    assert identity.calls == evaluated.calls == committed.calls == 0


def test_exact_replay_skips_all_source_reads_identity_clocks_and_time_reevaluation():
    repository = sources()
    request = command(repository)
    first = evaluate(repository, request)
    reads = repository.source_reads
    replay = owner(repository, fail=True)[0].execute(request)
    assert replay.replayed is True
    assert replay.intent == first.intent
    assert replay.receipt == first.receipt
    assert repository.source_reads == reads
    changed = replace(request, confirmed_at=request.confirmed_at + timedelta(seconds=1))
    with pytest.raises(RealMoneyExecutionIntentReplayConflictError):
        owner(repository, fail=True)[0].execute(changed)


def test_execution_intent_never_reruns_gate_market_or_economics():
    repository = sources()
    evaluate(repository)
    assert not hasattr(repository, "evaluate_gate")
    assert not hasattr(repository, "evaluate_market")
    assert not hasattr(repository, "calculate_economics")


def test_production_execution_intent_identity_is_stateless_uuid4_hex():
    import re

    supplier = ProductionRealMoneyExecutionIntentIdentityGenerator()
    values = {supplier() for _ in range(32)}
    assert len(values) == 32
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
