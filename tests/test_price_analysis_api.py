from datetime import timedelta
from decimal import Decimal
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.price_analysis import CandidatePriceAnalysisProductionEntry
from app.domain.market_intelligence import MarketObservationScope
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.price_intelligence import (
    ProductionPriceSnapshotIdentityGenerator,
    SQLitePriceAnalysisRepository,
)
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.web import app, get_candidate_price_analysis_entry
import app.web as web
from engine.price_intelligence import analyze_product_prices
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_price_analysis_production_entry import (
    COMMITTED_AT,
    GENERATED_AT,
    analysis_counts,
    analysis_entry,
    request,
)
from test_candidate_issuance_production_entry import Fail
from test_discovery_correlation_contract import NOW, market_identity
from test_product_snapshot_capture_production_entry import (
    capture_request,
    close_all,
    prepare,
    production_entry as capture_entry,
)


def payload(**changes):
    value = {
        "command_id": "price-analysis-command-1",
        "candidate_id": "candidate-1",
        "finalized_group_id": "group-opaque-1",
        "product_snapshot_capture_command_id": "capture-command-1",
        "fallback_multiplier": "1.50",
        "analyzer_version": "price-analyzer-v1",
        "requested_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_candidate_price_analysis_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def prepare_analysis_sources(path, scope=MarketObservationScope.LISTING):
    identity = market_identity(scope)
    sources, candidates, issuance, _, _ = prepare(
        path,
        candidate_market_identity=identity,
        second_marketplace="amazon",
    )
    captures = SQLiteProductSnapshotCaptureRepository(path)
    captured = capture_entry(
        candidates,
        sources[2],
        captures,
        Counter(ISSUED_AT),
    ).execute(capture_request(issuance))
    return sources, candidates, captures, issuance, captured


def test_price_analysis_composition_uses_production_owners_and_closes_scope(
    tmp_path, monkeypatch
):
    path = tmp_path / "price-analysis-api.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_candidate_price_analysis_entry()
    entry = next(dependency)
    owner = entry._analyze
    repositories = (entry._candidates, entry._captures, owner._repository)

    assert isinstance(entry, CandidatePriceAnalysisProductionEntry)
    assert isinstance(entry._candidates, SQLiteCandidateIssuanceRepository)
    assert isinstance(entry._captures, SQLiteProductSnapshotCaptureRepository)
    assert isinstance(owner._repository, SQLitePriceAnalysisRepository)
    assert isinstance(
        owner._snapshot_id_generator,
        ProductionPriceSnapshotIdentityGenerator,
    )
    assert owner._analyzer is analyze_product_prices
    assert owner._generated_clock is not owner._receipt_clock
    assert owner._generated_clock().tzinfo is not None
    assert owner._receipt_clock().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(path)}

    dependency.close()
    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_price_analysis_composition_failure_closes_open_resources(monkeypatch):
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

    monkeypatch.setattr(web, "SQLiteCandidateIssuanceRepository", FirstRepository)
    monkeypatch.setattr(
        web,
        "SQLiteProductSnapshotCaptureRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_candidate_price_analysis_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.LISTING, MarketObservationScope.CANONICAL_PRODUCT),
)
def test_price_analysis_api_persists_ordered_listing_and_canonical_result(
    tmp_path, scope
):
    path = tmp_path / f"price-analysis-{scope.value}.db"
    sources, candidates, captures, issuance, captured = prepare_analysis_sources(
        path, scope
    )
    analyses = SQLitePriceAnalysisRepository(path)
    seen = []

    def analyzer(products, *, fallback_multiplier):
        seen.append((tuple(products), fallback_multiplier))
        return analyze_product_prices(
            products,
            fallback_multiplier=fallback_multiplier,
        )

    entry = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=Counter("price-snapshot-1"),
        generated_clock=Counter(GENERATED_AT),
        receipt_clock=Counter(COMMITTED_AT),
        analyzer=analyzer,
    )
    client = use(entry)
    try:
        response = client.post("/api/v1/price-analyses", json=payload())

        assert response.status_code == 201
        body = response.json()
        assert len(seen) == 1
        assert seen[0][1] == Decimal("1.50")
        assert body["candidate_id"] == issuance.candidate_identity.candidate_id
        assert body["finalized_group_id"] == issuance.finalized_group_id
        assert body["price_snapshot_id"] == "price-snapshot-1"
        assert body["product_snapshot_ids"] == list(
            captured.receipt.product_snapshot_ids
        )
        assert body["market_observation_identity"]["scope"] == scope.value
        assert body["analyzer_version"] == "price-analyzer-v1"
        assert body["fallback_multiplier"] == "1.50"
        assert body["sample_size"] == 2
        persisted = analyses.get_result(
            analyses.get_receipt("price-analysis-command-1")
        )
        assert persisted.snapshot.snapshot_id == body["price_snapshot_id"]
        assert persisted.snapshot.product_observation_snapshot_ids == (
            "product-snapshot-1",
            "product-snapshot-2",
        )
        assert analysis_counts(analyses) == (1, 1)
    finally:
        clear_overrides()
        analyses.close()
        captures.close()
        candidates.close()
        close_all(*sources)


def test_price_analysis_api_exact_and_restart_replay_skip_owner_dependencies(
    tmp_path,
):
    path = tmp_path / "price-analysis-replay.db"
    sources, candidates, captures, issuance, _ = prepare_analysis_sources(path)
    analyses = SQLitePriceAnalysisRepository(path)
    snapshot_id = Counter("price-snapshot-1")
    generated_clock = Counter(GENERATED_AT)
    receipt_clock = Counter(COMMITTED_AT)
    analyzer_calls = []

    def analyzer(products, *, fallback_multiplier):
        analyzer_calls.append(True)
        return analyze_product_prices(
            products,
            fallback_multiplier=fallback_multiplier,
        )

    entry = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=snapshot_id,
        generated_clock=generated_clock,
        receipt_clock=receipt_clock,
        analyzer=analyzer,
    )
    client = use(entry)
    try:
        first = client.post("/api/v1/price-analyses", json=payload())
        replay = client.post("/api/v1/price-analyses", json=payload())

        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert snapshot_id.calls == generated_clock.calls == receipt_clock.calls == 1
        assert len(analyzer_calls) == 1
    finally:
        clear_overrides()
        analyses.close()
        captures.close()
        candidates.close()
        close_all(*sources)

    candidates = SQLiteCandidateIssuanceRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    analyses = SQLitePriceAnalysisRepository(path)
    dependencies = tuple(Fail() for _ in range(4))
    restarted = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=dependencies[0],
        generated_clock=dependencies[1],
        receipt_clock=dependencies[2],
        analyzer=dependencies[3],
    )
    client = use(restarted)
    try:
        response = client.post("/api/v1/price-analyses", json=payload())

        assert response.status_code == 200
        assert response.json() == {**first.json(), "replayed": True}
        assert all(value.calls == 0 for value in dependencies)
        assert analysis_counts(analyses) == (1, 1)
    finally:
        clear_overrides()
        analyses.close()
        captures.close()
        candidates.close()


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("fallback_multiplier", "1.75"),
        ("analyzer_version", "price-analyzer-v2"),
    ),
)
def test_price_analysis_api_changed_payload_conflicts_without_new_facts(
    tmp_path, change, value
):
    path = tmp_path / f"price-analysis-{change}.db"
    sources, candidates, captures, issuance, _ = prepare_analysis_sources(path)
    analyses = SQLitePriceAnalysisRepository(path)
    client = use(analysis_entry(candidates, captures, analyses))
    try:
        first = client.post("/api/v1/price-analyses", json=payload())
        conflict = client.post(
            "/api/v1/price-analyses",
            json=payload(**{change: value}),
        )

        assert first.status_code == 201
        assert conflict.status_code == 409
        assert analysis_counts(analyses) == (1, 1)
    finally:
        clear_overrides()
        analyses.close()
        captures.close()
        candidates.close()
        close_all(*sources)


def test_price_analysis_api_request_is_strict_and_existing_apis_remain_registered():
    client = TestClient(app)

    response = client.post(
        "/api/v1/price-analyses",
        json=payload(unexpected="value"),
    )

    assert response.status_code == 422
    paths = {route.path for route in app.routes}
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
    assert "/api/v1/product-snapshots/capture" in paths
    assert "/api/v1/price-analyses" in paths
