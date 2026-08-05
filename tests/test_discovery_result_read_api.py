from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.application.discovery import (
    DiscoveryCompletionReplayError,
    GroupingCorrelation,
    PersistedDiscoveryResultReader,
)
from app.application.discovery_persistence import (
    DiscoveryExecutionResultHistoryError,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryResultRepository,
)
from app.web import (
    app,
    get_authoritative_discovery_entry,
    get_authoritative_discovery_reader,
)
import app.web as web
from tests.test_application_group_finalization import (
    FINALIZED_AT,
    RecordingFinalizedGroupIdentityProvider,
    RecordingGroupFinalizationClock,
)
from tests.test_authoritative_discovery_api import payload
from tests.test_discovery_execution_completion import close_all, sqlite_entry
from tests.test_discovery_phase_checkpoints import CheckpointRuntime
from tests.test_persisted_discovery_execution_entry import command


def use(reader):
    app.dependency_overrides[get_authoritative_discovery_reader] = lambda: reader
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def seed(path, *, zero=False, two_groups=False):
    runtime = CheckpointRuntime([])
    if zero:
        runtime.collection_facts = ()
        runtime.grouping_correlations = ()
    elif two_groups:
        runtime.grouping_correlations = (
            GroupingCorrelation((0,), 0),
            GroupingCorrelation((1,), 1),
        )
    entry, *repositories = sqlite_entry(path, runtime)
    if two_groups:
        entry._finalized_group_identity_provider = (
            RecordingFinalizedGroupIdentityProvider("group-b", "group-a")
        )
        entry._group_finalization_clock = RecordingGroupFinalizationClock(
            FINALIZED_AT, FINALIZED_AT
        )
    result = entry.execute(command())
    return result, repositories


def test_read_composition_uses_only_result_and_group_repositories_and_closes_scope(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", tmp_path / "read.db")
    dependency = get_authoritative_discovery_reader()
    reader = next(dependency)

    assert isinstance(reader._result_repository, SQLiteDiscoveryResultRepository)
    assert isinstance(reader._group_repository, SQLiteDiscoveryGroupRepository)
    assert not hasattr(reader, "_runtime")
    assert not hasattr(reader, "_persist_command")
    paths = {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in (
            reader._result_repository,
            reader._group_repository,
        )
    }
    assert paths == {str(tmp_path / "read.db")}

    dependency.close()
    for repository in (
        reader._result_repository,
        reader._group_repository,
    ):
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_completed_result_and_groups_are_read_in_result_authoritative_order(
    tmp_path,
) -> None:
    persisted, repositories = seed(tmp_path / "ordered.db", two_groups=True)
    reader = PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
    )
    client = use(reader)
    try:
        result_response = client.get("/api/v1/discovery/executions/execution-1")
        groups_response = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        clear_overrides()
        close_all(*repositories)

    assert result_response.status_code == groups_response.status_code == 200
    assert result_response.json() == {
        "command_id": "command-1",
        "discovery_execution_id": "execution-1",
        "completed_at": persisted.execution_result.completed_at.isoformat().replace(
            "+00:00", "Z"
        ),
        "is_zero_result": False,
        "finalized_group_ids": ["group-b", "group-a"],
    }
    groups = groups_response.json()
    assert groups["discovery_execution_id"] == "execution-1"
    assert [value["finalized_group_id"] for value in groups["finalized_groups"]] == [
        "group-b",
        "group-a",
    ]
    assert groups["finalized_groups"][0]["observation_ids"] == ["observation-one"]
    assert groups["finalized_groups"][1]["observation_ids"] == ["observation-two"]


def test_zero_result_read_is_successful_with_empty_authoritative_groups(tmp_path) -> None:
    _, repositories = seed(tmp_path / "zero.db", zero=True)
    reader = PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
    )
    client = use(reader)
    try:
        result_response = client.get("/api/v1/discovery/executions/execution-1")
        groups_response = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        clear_overrides()
        close_all(*repositories)

    assert result_response.status_code == groups_response.status_code == 200
    assert result_response.json()["is_zero_result"] is True
    assert result_response.json()["finalized_group_ids"] == []
    assert groups_response.json()["finalized_groups"] == []


def test_reads_are_replay_consistent_and_do_not_mutate_repositories(tmp_path) -> None:
    path = tmp_path / "read-only.db"
    entry, *repositories = sqlite_entry(path, CheckpointRuntime([]))
    reader = PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
    )
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    app.dependency_overrides[get_authoritative_discovery_reader] = lambda: reader
    client = TestClient(app)
    try:
        post = client.post("/api/v1/discovery/executions", json=payload())
        before = tuple(
            repository._connection.total_changes
            for repository in (repositories[2], repositories[3])
        )
        first = client.get("/api/v1/discovery/executions/execution-1")
        groups = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
        second = client.get("/api/v1/discovery/executions/execution-1")
        after = tuple(
            repository._connection.total_changes
            for repository in (repositories[2], repositories[3])
        )
    finally:
        clear_overrides()
        close_all(*repositories)

    assert post.status_code == 201
    assert first.status_code == groups.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["command_id"] == post.json()["command_id"]
    assert first.json()["completed_at"] == post.json()["completed_at"]
    assert first.json()["finalized_group_ids"] == [
        value["finalized_group_id"] for value in post.json()["finalized_groups"]
    ]
    assert groups.json()["finalized_groups"] == post.json()["finalized_groups"]
    assert before == after


def test_missing_completion_is_404_for_result_and_groups(tmp_path) -> None:
    result_repository = SQLiteDiscoveryResultRepository(tmp_path / "missing.db")
    group_repository = SQLiteDiscoveryGroupRepository(tmp_path / "missing.db")
    client = use(
        PersistedDiscoveryResultReader(
            result_repository=result_repository,
            group_repository=group_repository,
        )
    )
    try:
        result_response = client.get("/api/v1/discovery/executions/missing")
        groups_response = client.get(
            "/api/v1/discovery/executions/missing/finalized-groups"
        )
    finally:
        clear_overrides()
        result_repository.close()
        group_repository.close()
    assert result_response.status_code == groups_response.status_code == 404
    assert result_response.json()["detail"] == "completed discovery execution not found: missing"


class FailingReader:
    def __init__(self, error):
        self.error = error

    def get_execution_result(self, execution_id):
        raise self.error

    def get_finalized_groups(self, execution_id):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code"),
    (
        (DiscoveryCompletionReplayError("invalid group lineage"), 409),
        (DiscoveryExecutionResultHistoryError("read failed"), 503),
        (sqlite3.OperationalError("database down"), 503),
    ),
)
def test_read_failures_have_explicit_http_mapping(error, status_code) -> None:
    client = use(FailingReader(error))
    try:
        result_response = client.get("/api/v1/discovery/executions/execution-1")
        groups_response = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        clear_overrides()
    assert result_response.status_code == groups_response.status_code == status_code
    expected = (
        "discovery persistence unavailable"
        if isinstance(error, sqlite3.Error)
        else str(error)
    )
    assert result_response.json()["detail"] == expected
