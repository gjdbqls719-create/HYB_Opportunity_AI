from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
import requests

import app.web as web
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.web import app
from engine import orchestrator
from marketplaces import ebay
from tests.test_authoritative_discovery_api import payload
from tests.test_candidate_issuance_api import payload as candidate_payload


def _discovery_counts(path) -> tuple[int, int, int, bool]:
    commands = SQLiteDiscoveryCommandRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    results = SQLiteDiscoveryResultRepository(path)
    try:
        return (
            len(observations.get_by_execution("execution-1")),
            len(groups.get_by_execution("execution-1")),
            0 if results.get_by_execution("execution-1") is None else 1,
            commands.get_command("command-1") is not None,
        )
    finally:
        commands.close()
        observations.close()
        groups.close()
        results.close()


def test_legitimate_empty_collection_commits_zero_result_and_replays_without_runtime(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "legitimate-zero.db"
    calls = 0

    def empty_collection(**kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(orchestrator, "search_ebay_products", empty_collection)

    with TestClient(app) as client:
        first = client.post("/api/v1/discovery/executions", json=payload())
        replay = client.post("/api/v1/discovery/executions", json=payload())

    assert first.status_code == 201
    assert first.json()["is_zero_result"] is True
    assert first.json()["finalized_groups"] == []
    assert replay.status_code == 200
    assert replay.json()["completion_replayed"] is True
    assert calls == 1
    assert _discovery_counts(path) == (0, 0, 1, True)


@pytest.mark.parametrize(
    "collector_error",
    (
        ValueError("EBAY_CLIENT_ID is not configured"),
        RuntimeError("eBay authentication failed"),
    ),
)
def test_collector_configuration_or_provider_failure_is_not_zero_result(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    collector_error: Exception,
) -> None:
    path = tmp_path / "collector-failure.db"

    def fail_collection(**kwargs):
        raise collector_error

    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(orchestrator, "search_ebay_products", fail_collection)

    with TestClient(app) as client:
        response = client.post("/api/v1/discovery/executions", json=payload())
        candidate = client.post("/api/v1/candidates", json=candidate_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == "authoritative discovery execution failed"
    assert candidate.status_code == 404
    assert _discovery_counts(path) == (0, 0, 0, True)


def test_ebay_transport_failure_is_an_explicit_authoritative_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "transport-failure.db"

    def fail_transport(**kwargs):
        raise requests.ConnectionError("eBay transport unavailable")

    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(ebay, "search_items", fail_transport)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/discovery/executions", json=payload())

    assert response.status_code == 502
    assert response.json()["detail"] == "authoritative discovery execution failed"
    assert _discovery_counts(path) == (0, 0, 0, True)
