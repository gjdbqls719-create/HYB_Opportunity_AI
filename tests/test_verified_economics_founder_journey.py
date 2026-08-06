from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web
from app.infrastructure.discovery import SQLiteDiscoveryObservationRepository
from app.web import app, get_authoritative_discovery_entry
from tests.test_authoritative_discovery_api import payload as discovery_payload
from tests.test_candidate_issuance_api import payload as candidate_payload
from tests.test_candidate_promotion_api import payload as promotion_payload
from tests.test_discovery_execution_completion import close_all, sqlite_entry
from tests.test_discovery_phase_checkpoints import CheckpointRuntime
from tests.test_economics_api import payload as economics_payload
from tests.test_price_analysis_api import payload as price_payload
from tests.test_product_snapshot_capture_api import payload as product_payload
from tests.test_snapshot_chain_api import payload as snapshot_chain_payload
from tests.test_verified_economics_operational_admission import (
    payload as verified_economics_payload,
)


def _prepare_promoted_opportunity(client: TestClient, path) -> tuple[str, str]:
    entry, *repositories = sqlite_entry(path, CheckpointRuntime([]))
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    try:
        discovery = client.post(
            "/api/v1/discovery/executions",
            json=discovery_payload(),
        )
        assert discovery.status_code == 201
    finally:
        app.dependency_overrides.clear()
        close_all(*repositories)

    observations = SQLiteDiscoveryObservationRepository(path)
    try:
        representative = observations.get_observation("observation-one")
    finally:
        observations.close()
    assert representative is not None
    market_identity = {
        "scope": "listing",
        "market": "US",
        "marketplace": representative.source_marketplace,
        "canonical_product_id": None,
        "marketplace_item_id": representative.source_item_id,
        "normalized_query": None,
        "category": None,
        "variant_identity": None,
        "condition": representative.product.condition,
        "window_started_at": representative.observed_at.isoformat(),
        "window_ended_at": representative.observed_at.isoformat(),
    }
    candidate = client.post(
        "/api/v1/candidates",
        json=candidate_payload(
            finalized_group_id="group-1",
            discovery_reference="collector:ebay:one",
            market_observation_identity=market_identity,
        ),
    )
    assert candidate.status_code == 201
    candidate_id = candidate.json()["candidate_id"]
    candidate_market_identity = candidate.json()["market_observation_identity"]

    captured = client.post(
        "/api/v1/product-snapshots/capture",
        json=product_payload(
            candidate_id=candidate_id,
            finalized_group_id="group-1",
        ),
    )
    assert captured.status_code == 201
    analyzed = client.post(
        "/api/v1/price-analyses",
        json=price_payload(
            candidate_id=candidate_id,
            finalized_group_id="group-1",
        ),
    )
    assert analyzed.status_code == 201
    promoted = client.post(
        "/api/v1/candidate-promotions",
        json=promotion_payload(candidate_id=candidate_id),
    )
    assert promoted.status_code == 201
    assert (
        promoted.json()["market_observation_identity"]
        == candidate_market_identity
    )
    return candidate_id, promoted.json()["opportunity_id"]


def _table_count(path, table: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


def test_promoted_opportunity_verified_economics_to_snapshot_chain_journey(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "founder-verified-economics.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)

    with TestClient(app) as client:
        candidate_id, opportunity_id = _prepare_promoted_opportunity(client, path)
        economics_request = economics_payload(opportunity_id=opportunity_id)
        upstream_counts = tuple(
            _table_count(path, table)
            for table in (
                "opportunity_candidate_history",
                "product_observation_snapshot_history",
                "price_intelligence_snapshot_history",
                "opportunity_candidate_promotion_history",
            )
        )

        readiness_before = client.get(
            f"/api/v1/opportunities/{opportunity_id}/decision-readiness"
        )
        missing = client.post("/api/v1/economics", json=economics_request)
        assert readiness_before.status_code == 200
        assert (
            readiness_before.json()["sources"]["verified_economics"]["status"]
            == "missing"
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Verified Economics source is missing"
        assert _table_count(path, "economics_calculation_snapshot_history") == 0

        request = verified_economics_payload()
        fresh = client.post(
            f"/api/v1/opportunities/{opportunity_id}/verified-economics",
            json=request,
        )
        replay = client.post(
            f"/api/v1/opportunities/{opportunity_id}/verified-economics",
            json=request,
        )
        changed = verified_economics_payload()
        changed["purchase_cost"]["amount"] = "999.00"
        conflict = client.post(
            f"/api/v1/opportunities/{opportunity_id}/verified-economics",
            json=changed,
        )
        wrong_opportunity = client.post(
            "/api/v1/opportunities/missing-opportunity/verified-economics",
            json=verified_economics_payload("wrong-opportunity-command"),
        )

        assert fresh.status_code == 201
        assert fresh.json()["opportunity_id"] == opportunity_id
        assert replay.status_code == 200
        assert replay.json() == fresh.json()
        assert conflict.status_code == 409
        assert wrong_opportunity.status_code == 404
        assert _table_count(path, "verified_economics_snapshots") == 1
        assert _table_count(path, "verified_economics_admission_receipts") == 1

        readiness_after = client.get(
            f"/api/v1/opportunities/{opportunity_id}/decision-readiness"
        )
        assert readiness_after.status_code == 200
        assert (
            readiness_after.json()["sources"]["verified_economics"]["status"]
            == "ready"
        )

        economics = client.post("/api/v1/economics", json=economics_request)
        economics_replay = client.post(
            "/api/v1/economics",
            json=economics_request,
        )
        assert economics.status_code == 201
        assert economics_replay.status_code == 200
        assert economics_replay.json() | {"replayed": False} == economics.json()
        assert economics.json()["candidate_id"] == candidate_id
        assert economics.json()["opportunity_id"] == opportunity_id
        assert (
            economics.json()["verified_economics_opportunity_id"]
            == opportunity_id
        )

        chain_request = snapshot_chain_payload(opportunity_id=opportunity_id)
        chain = client.post("/api/v1/snapshot-chains", json=chain_request)
        chain_replay = client.post("/api/v1/snapshot-chains", json=chain_request)
        assert chain.status_code == 201
        assert chain_replay.status_code == 200
        assert chain_replay.json() | {"replayed": False} == chain.json()
        assert chain.json()["candidate_id"] == candidate_id
        assert chain.json()["opportunity_id"] == opportunity_id
        assert chain.json()["economics_snapshot_id"] == economics.json()[
            "economics_snapshot_id"
        ]
        assert chain.json()["verified_economics_opportunity_id"] == opportunity_id

    assert _table_count(path, "economics_calculation_snapshot_history") == 1
    assert _table_count(path, "economics_calculation_receipts") == 1
    assert _table_count(path, "opportunity_snapshot_chain_binding_history") == 1
    assert tuple(
        _table_count(path, table)
        for table in (
            "opportunity_candidate_history",
            "product_observation_snapshot_history",
            "price_intelligence_snapshot_history",
            "opportunity_candidate_promotion_history",
        )
    ) == upstream_counts
