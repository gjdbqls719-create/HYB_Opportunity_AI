from datetime import timedelta
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.product_snapshot_capture import (
    CandidateProductSnapshotCaptureProductionEntry,
)
from app.domain.market_intelligence import MarketObservationScope
from app.infrastructure.discovery import (
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryGroupRepository,
)
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.web import app, get_product_snapshot_capture_entry
import app.web as web
from test_candidate_issuance_foundation import (
    Counter,
    ISSUED_AT,
    issuance_command,
)
from test_candidate_issuance_production_entry import Fail
from test_discovery_correlation_contract import NOW, market_identity
from test_product_snapshot_capture_production_entry import (
    capture_counts,
    close_all,
    prepare,
    production_entry,
)


def payload(**changes):
    value = {
        "command_id": "capture-command-1",
        "candidate_id": "candidate-1",
        "finalized_group_id": "group-opaque-1",
        "product_snapshot_ids": [
            "product-snapshot-1",
            "product-snapshot-2",
        ],
        "requested_at": (NOW + timedelta(minutes=3)).isoformat(),
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_product_snapshot_capture_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_product_snapshot_composition_uses_existing_owners_and_closes_scope(
    tmp_path, monkeypatch
):
    path = tmp_path / "product-snapshot-api.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_product_snapshot_capture_entry()
    entry = next(dependency)
    capture_owner = entry._capture
    repositories = (
        entry._candidates,
        entry._groups,
        capture_owner._repository,
    )

    assert isinstance(entry, CandidateProductSnapshotCaptureProductionEntry)
    assert isinstance(entry._candidates, SQLiteCandidateIssuanceRepository)
    assert isinstance(entry._groups, SQLiteDiscoveryGroupRepository)
    assert isinstance(
        capture_owner._repository,
        SQLiteProductSnapshotCaptureRepository,
    )
    assert not hasattr(entry, "_snapshot_id_generator")
    assert not hasattr(capture_owner, "_snapshot_id_generator")
    assert capture_owner._receipt_clock().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(path)}

    dependency.close()
    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_product_snapshot_composition_failure_closes_open_resources(monkeypatch):
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
        "SQLiteDiscoveryGroupRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_product_snapshot_capture_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


def test_product_snapshot_api_captures_ordered_listing_cohort(tmp_path):
    scope = MarketObservationScope.LISTING
    path = tmp_path / f"capture-{scope.value}.db"
    identity = issuance_command().market_observation_identity
    sources, candidates, issuance, first, second = prepare(
        path,
        candidate_market_identity=identity,
        second_marketplace="amazon",
    )
    captures = SQLiteProductSnapshotCaptureRepository(path)
    entry = production_entry(
        candidates,
        sources[2],
        captures,
        Counter(ISSUED_AT + timedelta(minutes=1)),
    )
    client = use(entry)
    try:
        response = client.post(
            "/api/v1/product-snapshots/capture",
            json=payload(candidate_id=issuance.candidate_identity.candidate_id),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["candidate_id"] == issuance.candidate_identity.candidate_id
        assert body["finalized_group_id"] == issuance.finalized_group_id
        assert body["market_observation_identity"]["scope"] == scope.value
        assert body["product_snapshot_ids"] == [
            "product-snapshot-1",
            "product-snapshot-2",
        ]
        assert [
            binding["collected_observation_id"]
            for binding in body["source_bindings"]
        ] == ["observation-1", "observation-2"]
        persisted = captures.get_result(
            captures.get_receipt("capture-command-1")
        )
        assert tuple(snapshot.product for snapshot in persisted.snapshots) == (
            first.product,
            second.product,
        )
        assert tuple(
            snapshot.market_observation_identity
            for snapshot in persisted.snapshots
        ) == (identity, identity)
        assert capture_counts(captures) == (2, 2, 1)
    finally:
        clear_overrides()
        captures.close()
        candidates.close()
        close_all(*sources)


def test_product_snapshot_api_exact_replay_reconstructs_after_restart_without_clock(
    tmp_path,
):
    path = tmp_path / "capture-replay.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    client = use(
        production_entry(
            candidates,
            sources[2],
            captures,
            Counter(ISSUED_AT),
        )
    )
    try:
        first = client.post("/api/v1/product-snapshots/capture", json=payload())
    finally:
        clear_overrides()
        captures.close()
        candidates.close()
        close_all(*sources)

    candidates = SQLiteCandidateIssuanceRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    clock = Fail("capture replay clock must not run")
    client = use(production_entry(candidates, groups, captures, clock))
    try:
        replay = client.post("/api/v1/product-snapshots/capture", json=payload())

        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert clock.calls == 0
        assert capture_counts(captures) == (2, 2, 1)
    finally:
        clear_overrides()
        captures.close()
        groups.close()
        candidates.close()


def test_product_snapshot_api_changed_payload_conflicts_without_new_facts(tmp_path):
    path = tmp_path / "capture-conflict.db"
    sources, candidates, _, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    client = use(
        production_entry(
            candidates,
            sources[2],
            captures,
            Counter(ISSUED_AT),
        )
    )
    try:
        first = client.post("/api/v1/product-snapshots/capture", json=payload())
        conflict = client.post(
            "/api/v1/product-snapshots/capture",
            json=payload(
                product_snapshot_ids=[
                    "product-snapshot-2",
                    "product-snapshot-1",
                ]
            ),
        )

        assert first.status_code == 201
        assert conflict.status_code == 409
        assert capture_counts(captures) == (2, 2, 1)
    finally:
        clear_overrides()
        captures.close()
        candidates.close()
        close_all(*sources)


def test_product_snapshot_api_request_is_strict_and_existing_apis_remain_registered():
    client = TestClient(app)

    response = client.post(
        "/api/v1/product-snapshots/capture",
        json=payload(unexpected="value"),
    )

    assert response.status_code == 422
    paths = {route.path for route in app.routes}
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
    assert "/api/v1/product-snapshots/capture" in paths
