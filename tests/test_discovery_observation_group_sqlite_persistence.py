from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.discovery_persistence import (
    DiscoveryExecutionIdentityConflictError,
    DiscoveryExecutionNotFoundError,
    DiscoveryGroupCommitError,
    DiscoveryGroupConflictError,
    DiscoveryGroupHistoryError,
    DiscoveryGroupMembershipError,
    DiscoveryGroupMembershipPersistenceError,
    DiscoveryGroupRepository,
    DiscoveryObservationCommitError,
    DiscoveryObservationConflictError,
    DiscoveryObservationHistoryError,
    DiscoveryObservationRepository,
    MalformedDiscoveryGroupPersistenceError,
    MalformedDiscoveryObservationPersistenceError,
    UnsupportedDiscoveryGroupVersionError,
    UnsupportedDiscoveryObservationVersionError,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
)
from test_discovery_command_sqlite_persistence import receipt
from test_discovery_correlation_contract import (
    candidate_ready_observation,
    command,
    group,
    market_identity,
    observation,
)


def prepare(path, *, second_execution=False):
    commands = SQLiteDiscoveryCommandRepository(path)
    first = command()
    commands.save_command(first, receipt(first))
    if second_execution:
        second = command(command_id="command-2", discovery_execution_id="execution-2")
        commands.save_command(second, receipt(second))
    commands.close()


def observation_two(**changes):
    values = {
        "observation_id": "observation-2",
        "observed_at": observation().observed_at + timedelta(seconds=1),
    }
    values.update(changes)
    return replace(observation(), **values)


def save_members(path):
    repository = SQLiteDiscoveryObservationRepository(path)
    repository.save_observation(observation())
    repository.save_observation(observation_two())
    repository.close()


def state(connection):
    return tuple(
        (
            table,
            tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")),
        )
        for table in (
            "discovery_command_history", "discovery_command_receipts",
            "discovery_collected_observation_history",
            "discovery_finalized_group_history", "discovery_finalized_group_members",
        )
    )


def test_repository_protocols_schema_triggers_and_no_current_projection(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    observations: DiscoveryObservationRepository = SQLiteDiscoveryObservationRepository(path)
    groups: DiscoveryGroupRepository = SQLiteDiscoveryGroupRepository(path)
    assert observations.get_observation("missing") is None
    assert groups.get_group("missing") is None
    tables = {
        row[0]
        for row in observations._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'discovery_%'"
        )
    }
    assert "discovery_collected_observation_history" in tables
    assert "discovery_finalized_group_history" in tables
    assert "discovery_finalized_group_members" in tables
    assert not any("current" in table for table in tables)
    observations.close()
    groups.close()
    SQLiteDiscoveryObservationRepository(path).close()


def test_observation_exact_round_trip_optional_identity_repeated_listing_and_restart(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    repository = SQLiteDiscoveryObservationRepository(path)
    first = replace(observation(), candidate_market_identity=market_identity())
    second = observation_two()
    assert repository.save_observation(first) == first
    assert repository.save_observation(second) == second
    assert repository.save_observation(first) == first
    assert repository.get_observation(first.observation_id) == first
    assert repository.get_by_execution("execution-1") == (first, second)
    assert repository.get_by_source_listing(first.source_marketplace, first.source_item_id) == (first, second)
    assert repository._connection.execute("SELECT COUNT(*) FROM discovery_collected_observation_history").fetchone()[0] == 2
    repository.close()
    restarted = SQLiteDiscoveryObservationRepository(path)
    assert restarted.get_observation(first.observation_id) == first
    assert restarted.get_observation(second.observation_id) == second
    restarted.close()


def test_candidate_handoff_v2_round_trip_restart_and_corruption_fail_closed(
    tmp_path,
) -> None:
    path = tmp_path / "handoff.db"
    prepare(path)
    repository = SQLiteDiscoveryObservationRepository(path)
    expected = candidate_ready_observation()
    assert repository.save_observation(expected) == expected
    assert repository.get_observation(expected.observation_id) == expected
    repository.close()

    restarted = SQLiteDiscoveryObservationRepository(path)
    assert restarted.get_observation(expected.observation_id) == expected
    restarted._connection.execute(
        "DROP TRIGGER trg_discovery_collected_observation_history_no_update"
    )
    row = restarted._connection.execute(
        "SELECT observation_payload_json FROM discovery_collected_observation_history "
        "WHERE observation_id = ?",
        (expected.observation_id,),
    ).fetchone()
    payload = json.loads(row[0])
    del payload["candidate_discovery_reference"]
    restarted._connection.execute(
        "UPDATE discovery_collected_observation_history "
        "SET observation_payload_json = ? WHERE observation_id = ?",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")),
         expected.observation_id),
    )
    restarted._connection.commit()
    with pytest.raises(MalformedDiscoveryObservationPersistenceError):
        restarted.get_observation(expected.observation_id)
    restarted.close()


def test_observation_conflict_and_orphan_execution_are_explicit(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    repository = SQLiteDiscoveryObservationRepository(path)
    repository.save_observation(observation())
    before = state(repository._connection)
    with pytest.raises(DiscoveryObservationConflictError):
        repository.save_observation(replace(observation(), observed_at=observation().observed_at + timedelta(seconds=2)))
    with pytest.raises(DiscoveryExecutionNotFoundError):
        repository.save_observation(
            replace(observation_two(), discovery_execution_id="missing-execution")
        )
    assert state(repository._connection) == before
    assert repository._connection.in_transaction is False
    repository.close()


def test_group_exact_ordered_round_trip_replay_shared_membership_and_restart(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    save_members(path)
    repository = SQLiteDiscoveryGroupRepository(path)
    first = group()
    second = replace(first, finalized_group_id="group-opaque-2")
    assert repository.save_group(first) == first
    assert repository.save_group(first) == first
    assert repository.save_group(second) == second
    assert repository.get_group(first.finalized_group_id) == first
    assert repository.get_by_execution("execution-1") == (first, second)
    assert repository.get_by_membership_fingerprint(first.membership_fingerprint) == (first, second)
    members = repository._connection.execute(
        "SELECT observation_id FROM discovery_finalized_group_members WHERE finalized_group_id = ? ORDER BY position",
        (first.finalized_group_id,),
    ).fetchall()
    assert tuple(row[0] for row in members) == first.observation_ids
    repository.close()
    restarted = SQLiteDiscoveryGroupRepository(path)
    assert restarted.get_group(first.finalized_group_id) == first
    restarted.close()


def test_group_changed_payload_missing_member_and_cross_execution_are_rejected(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path, second_execution=True)
    observations = SQLiteDiscoveryObservationRepository(path)
    observations.save_observation(observation())
    observations.save_observation(
        observation_two(discovery_execution_id="execution-2")
    )
    observations.close()
    repository = SQLiteDiscoveryGroupRepository(path)
    with pytest.raises(DiscoveryExecutionIdentityConflictError):
        repository.save_group(group())
    with pytest.raises(DiscoveryGroupMembershipError):
        repository.save_group(replace(group(), observation_ids=("observation-1", "missing")))
    same_execution = replace(
        observation_two(), observation_id="observation-3", discovery_execution_id="execution-1"
    )
    observations = SQLiteDiscoveryObservationRepository(path)
    observations.save_observation(same_execution)
    observations.close()
    committed = replace(group(), observation_ids=("observation-1", "observation-3"))
    repository.save_group(committed)
    before = state(repository._connection)
    with pytest.raises(DiscoveryGroupConflictError):
        repository.save_group(replace(committed, grouping_policy_version="changed"))
    assert state(repository._connection) == before
    repository.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (("history", DiscoveryObservationHistoryError), ("commit", DiscoveryObservationCommitError)),
)
def test_observation_atomic_failure_matrix(tmp_path, stage, error_type) -> None:
    class Failing(SQLiteDiscoveryObservationRepository):
        def _insert_observation(self, value):
            if stage == "history":
                raise sqlite3.OperationalError("private observation history failure")
            return super()._insert_observation(value)

        def _commit(self):
            if stage == "commit":
                raise sqlite3.OperationalError("private observation commit failure")
            return super()._commit()

    path = tmp_path / "discovery.db"
    prepare(path)
    baseline = SQLiteDiscoveryObservationRepository(path)
    baseline.save_observation(observation())
    expected = state(baseline._connection)
    baseline.close()
    repository = Failing(path)
    with pytest.raises(error_type):
        repository.save_observation(observation_two())
    assert state(repository._connection) == expected
    assert repository._connection.in_transaction is False
    repository.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (
        ("history", DiscoveryGroupHistoryError),
        ("membership", DiscoveryGroupMembershipPersistenceError),
        ("commit", DiscoveryGroupCommitError),
    ),
)
def test_group_atomic_failure_matrix(tmp_path, stage, error_type) -> None:
    class Failing(SQLiteDiscoveryGroupRepository):
        def _insert_group(self, value):
            if stage == "history":
                raise sqlite3.OperationalError("private group history failure")
            return super()._insert_group(value)

        def _insert_members(self, value):
            if stage == "membership":
                raise sqlite3.OperationalError("private membership failure")
            return super()._insert_members(value)

        def _commit(self):
            if stage == "commit":
                raise sqlite3.OperationalError("private group commit failure")
            return super()._commit()

    path = tmp_path / "discovery.db"
    prepare(path)
    save_members(path)
    repository = Failing(path)
    before = state(repository._connection)
    with pytest.raises(error_type):
        repository.save_group(group())
    assert state(repository._connection) == before
    assert repository._connection.in_transaction is False
    repository.close()


def _race(path, repository_type, left, right, save_name):
    barrier = Barrier(2)

    def save(value):
        repository = repository_type(path)
        try:
            barrier.wait()
            return getattr(repository, save_name)(value)
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


def test_separate_connection_observation_concurrency(tmp_path) -> None:
    path = tmp_path / "same.db"
    prepare(path)
    results, errors = _race(
        path, SQLiteDiscoveryObservationRepository,
        observation(), observation(), "save_observation",
    )
    assert errors == [] and results == [observation(), observation()]

    path = tmp_path / "changed.db"
    prepare(path)
    changed = replace(observation(), observed_at=observation().observed_at + timedelta(seconds=3))
    results, errors = _race(
        path, SQLiteDiscoveryObservationRepository,
        observation(), changed, "save_observation",
    )
    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], DiscoveryObservationConflictError)

    path = tmp_path / "repeated-listing.db"
    prepare(path)
    results, errors = _race(
        path, SQLiteDiscoveryObservationRepository,
        observation(), observation_two(), "save_observation",
    )
    assert errors == []
    assert {value.observation_id for value in results} == {
        "observation-1", "observation-2"
    }


def test_separate_connection_group_concurrency(tmp_path) -> None:
    path = tmp_path / "same.db"
    prepare(path)
    save_members(path)
    results, errors = _race(
        path, SQLiteDiscoveryGroupRepository, group(), group(), "save_group"
    )
    assert errors == [] and results == [group(), group()]

    path = tmp_path / "changed.db"
    prepare(path)
    save_members(path)
    changed = replace(group(), observation_ids=("observation-2", "observation-1"))
    results, errors = _race(
        path, SQLiteDiscoveryGroupRepository, group(), changed, "save_group"
    )
    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], DiscoveryGroupConflictError)

    path = tmp_path / "shared-membership.db"
    prepare(path)
    save_members(path)
    another_group = replace(group(), finalized_group_id="group-opaque-2")
    results, errors = _race(
        path, SQLiteDiscoveryGroupRepository,
        group(), another_group, "save_group",
    )
    assert errors == []
    assert {value.finalized_group_id for value in results} == {
        "group-opaque-1", "group-opaque-2"
    }

    path = tmp_path / "missing-member.db"
    prepare(path)
    save_members(path)
    missing = replace(group(), finalized_group_id="missing-group", observation_ids=("observation-1", "missing"))
    results, errors = _race(
        path, SQLiteDiscoveryGroupRepository, group(), missing, "save_group"
    )
    assert results == [group()]
    assert len(errors) == 1 and isinstance(errors[0], DiscoveryGroupMembershipError)


def test_malformed_and_unsupported_observation_persistence(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    repository = SQLiteDiscoveryObservationRepository(path)
    repository._connection.execute(
        """INSERT INTO discovery_collected_observation_history
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("bad", "execution-1", "ebay", "item", "not-json",
         observation().observed_at.isoformat(), "collector-observation-v1",
         observation().observed_at.isoformat()),
    )
    repository._connection.execute(
        """INSERT INTO discovery_collected_observation_history
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("future", "execution-1", "ebay", "item", "{}",
         observation().observed_at.isoformat(), "future",
         observation().observed_at.isoformat()),
    )
    repository._connection.commit()
    with pytest.raises(MalformedDiscoveryObservationPersistenceError):
        repository.get_observation("bad")
    with pytest.raises(UnsupportedDiscoveryObservationVersionError):
        repository.get_observation("future")
    repository.close()


def test_group_fingerprint_corruption_and_unsupported_version(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    save_members(path)
    repository = SQLiteDiscoveryGroupRepository(path)
    repository.save_group(group())
    repository._connection.execute("DROP TRIGGER trg_discovery_finalized_group_history_no_update")
    repository._connection.execute(
        "UPDATE discovery_finalized_group_history SET membership_fingerprint = ? WHERE finalized_group_id = ?",
        ("a" * 64, group().finalized_group_id),
    )
    repository._connection.commit()
    with pytest.raises(MalformedDiscoveryGroupPersistenceError):
        repository.get_group(group().finalized_group_id)
    repository.close()

    path = tmp_path / "unsupported.db"
    prepare(path)
    save_members(path)
    repository = SQLiteDiscoveryGroupRepository(path)
    repository.save_group(group())
    repository._connection.execute("DROP TRIGGER trg_discovery_finalized_group_history_no_update")
    repository._connection.execute(
        "UPDATE discovery_finalized_group_history SET group_schema_version = 'future'"
    )
    repository._connection.commit()
    with pytest.raises(UnsupportedDiscoveryGroupVersionError):
        repository.get_group(group().finalized_group_id)
    repository.close()


def test_all_authoritative_tables_are_append_only_and_reads_are_zero_write(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    prepare(path)
    save_members(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    groups.save_group(group())
    before = state(groups._connection)
    observations = SQLiteDiscoveryObservationRepository(path)
    assert observations.get_by_execution("execution-1") == (observation(), observation_two())
    assert observations.get_by_source_listing("ebay", observation().source_item_id) == (observation(), observation_two())
    assert groups.get_by_execution("execution-1") == (group(),)
    assert groups.get_by_membership_fingerprint(group().membership_fingerprint) == (group(),)
    assert state(groups._connection) == before
    assert observations._connection.in_transaction is False
    assert groups._connection.in_transaction is False
    for table in (
        "discovery_collected_observation_history",
        "discovery_finalized_group_history",
        "discovery_finalized_group_members",
    ):
        for operation in ("UPDATE", "DELETE"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                statement = (
                    f"UPDATE {table} SET rowid = rowid"
                    if operation == "UPDATE"
                    else f"DELETE FROM {table}"
                )
                groups._connection.execute(statement)
    observations.close()
    groups.close()
