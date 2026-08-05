from dataclasses import replace
from datetime import timedelta
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.domain.market_intelligence import MarketObservationScope
from app.infrastructure.discovery import (
    ProductionCandidateIdentityGenerator,
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.web import app, get_candidate_issuance_entry
import app.web as web
from test_candidate_issuance_foundation import (
    Counter,
    ISSUED_AT,
    close,
    issuance_command,
)
from test_candidate_issuance_persistence import counts
from test_candidate_issuance_production_entry import production_entry
from test_discovery_correlation_contract import market_identity
from test_discovery_execution_result_sqlite_persistence import result


def identity_payload(identity=None):
    value = identity or issuance_command().market_observation_identity
    return {
        "scope": value.scope.value,
        "market": value.market,
        "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id,
        "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query,
        "category": value.category,
        "variant_identity": value.variant_identity,
        "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(),
    }


def payload(**changes):
    command = issuance_command()
    value = {
        "issuance_command_id": command.issuance_command_id,
        "discovery_command_id": command.discovery_command_id,
        "discovery_execution_id": command.discovery_execution_id,
        "finalized_group_id": command.finalized_group_id,
        "discovery_reference": command.discovery_reference,
        "market_observation_identity": identity_payload(),
        "requested_at": command.requested_at.isoformat(),
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_candidate_issuance_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_candidate_composition_uses_production_boundaries_and_closes_scope(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", tmp_path / "candidate-api.db")
    dependency = get_candidate_issuance_entry()
    entry = next(dependency)
    persistence = entry._persist_issuance
    issuance = persistence._issuance_service
    repositories = (
        issuance._commands,
        issuance._results,
        issuance._groups,
        issuance._observations,
        persistence._repository,
    )

    assert isinstance(issuance._commands, SQLiteDiscoveryCommandRepository)
    assert isinstance(issuance._results, SQLiteDiscoveryResultRepository)
    assert isinstance(issuance._groups, SQLiteDiscoveryGroupRepository)
    assert isinstance(issuance._observations, SQLiteDiscoveryObservationRepository)
    assert isinstance(persistence._repository, SQLiteCandidateIssuanceRepository)
    assert isinstance(issuance._candidate_id_generator, ProductionCandidateIdentityGenerator)
    assert issuance._clock is not persistence._receipt_clock
    assert issuance._clock().tzinfo is not None
    assert persistence._receipt_clock().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(tmp_path / "candidate-api.db")}

    dependency.close()
    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_candidate_composition_failure_closes_already_opened_resources(monkeypatch):
    closed = []

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
        "SQLiteDiscoveryResultRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_candidate_issuance_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.LISTING, MarketObservationScope.CANONICAL_PRODUCT),
)
def test_candidate_api_issues_listing_and_canonical_product_identity(tmp_path, scope):
    path = tmp_path / f"candidate-{scope.value}.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Counter(f"candidate-{scope.value}"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT + timedelta(seconds=1)),
    )
    client = use(entry)
    identity = market_identity(scope)
    try:
        response = client.post(
            "/api/v1/candidates",
            json=payload(market_observation_identity=identity_payload(identity)),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["candidate_id"] == f"candidate-{scope.value}"
        expected_identity = identity_payload(identity)
        expected_identity["window_started_at"] = expected_identity[
            "window_started_at"
        ].replace("+00:00", "Z")
        expected_identity["window_ended_at"] = expected_identity[
            "window_ended_at"
        ].replace("+00:00", "Z")
        assert body["market_observation_identity"] == expected_identity
        assert body["discovery_command_id"] == "command-1"
        assert body["discovery_execution_id"] == "execution-1"
        assert body["finalized_group_id"] == "group-opaque-1"
        assert body["issuance_command_id"] == "issuance-command-1"
        assert body["replayed"] is False
        assert counts(candidates._connection) == (1, 1, 1)
    finally:
        clear_overrides()
        close(sources)
        candidates.close()


def test_candidate_api_exact_replay_returns_same_candidate_and_receipt(tmp_path):
    path = tmp_path / "candidate-replay.db"
    candidate_generator = Counter("candidate-1")
    issuance_clock = Counter(ISSUED_AT)
    receipt_clock = Counter(ISSUED_AT + timedelta(seconds=1))
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=candidate_generator,
        issuance_clock=issuance_clock,
        receipt_clock=receipt_clock,
    )
    client = use(entry)
    try:
        first = client.post("/api/v1/candidates", json=payload())
        replay = client.post("/api/v1/candidates", json=payload())

        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert candidate_generator.calls == issuance_clock.calls == receipt_clock.calls == 1
        assert counts(candidates._connection) == (1, 1, 1)
    finally:
        clear_overrides()
        close(sources)
        candidates.close()


def test_candidate_api_alias_reuses_candidate_and_adds_receipt(tmp_path):
    path = tmp_path / "candidate-alias.db"
    candidate_generator = Counter("candidate-1")
    issuance_clock = Counter(ISSUED_AT)
    receipt_clock = Counter(
        lambda call: ISSUED_AT + timedelta(seconds=call)
    )
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=candidate_generator,
        issuance_clock=issuance_clock,
        receipt_clock=receipt_clock,
    )
    client = use(entry)
    try:
        first = client.post("/api/v1/candidates", json=payload())
        alias = client.post(
            "/api/v1/candidates",
            json=payload(issuance_command_id="issuance-command-2"),
        )

        assert first.status_code == 201
        assert alias.status_code == 200
        assert alias.json()["candidate_id"] == first.json()["candidate_id"]
        assert alias.json()["issuance_command_id"] == "issuance-command-2"
        assert alias.json()["replayed"] is True
        assert candidate_generator.calls == issuance_clock.calls == 1
        assert receipt_clock.calls == 2
        assert counts(candidates._connection) == (1, 1, 2)
    finally:
        clear_overrides()
        close(sources)
        candidates.close()


@pytest.mark.parametrize(
    ("case", "status_code"),
    (
        ("zero", 409),
        ("missing_group", 404),
        ("missing_completion", 404),
        ("lineage_mismatch", 409),
        ("market_mismatch", 409),
    ),
)
def test_candidate_api_rejects_invalid_authoritative_lineage(
    tmp_path, case, status_code
):
    path = tmp_path / f"candidate-{case}.db"
    completed = case not in {"missing_completion", "zero"}
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Counter("candidate-must-not-persist"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
        completed=completed,
    )
    if case == "zero":
        sources[1].save_result(result(finalized_group_ids=()))
    request = payload()
    if case == "missing_group":
        request["finalized_group_id"] = "missing-group"
    elif case == "lineage_mismatch":
        request["discovery_execution_id"] = "other-execution"
    elif case == "market_mismatch":
        request["market_observation_identity"] = {
            **identity_payload(),
            "marketplace": "amazon",
        }
    client = use(entry)
    try:
        response = client.post("/api/v1/candidates", json=request)

        assert response.status_code == status_code
        assert counts(candidates._connection) == (0, 0, 0)
    finally:
        clear_overrides()
        close(sources)
        candidates.close()


def test_candidate_api_request_is_strict_and_discovery_api_remains_registered():
    malformed = payload(unexpected="value")
    client = TestClient(app)

    response = client.post("/api/v1/candidates", json=malformed)

    assert response.status_code == 422
    paths = {route.path for route in app.routes}
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
