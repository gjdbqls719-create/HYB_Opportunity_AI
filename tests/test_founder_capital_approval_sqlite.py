from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.founder_capital_approval import (
    ApproveFounderCapital,
    FounderCapitalApprovalReplayConflictError,
)
from app.infrastructure.capital_gate import SQLiteCapitalGateRepository
from app.infrastructure.founder_capital_approval import (
    FounderCapitalApprovalCommitError,
    FounderCapitalApprovalHistoryError,
    FounderCapitalApprovalReceiptError,
    MalformedFounderCapitalApprovalPersistenceError,
    SQLiteFounderCapitalApprovalRepository,
)
from test_capital_gate import command as gate_command
from test_capital_gate_sqlite import gate_owner, seed as seed_gate_sources
from test_founder_capital_approval import Calls, approval_command
from test_sourcing_authority_contract import NOW


HISTORY = "founder_capital_approval_history"
RECEIPTS = "founder_capital_approval_receipts"


def seed(path):
    opportunity, readiness, requirement, deployable = seed_gate_sources(path)
    values = type(
        "Values",
        (),
        {"readiness": readiness, "requirement": requirement, "deployable": deployable},
    )()
    with SQLiteCapitalGateRepository(path) as repository:
        gate = gate_owner(repository)[0].execute(
            gate_command(values, opportunity)
        ).assessment
    return gate


def owner(repository, identity="approval-1", *, fail=False):
    identity_call = Calls(AssertionError("identity called on replay") if fail else identity)
    admitted = Calls(
        AssertionError("admitted clock called on replay")
        if fail
        else NOW + timedelta(days=3)
    )
    committed = Calls(
        AssertionError("committed clock called on replay")
        if fail
        else NOW + timedelta(days=3, minutes=1)
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


def values(gate):
    return type("Values", (), {"gate": gate})()


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_restart_replay_and_read_path_are_exact(tmp_path):
    path = tmp_path / "approval.sqlite3"
    gate = seed(path)
    request = approval_command(values(gate))
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        first = owner(repository)[0].execute(request)
        before = repository._connection.total_changes
        assert repository.get_approval(first.approval.approval_id) == first.approval
        assert repository.get_receipt(request.command_id) == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        replay = owner(repository, fail=True)[0].execute(request)
        assert replay.replayed is True
        assert replay.approval == first.approval
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_approval_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    gate = seed(path)
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        owner(repository)[0].execute(approval_command(values(gate)))
        statement = (
            f"DELETE FROM {table}"
            if operation == "DELETE"
            else f"UPDATE {table} SET inserted_at=inserted_at"
        )
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("history", FounderCapitalApprovalHistoryError),
        ("receipt", FounderCapitalApprovalReceiptError),
        ("commit", FounderCapitalApprovalCommitError),
    ],
)
def test_transaction_failures_rollback_and_retry(tmp_path, monkeypatch, failure, error):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    gate = seed(path)
    request = approval_command(values(gate))
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
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


def test_concurrent_same_and_changed_commands_converge(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    gate = seed(path)
    request = approval_command(values(gate))
    barrier = Barrier(2)

    def run(identity, current_request=request):
        with SQLiteFounderCapitalApprovalRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity)[0].execute(current_request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("approval-a", "approval-b")))
    assert len({value.approval.approval_id for value in results}) == 1

    changed_path = tmp_path / "changed.sqlite3"
    gate = seed(changed_path)
    requests = (
        approval_command(values(gate)),
        approval_command(values(gate), approved_at=NOW + timedelta(days=4)),
    )
    path = changed_path
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, f"approval-{index}", requests[index]) for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except FounderCapitalApprovalReplayConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1


@pytest.mark.parametrize(
    "corruption", ["amount", "currency", "gate", "schema", "fingerprint", "orphan"]
)
def test_malformed_persistence_is_rejected(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    gate = seed(path)
    with SQLiteFounderCapitalApprovalRepository(path) as repository:
        result = owner(repository)[0].execute(approval_command(values(gate)))
        if corruption == "orphan":
            repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
            repository._connection.execute("PRAGMA foreign_keys=OFF")
            repository._connection.execute(
                f"UPDATE {RECEIPTS} SET approval_id='missing'"
            )
            repository._connection.commit()
            repository._connection.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(MalformedFounderCapitalApprovalPersistenceError):
                repository.get_receipt(result.receipt.command_id)
            return
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE approval_id=?",
            (result.approval.approval_id,),
        ).fetchone()
        payload = json.loads(row[0])
        if corruption == "amount":
            payload["approved_capital"] = "0"
        elif corruption == "currency":
            payload["currency"] = "USD"
        elif corruption == "gate":
            payload["capital_gate_id"] = "missing"
        elif corruption == "schema":
            payload["schema_version"] = "unsupported"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        integrity = (
            "0" * 64
            if corruption == "fingerprint"
            else hashlib.sha256(encoded.encode()).hexdigest()
        )
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=? WHERE approval_id=?",
            (encoded, integrity, result.approval.approval_id),
        )
        repository._connection.commit()
        with pytest.raises(MalformedFounderCapitalApprovalPersistenceError):
            repository.get_approval(result.approval.approval_id)
