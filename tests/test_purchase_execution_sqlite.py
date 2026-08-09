from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Barrier

import pytest

from app.application.purchase_execution import (
    PurchaseExecutionCardinalityConflictError,
    PurchaseExecutionPublication,
    PurchaseExecutionReplayConflictError,
    RecordPurchaseExecution,
    RecordPurchaseExecutionCommand,
)
from app.domain.capital import PurchaseExecutionEvidenceReference
from app.infrastructure.purchase_execution import (
    MalformedPurchaseExecutionPersistenceError,
    PurchaseExecutionCommitError,
    PurchaseExecutionHistoryError,
    PurchaseExecutionReceiptError,
    SQLitePurchaseExecutionRepository,
)
from app.infrastructure.real_money_execution_intent import (
    SQLiteRealMoneyExecutionIntentRepository,
)
from test_capital_gate import Calls
from test_real_money_execution_intent_sqlite import (
    owner as execution_owner,
    seed as seed_execution_sources,
    sqlite_command as execution_command,
)
from test_sourcing_authority_contract import NOW


HISTORY = "purchase_execution_record_history"
RECEIPTS = "purchase_execution_record_receipts"


def seed(path):
    approval, capital = seed_execution_sources(path)
    with SQLiteRealMoneyExecutionIntentRepository(path) as repository:
        intent = execution_owner(repository)[0].execute(
            execution_command(repository, approval, capital)
        ).intent
    return intent


def command(intent, **changes):
    source = intent.source_manifest
    values = {
        "command_id": "purchase-execution-command-1",
        "real_money_execution_intent_id": intent.intent_id,
        "quote_id": source.quote_id,
        "quote_revision": source.quote_revision,
        "actual_quantity": source.execution_quantity,
        "actual_quantity_unit": source.execution_quantity_unit,
        "actual_total_committed_amount": source.planned_execution_amount,
        "currency": source.currency,
        "external_order_reference": "opaque-order-001",
        "founder_id": source.founder_id,
        "executed_at": intent.evaluated_at + timedelta(minutes=1),
        "evidence_references": (
            PurchaseExecutionEvidenceReference(
                "artifact://purchase/001", intent.evaluated_at + timedelta(minutes=1)
            ),
        ),
        "requested_at": intent.evaluated_at + timedelta(minutes=2),
    }
    values.update(changes)
    return RecordPurchaseExecutionCommand(**values)


def owner(repository, identity="purchase-record-1", *, fail=False, alias=False):
    identity_call = Calls(
        AssertionError("identity called on replay/alias")
        if fail or alias
        else identity
    )
    admitted = Calls(
        AssertionError("admitted called on replay/alias")
        if fail or alias
        else NOW + timedelta(days=6, minutes=3)
    )
    committed = Calls(
        AssertionError("committed called on replay")
        if fail
        else NOW + timedelta(days=6, minutes=4)
    )
    return RecordPurchaseExecution(
        repository,
        record_id_generator=identity_call,
        admitted_clock=admitted,
        committed_clock=committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_file_restart_replay_and_read_path_are_exact(tmp_path):
    path = tmp_path / "purchase.sqlite3"
    intent = seed(path)
    request = command(intent)
    with SQLitePurchaseExecutionRepository(path) as repository:
        first = owner(repository).execute(request)
        before = repository._connection.total_changes
        assert repository.get_record(first.record.record_id) == first.record
        assert repository.validate_replay(request.command_id, request.fingerprint).receipt == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
    with SQLitePurchaseExecutionRepository(path) as repository:
        replay = owner(repository, fail=True).execute(request)
        assert replay.replayed is True
        assert replay.record == first.record
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    intent = seed(path)
    with SQLitePurchaseExecutionRepository(path) as repository:
        owner(repository).execute(command(intent))
        statement = (
            f"DELETE FROM {table}"
            if operation == "DELETE"
            else f"UPDATE {table} SET inserted_at=inserted_at"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    (
        ("history", PurchaseExecutionHistoryError),
        ("receipt", PurchaseExecutionReceiptError),
        ("commit", PurchaseExecutionCommitError),
    ),
)
def test_transaction_failures_rollback_leave_ready_unchanged_and_retry(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    intent = seed(path)
    with SQLitePurchaseExecutionRepository(path) as repository:
        request = command(intent)
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
        with pytest.raises(error_type):
            owner(repository).execute(request)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        assert repository.get_execution_intent(intent.intent_id) == intent
        if failure in {"history", "receipt"}:
            repository._connection.execute("DROP TRIGGER forced")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", original)
        retry = owner(repository, identity="purchase-record-retry").execute(request)
        assert retry.replayed is False
        assert counts(repository) == (1, 1)


def test_multi_connection_concurrency_converges_and_enforces_cardinality(tmp_path):
    path = tmp_path / "concurrency.sqlite3"
    intent = seed(path)
    same_request = command(intent)
    barrier = Barrier(2)

    def execute_same(index):
        with SQLitePurchaseExecutionRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity=f"same-{index}").execute(same_request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(execute_same, range(2)))
    assert {value.record.record_id for value in same} == {same[0].record.record_id}
    assert sorted(value.replayed for value in same) == [False, True]
    with SQLitePurchaseExecutionRepository(path) as repository:
        assert counts(repository) == (1, 1)

    alias_path = tmp_path / "alias.sqlite3"
    alias_intent = seed(alias_path)
    first_request = command(alias_intent)
    with SQLitePurchaseExecutionRepository(alias_path) as repository:
        first = owner(repository).execute(first_request)
    alias_request = replace(
        first_request,
        command_id="purchase-execution-alias-command",
        requested_at=first_request.requested_at + timedelta(minutes=1),
    )
    with SQLitePurchaseExecutionRepository(alias_path) as repository:
        alias = owner(repository, alias=True).execute(alias_request)
        assert alias.record.record_id == first.record.record_id
        assert alias.replayed is True
        assert counts(repository) == (1, 2)

    conflict_path = tmp_path / "conflict.sqlite3"
    conflict_intent = seed(conflict_path)
    requests = (
        command(conflict_intent, command_id="competing-a", external_order_reference="order-a"),
        command(conflict_intent, command_id="competing-b", external_order_reference="order-b"),
    )
    barrier = Barrier(2)

    def execute_competing(index):
        with SQLitePurchaseExecutionRepository(conflict_path) as repository:
            barrier.wait()
            return owner(repository, identity=f"competing-{index}").execute(requests[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute_competing, index) for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except PurchaseExecutionCardinalityConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, PurchaseExecutionPublication) for value in outcomes) == 1
    assert sum(isinstance(value, PurchaseExecutionCardinalityConflictError) for value in outcomes) == 1
    with SQLitePurchaseExecutionRepository(conflict_path) as repository:
        assert counts(repository) == (1, 1)


def test_same_command_changed_payload_concurrency_commits_once_and_conflicts(tmp_path):
    path = tmp_path / "changed.sqlite3"
    intent = seed(path)
    requests = (
        command(intent, external_order_reference="order-a"),
        command(intent, external_order_reference="order-b"),
    )
    barrier = Barrier(2)

    def execute(index):
        with SQLitePurchaseExecutionRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity=f"changed-{index}").execute(requests[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, index) for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except PurchaseExecutionReplayConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, PurchaseExecutionPublication) for value in outcomes) == 1
    assert sum(isinstance(value, PurchaseExecutionReplayConflictError) for value in outcomes) == 1
    with SQLitePurchaseExecutionRepository(path) as repository:
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("corruption", ["fingerprint", "schema", "orphan"])
def test_malformed_persistence_is_rejected(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    intent = seed(path)
    with SQLitePurchaseExecutionRepository(path) as repository:
        result = owner(repository).execute(command(intent))
        record_id = result.record.record_id
        command_id = result.receipt.command_id
    connection = sqlite3.connect(path)
    if corruption == "orphan":
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            f"INSERT INTO {RECEIPTS} VALUES(?,?,?,?,?,?)",
            ("orphan-command", "missing-record", "0" * 64, NOW.isoformat(), "purchase-execution-receipt-v1", NOW.isoformat()),
        )
    else:
        connection.execute("DROP TRIGGER trg_purchase_execution_record_history_no_update")
        if corruption == "fingerprint":
            connection.execute(
                f"UPDATE {HISTORY} SET integrity_fingerprint=? WHERE record_id=?",
                ("0" * 64, record_id),
            )
        else:
            connection.execute(
                f"UPDATE {HISTORY} SET schema_version=? WHERE record_id=?",
                ("purchase-execution-record-v999", record_id),
            )
    connection.commit()
    connection.close()
    with SQLitePurchaseExecutionRepository(path) as repository:
        with pytest.raises(MalformedPurchaseExecutionPersistenceError):
            if corruption == "orphan":
                repository.validate_replay("orphan-command", "0" * 64)
            else:
                repository.get_record(record_id)


def test_connection_ownership_and_cleanup(tmp_path):
    path = tmp_path / "ownership.sqlite3"
    seed(path)
    owned = SQLitePurchaseExecutionRepository(path)
    assert owned._execution._connection is owned._connection
    assert owned._execution._sourcing._connection is owned._connection
    owned.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        owned._connection.execute("SELECT 1")

    connection = sqlite3.connect(path)
    injected = SQLitePurchaseExecutionRepository(connection=connection)
    injected.close()
    connection.execute("SELECT 1")
    connection.close()
