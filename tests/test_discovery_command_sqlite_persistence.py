from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.discovery_persistence import (
    DiscoveryCommandCommitError,
    DiscoveryCommandHistoryError,
    DiscoveryCommandReceipt,
    DiscoveryCommandReceiptError,
    DiscoveryReplayConflict,
    DuplicateDiscoveryExecutionError,
    MalformedDiscoveryCommandPersistenceError,
    PersistDiscoveryCommand,
    UnsupportedDiscoveryReceiptVersion,
)
from app.domain.discovery_identity import UnsupportedDiscoveryCommandVersionError
from app.infrastructure.discovery import SQLiteDiscoveryCommandRepository
from test_discovery_correlation_contract import command


COMMITTED_AT = datetime(2026, 8, 5, 11, tzinfo=timezone.utc)


def receipt(value=None, *, committed_at=COMMITTED_AT):
    value = value or command()
    return DiscoveryCommandReceipt(
        value.command_id,
        value.discovery_execution_id,
        value.fingerprint,
        committed_at,
    )


def table_state(connection):
    return tuple(
        (
            table,
            tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")),
        )
        for table in ("discovery_command_history", "discovery_command_receipts")
    )


def test_schema_is_idempotent_exact_append_only_and_has_no_projection(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    repository = SQLiteDiscoveryCommandRepository(path)
    repository.close()
    repository = SQLiteDiscoveryCommandRepository(path)
    connection = repository._connection
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'discovery_command%'"
        )
    }
    assert tables == {"discovery_command_history", "discovery_command_receipts"}
    assert [row[1] for row in connection.execute("PRAGMA table_info(discovery_command_history)")] == [
        "command_id", "execution_id", "canonical_payload_json",
        "canonical_payload_fingerprint", "requested_at",
        "command_schema_version", "inserted_at",
    ]
    repository.save_command(command(), receipt())
    for table in tables:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(f"UPDATE {table} SET command_id = command_id")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(f"DELETE FROM {table}")
    repository.close()


def test_exact_command_and_receipt_round_trip_and_read_only_queries(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    repository = SQLiteDiscoveryCommandRepository(path)
    expected = command()
    expected_receipt = receipt(expected)
    assert repository.save_command(expected, expected_receipt) == expected_receipt
    before = table_state(repository._connection)
    assert repository.get_command(expected.command_id) == expected
    assert repository.get_by_execution(expected.discovery_execution_id) == expected
    assert repository.exists(expected.command_id)
    assert repository.validate_replay(expected.command_id, expected.fingerprint) == expected_receipt
    assert repository.validate_replay("missing", "a" * 64) is None
    assert table_state(repository._connection) == before
    assert repository._connection.in_transaction is False
    repository.close()
    restarted = SQLiteDiscoveryCommandRepository(path)
    assert restarted.get_command(expected.command_id) == expected
    assert restarted.validate_replay(expected.command_id, expected.fingerprint) == expected_receipt
    restarted.close()


def test_application_first_commit_restart_replay_and_clock_contract(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    calls = []
    repository = SQLiteDiscoveryCommandRepository(path)
    first = PersistDiscoveryCommand(
        repository, clock=lambda: calls.append(1) or COMMITTED_AT
    ).execute(command())
    repository.close()
    restarted = SQLiteDiscoveryCommandRepository(path)
    replay = PersistDiscoveryCommand(
        restarted,
        clock=lambda: pytest.fail("replay must not call the clock"),
    ).execute(command())
    assert calls == [1]
    assert first.replayed is False
    assert replay == replace(first, replayed=True)
    assert len(table_state(restarted._connection)[0][1]) == 1
    restarted.close()


def test_replay_conflict_execution_uniqueness_and_distinct_execution(tmp_path) -> None:
    repository = SQLiteDiscoveryCommandRepository(tmp_path / "discovery.db")
    original = command()
    repository.save_command(original, receipt(original))
    before = table_state(repository._connection)
    changed = command(parameters=replace(original.parameters, limit=20))
    with pytest.raises(DiscoveryReplayConflict):
        repository.save_command(changed, receipt(changed))
    collision = command(command_id="command-2")
    with pytest.raises(DuplicateDiscoveryExecutionError):
        repository.save_command(collision, receipt(collision))
    distinct = command(command_id="command-2", discovery_execution_id="execution-2")
    repository.save_command(distinct, receipt(distinct))
    assert table_state(repository._connection)[:1] != before[:1]
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_command_history").fetchone()[0] == 2
    repository.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (("history", DiscoveryCommandHistoryError),
     ("receipt", DiscoveryCommandReceiptError),
     ("commit", DiscoveryCommandCommitError)),
)
def test_atomic_failure_matrix_rolls_back_everything(tmp_path, stage, error_type) -> None:
    class FailingRepository(SQLiteDiscoveryCommandRepository):
        def _insert_command(self, *args):
            if stage == "history":
                raise sqlite3.OperationalError("private history failure")
            return super()._insert_command(*args)

        def _insert_receipt(self, *args):
            if stage == "receipt":
                raise sqlite3.OperationalError("private receipt failure")
            return super()._insert_receipt(*args)

        def _commit(self):
            if stage == "commit":
                raise sqlite3.OperationalError("private commit failure")
            return super()._commit()

    path = tmp_path / "discovery.db"
    baseline = SQLiteDiscoveryCommandRepository(path)
    baseline.save_command(command(), receipt())
    expected_state = table_state(baseline._connection)
    baseline.close()
    repository = FailingRepository(path)
    next_command = command(command_id="command-2", discovery_execution_id="execution-2")
    with pytest.raises(error_type):
        repository.save_command(next_command, receipt(next_command))
    assert table_state(repository._connection) == expected_state
    assert repository._connection.in_transaction is False
    repository.close()


def _concurrent(path, left, right):
    barrier = Barrier(2)

    def persist(value, minute):
        repository = SQLiteDiscoveryCommandRepository(path)
        try:
            barrier.wait()
            return PersistDiscoveryCommand(
                repository,
                clock=lambda: COMMITTED_AT.replace(minute=minute),
            ).execute(value)
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(persist, left, 1), executor.submit(persist, right, 2)]
        results, errors = [], []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:
                errors.append(error)
    return results, errors


def test_multi_connection_same_command_converges_and_changed_payload_conflicts(tmp_path) -> None:
    path = tmp_path / "same.db"
    results, errors = _concurrent(path, command(), command())
    assert errors == []
    assert len(results) == 2
    assert results[0].receipt == results[1].receipt
    assert sorted(result.replayed for result in results) == [False, True]
    repository = SQLiteDiscoveryCommandRepository(path)
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_command_history").fetchone()[0] == 1
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_command_receipts").fetchone()[0] == 1
    repository.close()

    path = tmp_path / "changed.db"
    changed = command(parameters=replace(command().parameters, limit=20))
    results, errors = _concurrent(path, command(), changed)
    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], DiscoveryReplayConflict)


def test_multi_connection_execution_collision_has_one_winner(tmp_path) -> None:
    first = command()
    second = command(command_id="command-2")
    results, errors = _concurrent(tmp_path / "collision.db", first, second)
    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], DuplicateDiscoveryExecutionError)


def test_multi_connection_distinct_commands_and_executions_both_commit(tmp_path) -> None:
    first = command()
    second = command(command_id="command-2", discovery_execution_id="execution-2")
    results, errors = _concurrent(tmp_path / "distinct.db", first, second)
    assert errors == []
    assert {result.command.command_id for result in results} == {"command-1", "command-2"}


def _raw_pair(connection, *, payload, fingerprint="a" * 64, command_version="discovery-command-v1", receipt_version="discovery-command-receipt-v1"):
    connection.execute(
        "INSERT INTO discovery_command_history VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("command-1", "execution-1", payload, fingerprint, COMMITTED_AT.isoformat(), command_version, COMMITTED_AT.isoformat()),
    )
    connection.execute(
        "INSERT INTO discovery_command_receipts VALUES (?, ?, ?, ?, ?, ?)",
        ("command-1", "execution-1", fingerprint, COMMITTED_AT.isoformat(), receipt_version, COMMITTED_AT.isoformat()),
    )
    connection.commit()


def test_malformed_json_and_unsupported_versions_are_distinguishable(tmp_path) -> None:
    malformed = SQLiteDiscoveryCommandRepository(tmp_path / "malformed.db")
    _raw_pair(malformed._connection, payload="not-json")
    with pytest.raises(MalformedDiscoveryCommandPersistenceError):
        malformed.get_command("command-1")
    malformed.close()

    unsupported = SQLiteDiscoveryCommandRepository(tmp_path / "unsupported.db")
    payload = json.loads(SQLiteDiscoveryCommandRepository._payload(command()))
    payload["schema_version"] = "future"
    _raw_pair(
        unsupported._connection,
        payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        command_version="future",
    )
    with pytest.raises(UnsupportedDiscoveryCommandVersionError):
        unsupported.get_command("command-1")
    unsupported.close()

    receipt_version = SQLiteDiscoveryCommandRepository(tmp_path / "receipt-version.db")
    _raw_pair(
        receipt_version._connection,
        payload=SQLiteDiscoveryCommandRepository._payload(command()),
        fingerprint=command().fingerprint,
        receipt_version="future",
    )
    with pytest.raises(UnsupportedDiscoveryReceiptVersion):
        receipt_version.validate_replay("command-1", command().fingerprint)
    receipt_version.close()


@pytest.mark.parametrize("corruption", ("fingerprint", "datetime", "decimal"))
def test_malformed_persisted_canonical_values_are_rejected(tmp_path, corruption) -> None:
    repository = SQLiteDiscoveryCommandRepository(tmp_path / f"{corruption}.db")
    payload = json.loads(SQLiteDiscoveryCommandRepository._payload(command()))
    fingerprint = command().fingerprint
    if corruption == "fingerprint":
        fingerprint = "a" * 64
    elif corruption == "datetime":
        payload["requested_at"] = "not-a-datetime"
    else:
        payload["parameters"]["minimum_roi"] = "not-a-decimal"
    _raw_pair(
        repository._connection,
        payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        fingerprint=fingerprint,
    )
    with pytest.raises(MalformedDiscoveryCommandPersistenceError):
        repository.get_command("command-1")
    repository.close()
