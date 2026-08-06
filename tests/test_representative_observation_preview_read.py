from __future__ import annotations

from fastapi.testclient import TestClient

from app.application.discovery import PersistedDiscoveryResultReader
from app.web import app, get_authoritative_discovery_reader
from tests.test_discovery_execution_completion import close_all, sqlite_entry
from tests.test_discovery_phase_checkpoints import CheckpointRuntime
from tests.test_persisted_discovery_execution_entry import command


def _client(reader: PersistedDiscoveryResultReader) -> TestClient:
    app.dependency_overrides[get_authoritative_discovery_reader] = lambda: reader
    return TestClient(app)


def _reader(repositories) -> PersistedDiscoveryResultReader:
    return PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
        observation_repository=repositories[1],
    )


def test_finalized_group_read_includes_exact_representative_observation_preview(
    tmp_path,
) -> None:
    entry, *repositories = sqlite_entry(
        tmp_path / "representative-preview.db",
        CheckpointRuntime([]),
    )
    entry.execute(command())
    client = _client(_reader(repositories))
    try:
        response = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        app.dependency_overrides.clear()
        close_all(*repositories)

    assert response.status_code == 200
    group = response.json()["finalized_groups"][0]
    assert group["observation_count"] == 2
    assert group["representative_observation"] == {
        "title": "Product one",
        "image_url": "",
        "marketplace": "ebay",
        "price": 10.0,
        "currency": "USD",
        "url": "https://example.com/one",
    }
    assert "price_range" not in group
    assert "lowest_price" not in group
    assert "highest_price" not in group


def test_zero_result_read_has_no_representative_preview(tmp_path) -> None:
    runtime = CheckpointRuntime([])
    runtime.collection_facts = ()
    runtime.grouping_correlations = ()
    entry, *repositories = sqlite_entry(tmp_path / "zero-preview.db", runtime)
    entry.execute(command())
    client = _client(_reader(repositories))
    try:
        response = client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        app.dependency_overrides.clear()
        close_all(*repositories)

    assert response.status_code == 200
    assert response.json()["finalized_groups"] == []


def test_restart_replay_restores_same_representative_preview(tmp_path) -> None:
    path = tmp_path / "restart-preview.db"
    entry, *repositories = sqlite_entry(path, CheckpointRuntime([]))
    entry.execute(command())
    first_client = _client(_reader(repositories))
    first = first_client.get(
        "/api/v1/discovery/executions/execution-1/finalized-groups"
    )
    app.dependency_overrides.clear()
    close_all(*repositories)

    _, *restarted_repositories = sqlite_entry(path, CheckpointRuntime([]), replay=True)
    restarted_client = _client(_reader(restarted_repositories))
    try:
        replay = restarted_client.get(
            "/api/v1/discovery/executions/execution-1/finalized-groups"
        )
    finally:
        app.dependency_overrides.clear()
        close_all(*restarted_repositories)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
