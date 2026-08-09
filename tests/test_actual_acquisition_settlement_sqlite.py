from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.actual_acquisition_settlement import (
    ActualAcquisitionSettlementPublication,
    ActualAcquisitionSettlementReplayConflictError,
    ActualAcquisitionSettlementRevisionConflictError,
    ActualAcquisitionSettlementTerminalConflictError,
    AdmitActualAcquisitionSettlement,
)
from app.domain.capital import (
    ActualAcquisitionCostCategory,
    ActualAcquisitionSettlementState,
)
from app.infrastructure.actual_acquisition_settlement import (
    ActualAcquisitionSettlementCommitError,
    ActualAcquisitionSettlementHistoryError,
    ActualAcquisitionSettlementReceiptError,
    MalformedActualAcquisitionSettlementPersistenceError,
    SQLiteActualAcquisitionSettlementRepository,
)
from app.infrastructure.purchase_execution import SQLitePurchaseExecutionRepository
from test_actual_acquisition_settlement import complete_facts, request, unknown
from test_purchase_execution_sqlite import command as purchase_command
from test_purchase_execution_sqlite import owner as purchase_owner
from test_purchase_execution_sqlite import seed as seed_purchase_sources


HISTORY = "actual_acquisition_settlement_history"
RECEIPTS = "actual_acquisition_settlement_receipts"


def seed(path):
    intent = seed_purchase_sources(path)
    with SQLitePurchaseExecutionRepository(path) as repository:
        record = purchase_owner(repository).execute(purchase_command(intent)).record
    return record


def owner(repository, record, identity="actual-settlement-1", *, commit_offset=4):
    return AdmitActualAcquisitionSettlement(
        repository,
        settlement_id_generator=lambda: identity,
        admitted_clock=lambda: record.executed_at + timedelta(minutes=3),
        committed_clock=lambda: record.executed_at + timedelta(minutes=commit_offset),
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def blocked_request(record, *, command_id="actual-settlement-command-1"):
    facts = list(complete_facts())
    facts[0] = unknown(ActualAcquisitionCostCategory.UNIT_PURCHASE)
    return request(record, command_id=command_id, fixed_cost_facts=tuple(facts))


def test_round_trip_restart_replay_read_purity_and_connection_ownership(tmp_path):
    path = tmp_path / "actual-settlement.sqlite3"
    record = seed(path)
    command = request(record)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        first = owner(repository, record).execute(command)
        before = repository._connection.total_changes
        assert repository.get_settlement(first.settlement.settlement_id) == first.settlement
        assert repository.validate_replay(command.command_id, command.fingerprint).receipt == first.receipt
        assert repository._connection.total_changes == before
        assert repository._purchase._connection is repository._connection
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        replay = owner(repository, record, identity="unused").execute(command)
        assert replay.replayed is True
        assert replay.settlement == first.settlement
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)

    connection = sqlite3.connect(path)
    injected = SQLiteActualAcquisitionSettlementRepository(connection=connection)
    injected.close()
    connection.execute("SELECT 1")
    connection.close()


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    record = seed(path)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        owner(repository, record).execute(request(record))
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
        ("history", ActualAcquisitionSettlementHistoryError),
        ("receipt", ActualAcquisitionSettlementReceiptError),
        ("commit", ActualAcquisitionSettlementCommitError),
    ),
)
def test_transaction_failures_rollback_and_retry(tmp_path, monkeypatch, failure, error_type):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    record = seed(path)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        command = request(record)
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
        with pytest.raises(error_type):
            owner(repository, record).execute(command)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        assert repository.get_purchase_execution_record(record.record_id) == record
        if failure in {"history", "receipt"}:
            repository._connection.execute("DROP TRIGGER forced")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", original)
        retry = owner(repository, record, identity="retry").execute(command)
        assert retry.replayed is False
        assert counts(repository) == (1, 1)


def test_revision_linearity_and_complete_terminality_survive_restart(tmp_path):
    path = tmp_path / "revisions.sqlite3"
    record = seed(path)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        root = owner(repository, record).execute(blocked_request(record)).settlement
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        complete = owner(repository, record, "complete", commit_offset=5).execute(
            request(
                record,
                command_id="complete-command",
                predecessor_settlement_id=root.settlement_id,
            )
        ).settlement
        assert complete.revision == 2
        assert complete.state is ActualAcquisitionSettlementState.COMPLETE
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        with pytest.raises(ActualAcquisitionSettlementTerminalConflictError):
            owner(repository, record, "post-complete", commit_offset=6).execute(
                request(
                    record,
                    command_id="post-complete-command",
                    predecessor_settlement_id=complete.settlement_id,
                )
            )
        assert counts(repository) == (2, 2)


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "concurrent-replay.sqlite3"
    record = seed(path)
    command = blocked_request(record)
    barrier = Barrier(2)

    def same(index):
        with SQLiteActualAcquisitionSettlementRepository(path) as repository:
            barrier.wait()
            return owner(repository, record, f"same-{index}").execute(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(same, range(2)))
    assert {value.settlement.settlement_id for value in results} == {
        results[0].settlement.settlement_id
    }
    assert sorted(value.replayed for value in results) == [False, True]

    changed_path = tmp_path / "concurrent-changed.sqlite3"
    changed_record = seed(changed_path)
    commands = (
        blocked_request(changed_record),
        replace(blocked_request(changed_record), target_currency="USD"),
    )
    barrier = Barrier(2)

    def changed(index):
        with SQLiteActualAcquisitionSettlementRepository(changed_path) as repository:
            barrier.wait()
            return owner(repository, changed_record, f"changed-{index}").execute(commands[index])

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(changed, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except ActualAcquisitionSettlementReplayConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, ActualAcquisitionSettlementPublication) for value in outcomes) == 1
    assert sum(isinstance(value, ActualAcquisitionSettlementReplayConflictError) for value in outcomes) == 1


def test_concurrent_first_and_child_revisions_never_fork(tmp_path):
    first_path = tmp_path / "competing-first.sqlite3"
    record = seed(first_path)
    commands = (
        blocked_request(record, command_id="first-a"),
        blocked_request(record, command_id="first-b"),
    )
    barrier = Barrier(2)

    def first(index):
        with SQLiteActualAcquisitionSettlementRepository(first_path) as repository:
            barrier.wait()
            return owner(repository, record, f"first-{index}").execute(commands[index])

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(first, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except ActualAcquisitionSettlementRevisionConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, ActualAcquisitionSettlementPublication) for value in outcomes) == 1
    assert sum(isinstance(value, ActualAcquisitionSettlementRevisionConflictError) for value in outcomes) == 1

    child_path = tmp_path / "competing-child.sqlite3"
    child_record = seed(child_path)
    with SQLiteActualAcquisitionSettlementRepository(child_path) as repository:
        root = owner(repository, child_record).execute(blocked_request(child_record)).settlement
    child_commands = (
        request(child_record, command_id="child-a", predecessor_settlement_id=root.settlement_id),
        request(child_record, command_id="child-b", predecessor_settlement_id=root.settlement_id),
    )
    barrier = Barrier(2)

    def child(index):
        with SQLiteActualAcquisitionSettlementRepository(child_path) as repository:
            barrier.wait()
            return owner(repository, child_record, f"child-{index}").execute(child_commands[index])

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(child, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except (ActualAcquisitionSettlementRevisionConflictError, ActualAcquisitionSettlementTerminalConflictError) as error:
                outcomes.append(error)
    assert sum(isinstance(value, ActualAcquisitionSettlementPublication) for value in outcomes) == 1
    assert len(outcomes) == 2
    with SQLiteActualAcquisitionSettlementRepository(child_path) as repository:
        assert counts(repository) == (2, 2)


@pytest.mark.parametrize(
    "corruption",
    ["fingerprint", "state", "revision", "decimal", "currency", "evidence", "arithmetic", "schema"],
)
def test_malformed_payload_and_columns_are_rejected(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    record = seed(path)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        result = owner(repository, record).execute(request(record))
        settlement_id = result.settlement.settlement_id
    connection = sqlite3.connect(path)
    connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
    row = connection.execute(
        f"SELECT payload_json FROM {HISTORY} WHERE settlement_id=?", (settlement_id,)
    ).fetchone()
    payload = json.loads(row[0])
    if corruption == "fingerprint":
        connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint=? WHERE settlement_id=?",
            ("0" * 64, settlement_id),
        )
    else:
        if corruption == "state":
            payload["state"] = "blocked"
        elif corruption == "revision":
            payload["revision"] = 2
        elif corruption == "decimal":
            payload["fixed_cost_facts"][0]["amount"] = "NaN"
        elif corruption == "currency":
            payload["target_currency"] = "BAD!"
        elif corruption == "evidence":
            payload["fixed_cost_facts"][0]["evidence"]["operator_id"] = "intruder"
        elif corruption == "arithmetic":
            payload["acquisition_batch_total"] = "999"
        else:
            payload["schema_version"] = "actual-acquisition-settlement-v999"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=? WHERE settlement_id=?",
            (encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest(), settlement_id),
        )
    connection.commit()
    connection.close()
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        with pytest.raises(MalformedActualAcquisitionSettlementPersistenceError):
            repository.get_settlement(settlement_id)


def test_orphan_receipt_is_rejected(tmp_path):
    path = tmp_path / "orphan.sqlite3"
    seed(path)
    with SQLiteActualAcquisitionSettlementRepository(path):
        pass
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        f"INSERT INTO {RECEIPTS} VALUES(?,?,?,?,?,?)",
        (
            "orphan-command", "missing-settlement", "0" * 64,
            "2026-01-01T00:00:00+00:00", "actual-acquisition-settlement-receipt-v1",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        with pytest.raises(MalformedActualAcquisitionSettlementPersistenceError):
            repository.validate_replay("orphan-command", "0" * 64)
