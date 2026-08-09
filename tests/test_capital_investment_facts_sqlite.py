from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from app.application.capital_investment import (
    AdmitDeployableCapitalSnapshot,
    AdmitIntendedOrderQuantity,
    CapitalInvestmentReplayConflictError,
)
from app.infrastructure.capital_investment import (
    CapitalInvestmentCommitError,
    CapitalInvestmentIntentHistoryError,
    CapitalInvestmentIntentReceiptError,
    DeployableCapitalSnapshotHistoryError,
    DeployableCapitalSnapshotReceiptError,
    MalformedCapitalInvestmentPersistenceError,
    SQLiteCapitalInvestmentFactsRepository,
)
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository
from test_capital_investment_facts import (
    Calls,
    capital_command,
    intent_command,
)
from test_sourcing_authority_contract import NOW, command as sourcing_command
from test_sourcing_authority_sqlite_persistence import boundary as sourcing_boundary


INTENT_HISTORY = "capital_investment_intent_history"
INTENT_RECEIPTS = "capital_investment_intent_receipts"
CAPITAL_HISTORY = "deployable_capital_snapshot_history"
CAPITAL_RECEIPTS = "deployable_capital_snapshot_receipts"


def seed(path: Path):
    with SQLiteSourcingAuthorityRepository(path) as repository:
        return sourcing_boundary(repository).execute(sourcing_command()).admission


def intent_owner(repository, identity="intent-1", *, fail=False):
    identity_call = Calls(AssertionError("identity called") if fail else identity)
    admitted = Calls(AssertionError("admitted clock called") if fail else NOW + timedelta(minutes=2))
    committed = Calls(AssertionError("committed clock called") if fail else NOW + timedelta(minutes=3))
    return AdmitIntendedOrderQuantity(
        repository,
        intent_id_generator=identity_call,
        admitted_clock=admitted,
        committed_clock=committed,
    ), identity_call, admitted, committed


def capital_owner(repository, identity="capital-1", *, fail=False):
    identity_call = Calls(AssertionError("identity called") if fail else identity)
    admitted = Calls(AssertionError("admitted clock called") if fail else NOW + timedelta(minutes=2))
    committed = Calls(AssertionError("committed clock called") if fail else NOW + timedelta(minutes=3))
    return AdmitDeployableCapitalSnapshot(
        repository,
        snapshot_id_generator=identity_call,
        admitted_clock=admitted,
        committed_clock=committed,
    ), identity_call, admitted, committed


def counts(repository):
    return tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        INTENT_HISTORY, INTENT_RECEIPTS, CAPITAL_HISTORY, CAPITAL_RECEIPTS,
    ))


def test_both_facts_round_trip_restart_and_replay_without_fresh_authority(tmp_path: Path):
    path = tmp_path / "capital.sqlite3"
    admission = seed(path)
    intent_request = intent_command(admission)
    capital_request = capital_command()
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent = intent_owner(repository)[0].execute(intent_request)
        capital = capital_owner(repository)[0].execute(capital_request)
        before = repository._connection.total_changes
        assert repository.get_intent(intent.intent.intent_id) == intent.intent
        assert repository.get_deployable_capital_snapshot(capital.snapshot.snapshot_id) == capital.snapshot
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False

    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent_replay = intent_owner(repository, fail=True)[0].execute(intent_request)
        capital_replay = capital_owner(repository, fail=True)[0].execute(capital_request)
        assert intent_replay.replayed is capital_replay.replayed is True
        assert intent_replay.intent == intent.intent
        assert capital_replay.snapshot == capital.snapshot
        assert counts(repository) == (1, 1, 1, 1)


@pytest.mark.parametrize("table", [INTENT_HISTORY, INTENT_RECEIPTS, CAPITAL_HISTORY, CAPITAL_RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_histories_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    admission = seed(path)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent_owner(repository)[0].execute(intent_command(admission))
        capital_owner(repository)[0].execute(capital_command())
        statement = f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET inserted_at=inserted_at"
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("table", "error"),
    [
        (INTENT_HISTORY, CapitalInvestmentIntentHistoryError),
        (INTENT_RECEIPTS, CapitalInvestmentIntentReceiptError),
        (CAPITAL_HISTORY, DeployableCapitalSnapshotHistoryError),
        (CAPITAL_RECEIPTS, DeployableCapitalSnapshotReceiptError),
    ],
)
def test_insert_failure_rolls_back_without_partial_authority(tmp_path, table, error):
    path = tmp_path / f"rollback-{table}.sqlite3"
    admission = seed(path)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        repository._connection.execute(
            f"CREATE TRIGGER forced_failure BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END"
        )
        owner, request = (
            (intent_owner(repository)[0], intent_command(admission))
            if table.startswith("capital_investment")
            else (capital_owner(repository)[0], capital_command())
        )
        with pytest.raises(error):
            owner.execute(request)
        assert counts(repository) == (0, 0, 0, 0)
        assert repository._connection.in_transaction is False


@pytest.mark.parametrize("authority", ["intent", "capital"])
def test_commit_failure_rolls_back_and_retry_is_possible(tmp_path, monkeypatch, authority):
    path = tmp_path / f"commit-{authority}.sqlite3"
    admission = seed(path)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        original = repository._commit
        monkeypatch.setattr(repository, "_commit", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")))
        owner, request = (
            (intent_owner(repository)[0], intent_command(admission))
            if authority == "intent"
            else (capital_owner(repository)[0], capital_command())
        )
        with pytest.raises(CapitalInvestmentCommitError):
            owner.execute(request)
        assert counts(repository) == (0, 0, 0, 0)
        assert repository._connection.in_transaction is False
        monkeypatch.setattr(repository, "_commit", original)
        owner.execute(request)


@pytest.mark.parametrize("authority", ["intent", "capital"])
def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path, authority):
    path = tmp_path / f"concurrent-{authority}.sqlite3"
    admission = seed(path)
    barrier = Barrier(2)

    def run(database_path, current_admission, current_barrier, identity, changed=False):
        with SQLiteCapitalInvestmentFactsRepository(database_path) as repository:
            current_barrier.wait()
            if authority == "intent":
                request = intent_command(current_admission, quantity=26 if changed else 25)
                return intent_owner(repository, identity)[0].execute(request)
            request = capital_command(amount=Decimal("2") if changed else Decimal("1"))
            return capital_owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(
            lambda value: run(path, admission, barrier, value),
            (f"{authority}-a", f"{authority}-b"),
        ))
    identities = {
        result.intent.intent_id if authority == "intent" else result.snapshot.snapshot_id
        for result in same
    }
    assert len(identities) == 1

    conflict_path = tmp_path / f"conflict-{authority}.sqlite3"
    admission = seed(conflict_path)
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run, conflict_path, admission, barrier, f"{authority}-c", False),
            pool.submit(run, conflict_path, admission, barrier, f"{authority}-d", True),
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except CapitalInvestmentReplayConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1


@pytest.mark.parametrize("authority", ["intent", "capital"])
def test_malformed_payload_fingerprint_and_orphan_receipt_are_rejected(tmp_path, authority):
    path = tmp_path / f"malformed-{authority}.sqlite3"
    admission = seed(path)
    history = INTENT_HISTORY if authority == "intent" else CAPITAL_HISTORY
    receipts = INTENT_RECEIPTS if authority == "intent" else CAPITAL_RECEIPTS
    identity_column = "intent_id" if authority == "intent" else "snapshot_id"
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        result = (
            intent_owner(repository)[0].execute(intent_command(admission))
            if authority == "intent"
            else capital_owner(repository)[0].execute(capital_command())
        )
        identity = result.intent.intent_id if authority == "intent" else result.snapshot.snapshot_id
        repository._connection.execute(f"DROP TRIGGER trg_{history}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {history} WHERE {identity_column}=?", (identity,)
        ).fetchone()
        payload = json.loads(row[0])
        if authority == "intent":
            payload["quantity"] = 0
        else:
            payload["currency"] = "BAD"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        repository._connection.execute(
            f"UPDATE {history} SET payload_json=?,integrity_fingerprint=? WHERE {identity_column}=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest(), identity),
        )
        repository._connection.commit()
        getter = repository.get_intent if authority == "intent" else repository.get_deployable_capital_snapshot
        with pytest.raises(MalformedCapitalInvestmentPersistenceError):
            getter(identity)

    orphan_path = tmp_path / f"orphan-{authority}.sqlite3"
    admission = seed(orphan_path)
    with SQLiteCapitalInvestmentFactsRepository(orphan_path) as repository:
        result = (
            intent_owner(repository)[0].execute(intent_command(admission))
            if authority == "intent"
            else capital_owner(repository)[0].execute(capital_command())
        )
        identity = result.intent.intent_id if authority == "intent" else result.snapshot.snapshot_id
        repository._connection.execute(f"DROP TRIGGER trg_{history}_no_delete")
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute(f"DELETE FROM {history} WHERE {identity_column}=?", (identity,))
        repository._connection.commit()
        getter = repository.get_intent_receipt if authority == "intent" else repository.get_deployable_capital_receipt
        with pytest.raises(MalformedCapitalInvestmentPersistenceError):
            getter(result.receipt.command_id)


@pytest.mark.parametrize(
    ("authority", "mutation"),
    [
        ("intent", lambda value: value.__setitem__("quantity_unit", "")),
        ("intent", lambda value: value["opportunity_identity"].__setitem__("opportunity_id", "other")),
        ("intent", lambda value: value.__setitem__("quote_id", "other-quote")),
        ("intent", lambda value: value.__setitem__("requested_at", "2026-08-07T08:00:00")),
        ("intent", lambda value: value.__setitem__("schema_version", "future")),
        ("capital", lambda value: value.__setitem__("amount", "-1")),
        ("capital", lambda value: value.__setitem__("as_of", "2026-08-07T08:00:00")),
        ("capital", lambda value: value.__setitem__("operator_id", "")),
        ("capital", lambda value: value.__setitem__("semantics_version", "gross-cash")),
        ("capital", lambda value: value.__setitem__("schema_version", "future")),
    ],
)
def test_malformed_authoritative_values_are_never_repaired(tmp_path, authority, mutation):
    path = tmp_path / f"malformed-value-{authority}.sqlite3"
    admission = seed(path)
    history = INTENT_HISTORY if authority == "intent" else CAPITAL_HISTORY
    identity_column = "intent_id" if authority == "intent" else "snapshot_id"
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        result = (
            intent_owner(repository)[0].execute(intent_command(admission))
            if authority == "intent"
            else capital_owner(repository)[0].execute(capital_command())
        )
        identity = result.intent.intent_id if authority == "intent" else result.snapshot.snapshot_id
        repository._connection.execute(f"DROP TRIGGER trg_{history}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {history} WHERE {identity_column}=?", (identity,)
        ).fetchone()
        payload = json.loads(row[0])
        mutation(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        repository._connection.execute(
            f"UPDATE {history} SET payload_json=?,integrity_fingerprint=? WHERE {identity_column}=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest(), identity),
        )
        repository._connection.commit()
        getter = repository.get_intent if authority == "intent" else repository.get_deployable_capital_snapshot
        with pytest.raises(MalformedCapitalInvestmentPersistenceError):
            getter(identity)


@pytest.mark.parametrize("authority", ["intent", "capital"])
def test_integrity_fingerprint_mismatch_is_rejected(tmp_path, authority):
    path = tmp_path / f"integrity-{authority}.sqlite3"
    admission = seed(path)
    history = INTENT_HISTORY if authority == "intent" else CAPITAL_HISTORY
    identity_column = "intent_id" if authority == "intent" else "snapshot_id"
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        result = (
            intent_owner(repository)[0].execute(intent_command(admission))
            if authority == "intent"
            else capital_owner(repository)[0].execute(capital_command())
        )
        identity = result.intent.intent_id if authority == "intent" else result.snapshot.snapshot_id
        repository._connection.execute(f"DROP TRIGGER trg_{history}_no_update")
        repository._connection.execute(
            f"UPDATE {history} SET integrity_fingerprint=? WHERE {identity_column}=?",
            ("0" * 64, identity),
        )
        repository._connection.commit()
        getter = repository.get_intent if authority == "intent" else repository.get_deployable_capital_snapshot
        with pytest.raises(MalformedCapitalInvestmentPersistenceError):
            getter(identity)


def test_missing_exact_sourcing_source_is_rejected_on_reconstruction(tmp_path):
    path = tmp_path / "missing-source.sqlite3"
    admission = seed(path)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        result = intent_owner(repository)[0].execute(intent_command(admission))
        repository._connection.execute(
            "DROP TRIGGER trg_founder_sourcing_admission_history_no_delete"
        )
        repository._connection.commit()
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute(
            "DELETE FROM founder_sourcing_admission_history WHERE admission_id=? AND revision=?",
            (admission.admission_id, admission.revision),
        )
        repository._connection.commit()
        with pytest.raises(MalformedCapitalInvestmentPersistenceError):
            repository.get_intent(result.intent.intent_id)


def test_changed_source_and_as_of_conflict_after_restart(tmp_path):
    path = tmp_path / "changed.sqlite3"
    admission = seed(path)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent_owner(repository)[0].execute(intent_command(admission))
        capital_owner(repository)[0].execute(capital_command())
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        with pytest.raises(CapitalInvestmentReplayConflictError):
            intent_owner(repository, fail=True)[0].execute(intent_command(admission, quote_id="other"))
        with pytest.raises(CapitalInvestmentReplayConflictError):
            capital_owner(repository, fail=True)[0].execute(capital_command(as_of=NOW + timedelta(seconds=1)))


def test_injected_connection_remains_caller_owned(tmp_path):
    path = tmp_path / "injected.sqlite3"
    seed(path)
    connection = sqlite3.connect(path)
    with SQLiteCapitalInvestmentFactsRepository(connection=connection):
        pass
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()
