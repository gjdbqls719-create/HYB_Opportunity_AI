from __future__ import annotations

from dataclasses import replace
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.discovery import (
    DiscoveryCompletionReplayError,
    DiscoveryRuntimeCorrelationError,
)
from app.application.discovery_persistence import (
    DiscoveryCommandCommitError,
    DiscoveryReplayConflict,
)
from app.infrastructure.discovery import (
    OrchestratorProductionDiscoveryRuntime,
    ProductionFinalizedGroupIdentityProvider,
    ProductionObservationIdentityProvider,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.web import app, get_authoritative_discovery_entry
import app.web as web
from services.currency import (
    CurrencyConverter,
    ExchangeRateNotFoundError,
    ExchangeRateProviderError,
)
from tests.test_discovery_execution_completion import close_all, sqlite_entry
from tests.test_discovery_phase_checkpoints import CheckpointRuntime
from tests.test_persisted_discovery_execution_entry import NOW, command


def payload(**changes):
    parameters = command().parameters
    value = {
        "command_id": "command-1",
        "discovery_execution_id": "execution-1",
        "requested_at": NOW.isoformat(),
        "query": parameters.query,
        "selling_price_multiplier": str(parameters.selling_price_multiplier),
        "shipping_cost": str(parameters.shipping_cost),
        "marketplace_fee_rate": str(parameters.marketplace_fee_rate),
        "payment_fee_rate": str(parameters.payment_fee_rate),
        "fixed_fee": str(parameters.fixed_fee),
        "marketplace_fee_known": parameters.marketplace_fee_known,
        "payment_fee_known": parameters.payment_fee_known,
        "fixed_fee_known": parameters.fixed_fee_known,
        "tax_rate": str(parameters.tax_rate),
        "other_cost": str(parameters.other_cost),
        "minimum_net_profit": str(parameters.minimum_net_profit),
        "minimum_roi": str(parameters.minimum_roi),
        "estimated_monthly_sales": parameters.estimated_monthly_sales,
        "competitor_count": parameters.competitor_count,
        "risk_level": parameters.risk_level,
        "limit": parameters.limit,
        "match_threshold": str(parameters.match_threshold),
        "target_currency": None,
        "policy_references": [["pricing", "policy-v3"]],
        "source_references": [["market", "ebay-us"]],
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_production_composition_uses_existing_concrete_boundaries_and_closes_scope(
    tmp_path, monkeypatch
) -> None:
    sessions = []

    class Session:
        def __init__(self):
            self.closed = False
            sessions.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(web.requests, "Session", Session)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", tmp_path / "production.db")
    dependency = get_authoritative_discovery_entry()
    entry = next(dependency)

    assert isinstance(
        entry._persist_command._repository, SQLiteDiscoveryCommandRepository
    )
    assert isinstance(entry._runtime, OrchestratorProductionDiscoveryRuntime)
    assert isinstance(
        entry._observation_identity_provider,
        ProductionObservationIdentityProvider,
    )
    assert isinstance(
        entry._observation_repository, SQLiteDiscoveryObservationRepository
    )
    assert isinstance(
        entry._finalized_group_identity_provider,
        ProductionFinalizedGroupIdentityProvider,
    )
    assert isinstance(entry._group_repository, SQLiteDiscoveryGroupRepository)
    assert isinstance(entry._result_repository, SQLiteDiscoveryResultRepository)
    assert isinstance(entry._runtime._currency_converter, CurrencyConverter)
    paths = {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in (
            entry._persist_command._repository,
            entry._observation_repository,
            entry._group_repository,
            entry._result_repository,
        )
    }
    assert paths == {str(tmp_path / "production.db")}

    dependency.close()
    assert sessions[0].closed is True
    for repository in (
        entry._persist_command._repository,
        entry._observation_repository,
        entry._group_repository,
        entry._result_repository,
    ):
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_partial_dependency_construction_failure_closes_open_repository(
    monkeypatch,
) -> None:
    closed: list[bool] = []

    class FirstRepository:
        def __init__(self, path):
            pass

        def close(self):
            closed.append(True)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(web, "SQLiteDiscoveryCommandRepository", FirstRepository)
    monkeypatch.setattr(
        web,
        "SQLiteDiscoveryObservationRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_authoritative_discovery_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


def test_fresh_execution_persists_complete_lineage_and_returns_only_authoritative_facts(
    tmp_path,
) -> None:
    entry, *repositories = sqlite_entry(
        tmp_path / "fresh.db", CheckpointRuntime([])
    )
    client = use(entry)
    try:
        response = client.post("/api/v1/discovery/executions", json=payload())
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {
            "command_id",
            "discovery_execution_id",
            "completed_at",
            "is_zero_result",
            "completion_replayed",
            "finalized_groups",
        }
        assert body["command_id"] == "command-1"
        assert body["discovery_execution_id"] == "execution-1"
        assert body["is_zero_result"] is False
        assert body["completion_replayed"] is False
        assert [group["finalized_group_id"] for group in body["finalized_groups"]] == [
            "group-1"
        ]
        assert body["finalized_groups"][0]["observation_ids"] == [
            "observation-one",
            "observation-two",
        ]
        assert "discovery_results" not in body
        assert "collection_facts" not in body
        assert "grouping_correlations" not in body
        assert repositories[0].get_command("command-1") is not None
        assert len(repositories[1].get_by_execution("execution-1")) == 2
        assert len(repositories[2].get_by_execution("execution-1")) == 1
        assert repositories[3].get_by_execution("execution-1") is not None
    finally:
        clear_overrides()
        close_all(*repositories)


def test_completed_exact_replay_is_runtime_free_and_preserves_group_order(
    tmp_path,
) -> None:
    path = tmp_path / "replay.db"
    first_entry, *first_repositories = sqlite_entry(path, CheckpointRuntime([]))
    client = use(first_entry)
    try:
        first = client.post("/api/v1/discovery/executions", json=payload())
    finally:
        clear_overrides()
        close_all(*first_repositories)

    replay_runtime = CheckpointRuntime([])
    replay_entry, *replay_repositories = sqlite_entry(
        path, replay_runtime, replay=True
    )

    def forbidden_save(*args, **kwargs):
        pytest.fail("completed replay must not call repository save methods")

    replay_repositories[0].save_command = forbidden_save
    replay_repositories[1].save_observation = forbidden_save
    replay_repositories[2].save_group = forbidden_save
    replay_repositories[3].save_result = forbidden_save
    client = use(replay_entry)
    try:
        replay = client.post("/api/v1/discovery/executions", json=payload())
    finally:
        clear_overrides()
        close_all(*replay_repositories)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay_runtime.calls == []
    assert replay_entry._observation_identity_provider.calls == 0
    assert replay_entry._finalized_group_identity_provider.calls == 0
    assert replay_entry._group_finalization_clock.calls == 0
    assert replay_entry._discovery_completion_clock.calls == 0
    assert replay.json()["completion_replayed"] is True
    assert replay.json()["finalized_groups"] == first.json()["finalized_groups"]


def test_zero_result_commit_and_replay_are_explicit_and_runtime_free(tmp_path) -> None:
    path = tmp_path / "zero.db"
    runtime = CheckpointRuntime([])
    runtime.collection_facts = ()
    runtime.grouping_correlations = ()
    first_entry, *first_repositories = sqlite_entry(path, runtime)
    client = use(first_entry)
    try:
        first = client.post("/api/v1/discovery/executions", json=payload())
    finally:
        clear_overrides()
        close_all(*first_repositories)

    replay_runtime = CheckpointRuntime([])
    replay_entry, *replay_repositories = sqlite_entry(
        path, replay_runtime, replay=True
    )
    client = use(replay_entry)
    try:
        replay = client.post("/api/v1/discovery/executions", json=payload())
    finally:
        clear_overrides()
        close_all(*replay_repositories)

    assert first.status_code == 201 and replay.status_code == 200
    assert first.json()["is_zero_result"] is True
    assert first.json()["finalized_groups"] == []
    assert replay.json()["is_zero_result"] is True
    assert replay.json()["completion_replayed"] is True
    assert replay_runtime.calls == []


class FailingEntry:
    def __init__(self, error):
        self.error = error

    def execute(self, value):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    (
        (DiscoveryReplayConflict("changed payload"), 409, "changed payload"),
        (DiscoveryRuntimeCorrelationError("correlation failed"), 409, "correlation failed"),
        (DiscoveryCompletionReplayError("missing lineage"), 409, "missing lineage"),
        (DiscoveryCommandCommitError("write failed"), 503, "write failed"),
        (ExchangeRateNotFoundError("USD/ZZZ unsupported"), 422, "USD/ZZZ unsupported"),
        (ValueError("currency converter is required"), 422, "currency converter is required"),
        (ExchangeRateProviderError("provider down"), 502, "discovery currency conversion failed"),
        (sqlite3.OperationalError("database down"), 503, "discovery persistence unavailable"),
        (RuntimeError("collector failed"), 502, "authoritative discovery execution failed"),
    ),
)
def test_application_failures_have_explicit_http_mapping(error, status_code, detail) -> None:
    client = use(FailingEntry(error))
    try:
        response = client.post("/api/v1/discovery/executions", json=payload())
    finally:
        clear_overrides()
    assert response.status_code == status_code
    assert response.json()["detail"] == detail


def test_malformed_request_and_changed_payload_do_not_fall_back_to_transient_search(
    tmp_path,
) -> None:
    path = tmp_path / "conflict.db"
    entry, *repositories = sqlite_entry(path, CheckpointRuntime([]))
    client = use(entry)
    try:
        malformed = client.post(
            "/api/v1/discovery/executions",
            json=payload(requested_at="2026-08-05T01:00:00"),
        )
        first = client.post("/api/v1/discovery/executions", json=payload())
        conflict = client.post(
            "/api/v1/discovery/executions", json=payload(query="changed")
        )
    finally:
        clear_overrides()
        close_all(*repositories)
    assert malformed.status_code == 422
    assert first.status_code == 201
    assert conflict.status_code == 409


def test_legacy_transient_search_endpoint_remains_separate(monkeypatch) -> None:
    monkeypatch.setattr(web, "find_best_opportunities", lambda **kwargs: [])
    response = TestClient(app).post(
        "/api/v1/opportunities/search", json={"query": "camera"}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"query", "opportunities", "dashboard_cards"}
