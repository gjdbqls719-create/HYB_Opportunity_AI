from datetime import timedelta
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.economics_calculation_owner import (
    EconomicsCalculationCommandConflictError,
    EconomicsCalculationSourceNotFoundError,
    EconomicsSnapshotProductionEntry,
)
from app.infrastructure.economics_calculation import (
    ProductionEconomicsSnapshotIdentityGenerator,
    SQLiteEconomicsCalculationOwnerRepository,
)
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from app.web import app, get_economics_snapshot_entry
import app.web as web
from engine.opportunity import calculate_verified_economics
from test_candidate_issuance_foundation import Counter
from test_candidate_issuance_production_entry import Fail
from test_discovery_correlation_contract import NOW
from test_economics_snapshot_production_entry import (
    ECONOMICS_COMMITTED_AT,
    ECONOMICS_GENERATED_AT,
    close_sources,
    economics_counts,
    prepare_persisted_sources,
    production_entry,
)


def payload(**changes):
    value = {
        "command_id": "economics-command-1",
        "opportunity_id": "opportunity-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "calculation_parameters": {
            "marketplace": "ebay",
            "minimum_net_profit": "20",
            "minimum_roi": "15",
            "estimated_monthly_sales": 10,
            "competitor_count": 3,
            "risk_level": "low",
            "context_items": [["category", "camera"]],
        },
        "calculation_version": "verified-economics-calculator-v1",
        "requested_at": (NOW + timedelta(minutes=30)).isoformat(),
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_economics_snapshot_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_economics_composition_uses_production_dependencies_and_closes_scope(
    tmp_path, monkeypatch
):
    path = tmp_path / "economics-composition.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_economics_snapshot_entry()
    entry = next(dependency)
    owner = entry._calculate
    repositories = (entry._promotions, entry._prices, owner._repository)

    assert isinstance(entry, EconomicsSnapshotProductionEntry)
    assert isinstance(entry._promotions, SQLiteCandidatePromotionRepository)
    assert isinstance(entry._prices, SQLitePriceAnalysisRepository)
    assert isinstance(owner._repository, SQLiteEconomicsCalculationOwnerRepository)
    assert isinstance(owner._id, ProductionEconomicsSnapshotIdentityGenerator)
    assert owner._calculator is calculate_verified_economics
    assert owner._generated is not owner._committed
    assert owner._generated().tzinfo is not None
    assert owner._committed().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(path)}

    dependency.close()
    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_economics_composition_failure_closes_open_resources(monkeypatch):
    closed = []

    class PromotionRepository:
        def __init__(self, path):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(web, "SQLiteCandidatePromotionRepository", PromotionRepository)
    monkeypatch.setattr(
        web,
        "SQLitePriceAnalysisRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_economics_snapshot_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


def test_economics_api_persists_authoritative_sources_and_result(tmp_path):
    path = tmp_path / "economics-api.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    analyzed, promoted, verified = prepared[7], prepared[8], prepared[9]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    seen = []

    def calculator(**kwargs):
        seen.append(kwargs)
        return calculate_verified_economics(**kwargs)

    entry = production_entry(
        promotions,
        prices,
        economics,
        calculator=calculator,
    )
    client = use(entry)
    try:
        response = client.post("/api/v1/economics", json=payload())

        assert response.status_code == 201
        body = response.json()
        assert len(seen) == 1
        assert seen[0]["economics"] == verified.inputs
        assert body["command_id"] == "economics-command-1"
        assert body["opportunity_id"] == promoted.item.opportunity_id
        assert body["candidate_id"] == promoted.binding.candidate_id
        assert body["candidate_opportunity_binding_id"] == promoted.binding.binding_id
        assert body["price_analysis_command_id"] == analyzed.receipt.command_id
        assert body["price_intelligence_snapshot_id"] == analyzed.snapshot.snapshot_id
        assert body["verified_economics_opportunity_id"] == verified.opportunity_id
        assert body["economics_snapshot_id"] == "economics-snapshot-1"
        assert body["calculation_parameters"] == payload()["calculation_parameters"]
        assert body["currency"] == "USD"
        assert body["replayed"] is False
        assert economics_counts(economics) == (1, 1)
    finally:
        clear_overrides()
        close_sources(sources, candidates, captures, prices, promotions, economics)


def test_economics_api_exact_and_restart_replay_skips_owner_dependencies(tmp_path):
    path = tmp_path / "economics-replay.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    snapshot_id = Counter("economics-snapshot-1")
    generated = Counter(ECONOMICS_GENERATED_AT)
    committed = Counter(ECONOMICS_COMMITTED_AT)
    calculator_calls = []

    def calculator(**kwargs):
        calculator_calls.append(True)
        return calculate_verified_economics(**kwargs)

    client = use(
        production_entry(
            promotions,
            prices,
            economics,
            snapshot_id_generator=snapshot_id,
            generated_clock=generated,
            receipt_clock=committed,
            calculator=calculator,
        )
    )
    try:
        first = client.post("/api/v1/economics", json=payload())
        replay = client.post("/api/v1/economics", json=payload())

        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert snapshot_id.calls == generated.calls == committed.calls == 1
        assert len(calculator_calls) == 1
    finally:
        clear_overrides()
        close_sources(sources, candidates, captures, prices, promotions, economics)

    promotions = SQLiteCandidatePromotionRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    dependencies = tuple(Fail() for _ in range(4))
    restarted = EconomicsSnapshotProductionEntry(
        promotion_repository=promotions,
        price_analysis_repository=prices,
        economics_repository=economics,
        snapshot_id_generator=dependencies[0],
        generated_clock=dependencies[1],
        receipt_clock=dependencies[2],
        calculator=dependencies[3],
    )
    client = use(restarted)
    try:
        replay = client.post("/api/v1/economics", json=payload())
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert tuple(value.calls for value in dependencies) == (0, 0, 0, 0)
        assert economics_counts(economics) == (1, 1)
    finally:
        clear_overrides()
        economics.close()
        prices.close()
        promotions.close()


def test_economics_api_changed_payload_conflicts_without_new_facts(tmp_path):
    path = tmp_path / "economics-conflict.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    client = use(production_entry(promotions, prices, economics))
    try:
        first = client.post("/api/v1/economics", json=payload())
        conflict = client.post(
            "/api/v1/economics",
            json=payload(calculation_version="changed"),
        )

        assert first.status_code == 201
        assert conflict.status_code == 409
        assert economics_counts(economics) == (1, 1)
    finally:
        clear_overrides()
        close_sources(sources, candidates, captures, prices, promotions, economics)


def test_economics_api_missing_source_returns_not_found_without_writes(tmp_path):
    path = tmp_path / "economics-missing.db"
    promotions = SQLiteCandidatePromotionRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    client = use(production_entry(promotions, prices, economics))
    try:
        response = client.post("/api/v1/economics", json=payload())
        assert response.status_code == 404
        assert economics_counts(economics) == (0, 0)
    finally:
        clear_overrides()
        economics.close()
        prices.close()
        promotions.close()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (EconomicsCalculationSourceNotFoundError("missing"), 404),
        (EconomicsCalculationCommandConflictError("conflict"), 409),
        (sqlite3.OperationalError("unavailable"), 503),
        (ValueError("invalid"), 422),
    ),
)
def test_economics_api_maps_application_failures(error, expected_status):
    class Entry:
        def execute(self, request):
            raise error

    client = use(Entry())
    try:
        response = client.post("/api/v1/economics", json=payload())
        assert response.status_code == expected_status
    finally:
        clear_overrides()


def test_economics_dependency_closes_on_application_failure(tmp_path, monkeypatch):
    path = tmp_path / "economics-dependency-failure.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_economics_snapshot_entry()
    entry = next(dependency)
    repositories = (entry._promotions, entry._prices, entry._calculate._repository)

    with pytest.raises(ValueError, match="failure"):
        dependency.throw(ValueError("failure"))

    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_economics_request_is_strict_and_existing_apis_remain_registered():
    client = TestClient(app)
    response = client.post("/api/v1/economics", json=payload(unexpected="value"))

    assert response.status_code == 422
    paths = {route.path for route in app.routes}
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
    assert "/api/v1/product-snapshots/capture" in paths
    assert "/api/v1/price-analyses" in paths
    assert "/api/v1/candidate-promotions" in paths
    assert "/api/v1/economics" in paths
