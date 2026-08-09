from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.capital_investment import AdmitDeployableCapitalSnapshot
from app.application.real_money_execution_intent import (
    EvaluateRealMoneyExecutionIntent,
    RealMoneyExecutionIntentReadyConflictError,
    RealMoneyExecutionIntentReplayConflictError,
)
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.founder_capital_approval import SQLiteFounderCapitalApprovalRepository
from app.infrastructure.real_money_execution_intent import (
    MalformedRealMoneyExecutionIntentPersistenceError,
    RealMoneyExecutionIntentCommitError,
    RealMoneyExecutionIntentHistoryError,
    RealMoneyExecutionIntentReceiptError,
    SQLiteRealMoneyExecutionIntentRepository,
)
from test_capital_gate import Calls
from test_capital_investment_facts import capital_command
from test_capital_gate_sqlite import gate_owner, seed as seed_gate_sources
from test_founder_capital_approval import approval_command
from test_founder_capital_approval_sqlite import owner as approval_owner
from test_sourcing_authority_contract import NOW


HISTORY = "real_money_execution_intent_history"
RECEIPTS = "real_money_execution_intent_receipts"


def seed(path):
    opportunity, readiness, requirement, historical_capital = seed_gate_sources(path)
    values = type(
        "Values",
        (),
        {"readiness": readiness, "requirement": requirement, "deployable": historical_capital},
    )()
    from app.infrastructure.capital_gate import SQLiteCapitalGateRepository
    from test_capital_gate import command as gate_command

    with SQLiteCapitalGateRepository(path) as repository:
        gate = gate_owner(repository)[0].execute(gate_command(values, opportunity)).assessment
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        approval = approval_owner(repository)[0].execute(
            approval_command(type("Values", (), {"gate": gate})())
        ).approval
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        current_capital = AdmitDeployableCapitalSnapshot(
            repository,
            snapshot_id_generator=lambda: "current-capital-1",
            admitted_clock=lambda: NOW + timedelta(days=4, minutes=1),
            committed_clock=lambda: NOW + timedelta(days=4, minutes=2),
        ).execute(
            capital_command(
                command_id="current-capital-command-1",
                amount=approval.approved_capital,
                currency=approval.currency,
                as_of=NOW + timedelta(days=4),
                operator_id=approval.founder_id,
                requested_at=NOW + timedelta(days=4),
            )
        ).snapshot
    return approval, current_capital


def sqlite_command(repository, approval, current_capital, **changes):
    gate = repository.get_capital_gate(approval.capital_gate_id)
    requirement = repository.get_capital_requirement(approval.capital_requirement_id)
    values = {
        "command_id": "execution-intent-command-1",
        "founder_capital_approval_id": approval.approval_id,
        "quote_id": gate.source_manifest.quote_id,
        "quote_revision": gate.source_manifest.quote_revision,
        "current_deployable_capital_snapshot_id": current_capital.snapshot_id,
        "execution_quantity": requirement.quantity,
        "execution_quantity_unit": requirement.quantity_unit,
        "planned_execution_amount": approval.approved_capital,
        "currency": approval.currency,
        "founder_id": approval.founder_id,
        "requested_at": NOW + timedelta(days=5),
        "confirmed_at": NOW + timedelta(days=5, minutes=1),
        "current_execution_confirmed": True,
        "policy_name": "domestic-commerce-real-money-execution-safety",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    from app.application.real_money_execution_intent import EvaluateRealMoneyExecutionIntentCommand

    return EvaluateRealMoneyExecutionIntentCommand(**values)


def owner(repository, identity="execution-intent-1", *, fail=False, alias=False):
    identity_call = Calls(
        AssertionError("identity called on replay/alias")
        if fail or alias
        else identity
    )
    evaluated = Calls(
        AssertionError("evaluated called on replay/alias")
        if fail or alias
        else NOW + timedelta(days=5, minutes=2)
    )
    committed = Calls(
        AssertionError("committed called on replay")
        if fail
        else NOW + timedelta(days=5, minutes=3)
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


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_restart_replay_and_read_path_are_exact(tmp_path):
    path = tmp_path / "execution.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        request = sqlite_command(repository, approval, capital)
        first = owner(repository)[0].execute(request)
        before = repository._connection.total_changes
        assert repository.get_intent(first.intent.intent_id) == first.intent
        assert repository.get_receipt(request.command_id) == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        replay = owner(repository, fail=True)[0].execute(request)
        assert replay.replayed is True
        assert replay.intent == first.intent
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_blocked_action_is_authoritative_and_round_trips(tmp_path):
    path = tmp_path / "blocked.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        request = sqlite_command(repository, approval, capital, quote_id="different-quote")
        first = owner(repository)[0].execute(request)
        assert first.intent.state.value == "blocked"
        assert [reason.value for reason in first.intent.blocking_reasons] == [
            "quote_revision_mismatch"
        ]
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        replay = owner(repository, fail=True)[0].execute(request)
        assert replay.intent == first.intent
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        owner(repository)[0].execute(sqlite_command(repository, approval, capital))
        statement = f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET inserted_at=inserted_at"
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("history", RealMoneyExecutionIntentHistoryError),
        ("receipt", RealMoneyExecutionIntentReceiptError),
        ("commit", RealMoneyExecutionIntentCommitError),
    ],
)
def test_transaction_failures_rollback_and_retry(tmp_path, monkeypatch, failure, error):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        request = sqlite_command(repository, approval, capital)
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
        else:
            original = repository._commit
            monkeypatch.setattr(
                repository,
                "_commit",
                lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
            )
        with pytest.raises(error):
            owner(repository)[0].execute(request)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        if failure == "commit":
            monkeypatch.setattr(repository, "_commit", original)
            owner(repository)[0].execute(request)


def test_same_action_aliases_and_different_ready_action_conflicts(tmp_path):
    path = tmp_path / "cardinality.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        first_request = sqlite_command(repository, approval, capital)
        first = owner(repository)[0].execute(first_request)
        alias_request = replace(
            first_request,
            command_id="execution-intent-command-alias",
            requested_at=first_request.requested_at + timedelta(seconds=1),
        )
        alias_owner, identity, evaluated, committed = owner(repository, alias=True)
        alias = alias_owner.execute(alias_request)
        assert alias.intent == first.intent
        assert alias.replayed is True
        assert identity.calls == evaluated.calls == 0
        assert committed.calls == 1
        assert counts(repository) == (1, 2)
        changed = replace(
            first_request,
            command_id="execution-intent-command-changed",
            confirmed_at=first_request.confirmed_at + timedelta(seconds=1),
        )
        with pytest.raises(RealMoneyExecutionIntentReadyConflictError):
            owner(repository, identity="discarded-conflict-id")[0].execute(changed)
        assert counts(repository) == (1, 2)


def test_concurrency_converges_and_enforces_one_ready_per_approval(tmp_path):
    path = tmp_path / "concurrency.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        base = sqlite_command(repository, approval, capital)
    barrier = Barrier(2)

    def run(identity, request):
        with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: run(value, base), ("intent-a", "intent-b")))
    assert len({result.intent.intent_id for result in results}) == 1

    alias_path = tmp_path / "concurrency-alias.sqlite3"
    approval, capital = seed(alias_path)
    with SQLiteRealMoneyExecutionIntentRepository(alias_path) as repository:
        base = sqlite_command(repository, approval, capital)
    alias_requests = (
        base,
        replace(
            base,
            command_id="execution-intent-command-alias",
            requested_at=base.requested_at + timedelta(seconds=1),
        ),
    )
    barrier = Barrier(2)
    path = alias_path
    with ThreadPoolExecutor(max_workers=2) as pool:
        alias_results = list(
            pool.map(
                lambda values: run(values[0], values[1]),
                (("intent-a", alias_requests[0]), ("intent-b", alias_requests[1])),
            )
        )
    assert len({result.intent.intent_id for result in alias_results}) == 1
    with SQLiteRealMoneyExecutionIntentRepository(alias_path) as repository:
        assert counts(repository) == (1, 2)

    replay_conflict_path = tmp_path / "concurrency-replay-conflict.sqlite3"
    approval, capital = seed(replay_conflict_path)
    with SQLiteRealMoneyExecutionIntentRepository(replay_conflict_path) as repository:
        base = sqlite_command(repository, approval, capital)
    same_command_changed = (
        base,
        replace(base, confirmed_at=base.confirmed_at + timedelta(seconds=1)),
    )
    barrier = Barrier(2)
    path = replay_conflict_path
    replay_outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run, f"intent-{index}", same_command_changed[index])
            for index in range(2)
        ]
        for future in futures:
            try:
                replay_outcomes.append(future.result())
            except RealMoneyExecutionIntentReplayConflictError:
                replay_outcomes.append("conflict")
    assert replay_outcomes.count("conflict") == 1

    changed_path = tmp_path / "concurrency-changed.sqlite3"
    approval, capital = seed(changed_path)
    with SQLiteRealMoneyExecutionIntentRepository(changed_path) as repository:
        base = sqlite_command(repository, approval, capital)
    requests = (
        base,
        replace(
            base,
            command_id="execution-intent-command-2",
            confirmed_at=base.confirmed_at + timedelta(seconds=1),
        ),
    )
    barrier = Barrier(2)
    path = changed_path
    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, f"intent-{index}", requests[index]) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except RealMoneyExecutionIntentReadyConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1


@pytest.mark.parametrize(
    "corruption",
    ["state", "reasons", "amount", "manifest", "schema", "fingerprint", "orphan"],
)
def test_malformed_persistence_is_rejected(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    approval, capital = seed(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        result = owner(repository)[0].execute(sqlite_command(repository, approval, capital))
        if corruption == "orphan":
            repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
            repository._connection.execute("PRAGMA foreign_keys=OFF")
            repository._connection.execute(f"UPDATE {RECEIPTS} SET intent_id='missing'")
            repository._connection.commit()
            repository._connection.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(MalformedRealMoneyExecutionIntentPersistenceError):
                repository.get_receipt(result.receipt.command_id)
            return
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE intent_id=?",
            (result.intent.intent_id,),
        ).fetchone()
        payload = json.loads(row[0])
        if corruption == "state":
            payload["state"] = "invalid"
        elif corruption == "reasons":
            payload["blocking_reasons"] = ["quote_expired"]
        elif corruption == "amount":
            payload["source_manifest"]["planned_execution_amount"] = "-1"
        elif corruption == "manifest":
            payload["source_manifest"]["quote_id"] = "other"
        elif corruption == "schema":
            payload["schema_version"] = "unsupported"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        integrity = "0" * 64 if corruption == "fingerprint" else hashlib.sha256(encoded.encode()).hexdigest()
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=? WHERE intent_id=?",
            (encoded, integrity, result.intent.intent_id),
        )
        repository._connection.commit()
        with pytest.raises(MalformedRealMoneyExecutionIntentPersistenceError):
            repository.get_intent(result.intent.intent_id)
