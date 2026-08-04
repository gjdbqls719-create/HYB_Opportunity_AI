from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import inspect
import sqlite3
from threading import Barrier

import pytest

from app.application.discovery_persistence import (
    DiscoveryExecutionIdentityConflictError,
    DiscoveryExecutionNotFoundError,
    DiscoveryExecutionReplayConflict,
    DiscoveryExecutionResultCommitError,
    DiscoveryExecutionResultHistoryError,
    DiscoveryGroupMembershipError,
    DiscoveryResultRepository,
    MalformedDiscoveryExecutionResult,
    UnsupportedDiscoveryExecutionResultVersion,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryResultRepository,
)
from test_discovery_command_sqlite_persistence import receipt
from test_discovery_correlation_contract import NOW, command, group
from test_discovery_observation_group_sqlite_persistence import prepare, save_members


def result(**changes):
    values = {
        "command_id": "command-1",
        "discovery_execution_id": "execution-1",
        "finalized_group_ids": ("group-opaque-1",),
        "completed_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return DiscoveryExecutionResult(**values)


def prepare_group(path):
    prepare(path)
    save_members(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    groups.save_group(group())
    groups.close()


def table_state(connection):
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM discovery_execution_result_history ORDER BY rowid"
        )
    )


def test_schema_protocol_initialization_trigger_and_no_current_projection(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare_group(path)
    repository: DiscoveryResultRepository = SQLiteDiscoveryResultRepository(path)
    repository.close()
    repository = SQLiteDiscoveryResultRepository(path)
    columns = [
        row[1]
        for row in repository._connection.execute(
            "PRAGMA table_info(discovery_execution_result_history)"
        )
    ]
    assert columns == [
        "command_id", "execution_id", "ordered_finalized_group_ids_json",
        "zero_result", "completed_at", "result_schema_version",
        "result_fingerprint", "inserted_at",
    ]
    tables = {
        row[0]
        for row in repository._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'discovery_execution_result%'"
        )
    }
    assert tables == {"discovery_execution_result_history"}
    repository.save_result(result())
    for operation in ("UPDATE", "DELETE"):
        statement = (
            "UPDATE discovery_execution_result_history SET command_id = command_id"
            if operation == "UPDATE"
            else "DELETE FROM discovery_execution_result_history"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)
    repository.close()


def test_exact_round_trip_queries_restart_and_response_loss_replay(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare_group(path)
    repository = SQLiteDiscoveryResultRepository(path)
    expected = result()
    assert repository.save_result(expected) == expected
    assert repository.save_result(expected) == expected
    assert repository.get_result("execution-1") == expected
    assert repository.get_by_execution("execution-1") == expected
    assert repository.get_by_command("command-1") == expected
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_execution_result_history").fetchone()[0] == 1
    repository.close()
    restarted = SQLiteDiscoveryResultRepository(path)
    assert restarted.save_result(expected) == expected
    assert restarted.get_by_command("command-1") == expected
    assert restarted._connection.execute("SELECT COUNT(*) FROM discovery_execution_result_history").fetchone()[0] == 1
    restarted.close()


def test_zero_result_is_an_authoritative_success_without_groups(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    repository = SQLiteDiscoveryResultRepository(path)
    zero = result(finalized_group_ids=())
    repository.save_result(zero)
    assert repository.get_result("execution-1") == zero
    row = repository._connection.execute(
        "SELECT zero_result FROM discovery_execution_result_history"
    ).fetchone()
    assert row[0] == 1
    repository.close()


def test_changed_result_missing_group_and_identity_mismatch_are_rejected(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare_group(path)
    repository = SQLiteDiscoveryResultRepository(path)
    repository.save_result(result())
    before = table_state(repository._connection)
    with pytest.raises(DiscoveryExecutionReplayConflict):
        repository.save_result(
            replace(result(), completed_at=result().completed_at + timedelta(seconds=1))
        )
    assert table_state(repository._connection) == before
    repository.close()

    path = tmp_path / "missing.db"
    prepare(path)
    SQLiteDiscoveryGroupRepository(path).close()
    repository = SQLiteDiscoveryResultRepository(path)
    with pytest.raises(DiscoveryGroupMembershipError):
        repository.save_result(result())
    with pytest.raises(DiscoveryExecutionNotFoundError):
        repository.save_result(
            result(command_id="missing", discovery_execution_id="missing")
        )
    repository.close()

    path = tmp_path / "identity.db"
    prepare(path, second_execution=True)
    repository = SQLiteDiscoveryResultRepository(path)
    with pytest.raises(DiscoveryExecutionIdentityConflictError):
        repository.save_result(
            result(discovery_execution_id="execution-2", finalized_group_ids=())
        )
    repository.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (("insert", DiscoveryExecutionResultHistoryError),
     ("commit", DiscoveryExecutionResultCommitError)),
)
def test_atomic_failure_matrix_preserves_committed_rows(tmp_path, stage, error_type) -> None:
    class Failing(SQLiteDiscoveryResultRepository):
        def _insert_result(self, value):
            if stage == "insert":
                raise sqlite3.OperationalError("private result insert failure")
            return super()._insert_result(value)

        def _commit(self):
            if stage == "commit":
                raise sqlite3.OperationalError("private result commit failure")
            return super()._commit()

    path = tmp_path / "discovery.db"
    prepare(path, second_execution=True)
    baseline = SQLiteDiscoveryResultRepository(path)
    baseline_result = result(finalized_group_ids=())
    baseline.save_result(baseline_result)
    expected = table_state(baseline._connection)
    baseline.close()
    repository = Failing(path)
    second = result(
        command_id="command-2", discovery_execution_id="execution-2",
        finalized_group_ids=(), completed_at=result().completed_at + timedelta(minutes=1),
    )
    with pytest.raises(error_type):
        repository.save_result(second)
    assert table_state(repository._connection) == expected
    assert repository._connection.in_transaction is False
    repository.close()


def test_read_only_queries_are_deterministic_and_zero_write(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare_group(path)
    repository = SQLiteDiscoveryResultRepository(path)
    repository.save_result(result())
    before = tuple(
        (table, tuple(tuple(row) for row in repository._connection.execute(f"SELECT * FROM {table} ORDER BY rowid")))
        for table in (
            "discovery_command_history", "discovery_command_receipts",
            "discovery_collected_observation_history",
            "discovery_finalized_group_history", "discovery_finalized_group_members",
            "discovery_execution_result_history",
        )
    )
    for _ in range(2):
        assert repository.get_result("execution-1") == result()
        assert repository.get_by_command("command-1") == result()
        assert repository.get_by_execution("execution-1") == result()
    after = tuple(
        (table, tuple(tuple(row) for row in repository._connection.execute(f"SELECT * FROM {table} ORDER BY rowid")))
        for table in (
            "discovery_command_history", "discovery_command_receipts",
            "discovery_collected_observation_history",
            "discovery_finalized_group_history", "discovery_finalized_group_members",
            "discovery_execution_result_history",
        )
    )
    assert after == before
    assert repository._connection.in_transaction is False
    repository.close()


def _race(path, left, right):
    barrier = Barrier(2)

    def save(value):
        repository = SQLiteDiscoveryResultRepository(path)
        try:
            barrier.wait()
            return repository.save_result(value)
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(save, left), executor.submit(save, right))
        results, errors = [], []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:
                errors.append(error)
    return results, errors


def test_multi_connection_exact_replay_and_conflict(tmp_path) -> None:
    path = tmp_path / "same.db"
    prepare_group(path)
    results, errors = _race(path, result(), result())
    assert errors == [] and results == [result(), result()]
    repository = SQLiteDiscoveryResultRepository(path)
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_execution_result_history").fetchone()[0] == 1
    repository.close()

    path = tmp_path / "changed.db"
    prepare_group(path)
    changed = replace(result(), completed_at=result().completed_at + timedelta(seconds=1))
    results, errors = _race(path, result(), changed)
    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], DiscoveryExecutionReplayConflict)


def test_malformed_fingerprint_zero_flag_and_unsupported_version(tmp_path) -> None:
    for corruption in ("fingerprint", "zero", "version"):
        path = tmp_path / f"{corruption}.db"
        prepare_group(path)
        repository = SQLiteDiscoveryResultRepository(path)
        repository.save_result(result())
        repository._connection.execute(
            "DROP TRIGGER trg_discovery_execution_result_history_no_update"
        )
        if corruption == "fingerprint":
            repository._connection.execute(
                "UPDATE discovery_execution_result_history SET result_fingerprint = ?",
                ("a" * 64,),
            )
        elif corruption == "zero":
            repository._connection.execute(
                "UPDATE discovery_execution_result_history SET zero_result = 1"
            )
        else:
            repository._connection.execute(
                "UPDATE discovery_execution_result_history SET result_schema_version = 'future'"
            )
        repository._connection.commit()
        error_type = (
            UnsupportedDiscoveryExecutionResultVersion
            if corruption == "version"
            else MalformedDiscoveryExecutionResult
        )
        with pytest.raises(error_type):
            repository.get_result("execution-1")
        repository.close()


def test_missing_persisted_group_lineage_is_malformed_result(tmp_path) -> None:
    path = tmp_path / "lineage.db"
    prepare_group(path)
    repository = SQLiteDiscoveryResultRepository(path)
    repository.save_result(result())
    repository._connection.execute(
        "DROP TRIGGER trg_discovery_finalized_group_members_no_delete"
    )
    repository._connection.execute(
        "DROP TRIGGER trg_discovery_finalized_group_history_no_delete"
    )
    repository._connection.execute(
        "DELETE FROM discovery_finalized_group_members"
    )
    repository._connection.execute(
        "DELETE FROM discovery_finalized_group_history"
    )
    repository._connection.commit()
    with pytest.raises(MalformedDiscoveryExecutionResult):
        repository.get_result("execution-1")
    repository.close()


def test_repository_owns_no_clock_or_forbidden_write_boundary() -> None:
    source = inspect.getsource(SQLiteDiscoveryResultRepository).lower()
    assert "clock" not in source
    for forbidden in (
        "insert into discovery_collected",
        "insert into discovery_finalized_group",
        "candidate", "snapshot", "safety", "decision",
    ):
        assert forbidden not in source
