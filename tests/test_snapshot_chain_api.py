from datetime import timedelta
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.snapshot_chain_binding import (
    CompleteSnapshotChainProductionEntry,
    SnapshotChainBindingCommandConflictError,
    SnapshotChainBindingNotFoundError,
    SnapshotChainIncompleteError,
    SnapshotChainMarketIdentityConflictError,
)
from app.infrastructure.economics_calculation import (
    SQLiteEconomicsCalculationOwnerRepository,
)
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from app.infrastructure.snapshot_chain_identity import (
    ProductionSnapshotChainBindingIdentityGenerator,
)
from app.web import app, get_snapshot_chain_entry
import app.web as web
from test_candidate_issuance_foundation import Counter
from test_discovery_correlation_contract import NOW
from test_snapshot_chain_production_entry import (
    BOUND_AT,
    COMMITTED_AT,
    chain_counts,
    close_prepared,
    prepare_complete_sources,
    production_entry,
)


def payload(**changes):
    value = {
        "command_id": "snapshot-chain-command-1",
        "opportunity_id": "opportunity-1",
        "product_snapshot_capture_command_id": "capture-command-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "economics_calculation_command_id": "economics-command-1",
        "requested_at": (NOW + timedelta(minutes=45)).isoformat(),
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_snapshot_chain_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_snapshot_chain_composition_uses_production_dependencies_and_closes(
    tmp_path, monkeypatch
):
    path = tmp_path / "snapshot-chain-composition.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_snapshot_chain_entry()
    entry = next(dependency)
    owner = entry._bind
    repositories = (
        entry._sources,
        entry._captures,
        entry._prices,
        entry._economics,
        owner._repo,
    )

    assert isinstance(entry, CompleteSnapshotChainProductionEntry)
    assert isinstance(entry._sources, SQLiteCandidatePromotionRepository)
    assert isinstance(entry._captures, SQLiteProductSnapshotCaptureRepository)
    assert isinstance(entry._prices, SQLitePriceAnalysisRepository)
    assert isinstance(entry._economics, SQLiteEconomicsCalculationOwnerRepository)
    assert isinstance(owner._repo, SQLiteSnapshotChainBindingRepository)
    assert isinstance(
        owner._id,
        ProductionSnapshotChainBindingIdentityGenerator,
    )
    assert owner._bound is not owner._committed
    assert owner._bound().tzinfo is not None
    assert owner._committed().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(path)}

    dependency.close()
    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_snapshot_chain_composition_failure_closes_open_resources(monkeypatch):
    closed = []

    class PromotionRepository:
        def __init__(self, path):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(web, "SQLiteCandidatePromotionRepository", PromotionRepository)
    monkeypatch.setattr(
        web,
        "SQLiteProductSnapshotCaptureRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_snapshot_chain_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


def test_snapshot_chain_api_persists_complete_ordered_exact_sources(tmp_path):
    path = tmp_path / "snapshot-chain-api.db"
    prepared, economics, economics_result = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    captured, analyzed, promoted, verified = prepared[6:10]
    chains = SQLiteSnapshotChainBindingRepository(path)
    client = use(production_entry(promotions, captures, prices, economics, chains))
    try:
        response = client.post("/api/v1/snapshot-chains", json=payload())

        assert response.status_code == 201
        body = response.json()
        assert body["command_id"] == "snapshot-chain-command-1"
        assert body["binding_id"] == "snapshot-chain-1"
        assert body["candidate_opportunity_binding_id"] == promoted.binding.binding_id
        assert body["candidate_id"] == promoted.binding.candidate_id
        assert body["opportunity_id"] == promoted.binding.opportunity_id
        assert body["chain_version"] == 1
        assert body["product_snapshot_ids"] == list(
            captured.receipt.product_snapshot_ids
        )
        assert body["price_snapshot_id"] == analyzed.snapshot.snapshot_id
        assert body["economics_snapshot_id"] == economics_result.snapshot.snapshot_id
        assert body["verified_economics_opportunity_id"] == verified.opportunity_id
        assert body["market_observation_identity"]["marketplace"] == "ebay"
        assert body["replayed"] is False
        assert body["aliased"] is False
        assert chain_counts(chains) == (1, 2, 1)
    finally:
        clear_overrides()
        close_prepared(prepared, economics, chains)


def test_snapshot_chain_api_exact_alias_and_restart_replay(tmp_path):
    path = tmp_path / "snapshot-chain-replay.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    identity = Counter("snapshot-chain-1")
    bound = Counter(BOUND_AT)
    committed = Counter(COMMITTED_AT)
    client = use(
        production_entry(
            promotions,
            captures,
            prices,
            economics,
            chains,
            binding_id_generator=identity,
            bound_clock=bound,
            receipt_clock=committed,
        )
    )
    try:
        first = client.post("/api/v1/snapshot-chains", json=payload())
        replay = client.post("/api/v1/snapshot-chains", json=payload())
        alias = client.post(
            "/api/v1/snapshot-chains",
            json=payload(command_id="snapshot-chain-command-2"),
        )

        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert alias.status_code == 200
        assert alias.json()["binding_id"] == first.json()["binding_id"]
        assert alias.json()["command_id"] == "snapshot-chain-command-2"
        assert alias.json()["replayed"] is False
        assert alias.json()["aliased"] is True
        assert identity.calls == bound.calls == committed.calls == 2
        assert chain_counts(chains) == (1, 2, 2)
    finally:
        clear_overrides()
        close_prepared(prepared, economics, chains)

    promotions = SQLiteCandidatePromotionRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    chains = SQLiteSnapshotChainBindingRepository(path)

    class Fail:
        def __call__(self):
            raise AssertionError("restart replay supplier must not run")

    client = use(
        production_entry(
            promotions,
            captures,
            prices,
            economics,
            chains,
            binding_id_generator=Fail(),
            bound_clock=Fail(),
            receipt_clock=Fail(),
        )
    )
    try:
        restarted = client.post("/api/v1/snapshot-chains", json=payload())
        assert restarted.status_code == 200
        assert restarted.json() == {**first.json(), "replayed": True}
        assert chain_counts(chains) == (1, 2, 2)
    finally:
        clear_overrides()
        chains.close()
        economics.close()
        prices.close()
        captures.close()
        promotions.close()


def test_snapshot_chain_api_changed_payload_conflicts_without_new_facts(tmp_path):
    path = tmp_path / "snapshot-chain-conflict.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    client = use(production_entry(promotions, captures, prices, economics, chains))
    try:
        first = client.post("/api/v1/snapshot-chains", json=payload())
        conflict = client.post(
            "/api/v1/snapshot-chains",
            json=payload(
                requested_at=(NOW + timedelta(minutes=46)).isoformat()
            ),
        )

        assert first.status_code == 201
        assert conflict.status_code == 409
        assert chain_counts(chains) == (1, 2, 1)
    finally:
        clear_overrides()
        close_prepared(prepared, economics, chains)


def test_snapshot_chain_api_missing_source_returns_not_found_without_writes(tmp_path):
    path = tmp_path / "snapshot-chain-missing.db"
    promotions = SQLiteCandidatePromotionRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    chains = SQLiteSnapshotChainBindingRepository(path)
    client = use(production_entry(promotions, captures, prices, economics, chains))
    try:
        response = client.post("/api/v1/snapshot-chains", json=payload())
        assert response.status_code == 404
        assert chain_counts(chains) == (0, 0, 0)
    finally:
        clear_overrides()
        chains.close()
        economics.close()
        prices.close()
        captures.close()
        promotions.close()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (SnapshotChainBindingNotFoundError("missing"), 404),
        (SnapshotChainIncompleteError("incomplete"), 404),
        (SnapshotChainMarketIdentityConflictError("conflict"), 409),
        (SnapshotChainBindingCommandConflictError("conflict"), 409),
        (sqlite3.OperationalError("unavailable"), 503),
        (ValueError("invalid"), 422),
    ),
)
def test_snapshot_chain_api_maps_application_failures(error, expected_status):
    class Entry:
        def execute(self, request):
            raise error

    client = use(Entry())
    try:
        response = client.post("/api/v1/snapshot-chains", json=payload())
        assert response.status_code == expected_status
    finally:
        clear_overrides()


def test_snapshot_chain_dependency_closes_on_application_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / "snapshot-chain-dependency-failure.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_snapshot_chain_entry()
    entry = next(dependency)
    repositories = (
        entry._sources,
        entry._captures,
        entry._prices,
        entry._economics,
        entry._bind._repo,
    )

    with pytest.raises(ValueError, match="failure"):
        dependency.throw(ValueError("failure"))

    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_snapshot_chain_request_is_strict_and_existing_apis_remain_registered():
    client = TestClient(app)
    response = client.post(
        "/api/v1/snapshot-chains",
        json=payload(unexpected="value"),
    )

    assert response.status_code == 422
    paths = {route.path for route in app.routes}
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
    assert "/api/v1/product-snapshots/capture" in paths
    assert "/api/v1/price-analyses" in paths
    assert "/api/v1/candidate-promotions" in paths
    assert "/api/v1/economics" in paths
    assert "/api/v1/snapshot-chains" in paths
