from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_validation_queue_repository


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


@pytest.fixture
def api_repository():
    repository = SQLiteValidationQueueRepository(":memory:")
    app.dependency_overrides[get_validation_queue_repository] = lambda: repository
    try:
        yield repository
    finally:
        app.dependency_overrides.clear()
        repository.close()


@pytest.fixture
def client(api_repository):
    return TestClient(app)


def admission_payload(opportunity_id="opp-api"):
    return {
        "opportunity_id": opportunity_id,
        "discovery_reference": "ebay:item-api",
        "marketplace": "ebay",
        "title": "API Camera",
        "admission_recommendation": "WATCH",
        "admission_score": 68.0,
        "admission_roi": 22.5,
        "currency": "USD",
        "admission_safety_status": "READY",
        "operator_id": "founder",
        "reason": "selected",
        "captured_at": NOW.isoformat(),
    }


def action_payload(version, minute):
    return {
        "expected_version": version,
        "operator_id": "founder",
        "reason": "manual validation",
        "occurred_at": NOW.replace(minute=minute).isoformat(),
    }


def test_additive_api_adds_and_lists_selected_item(client) -> None:
    added = client.post("/api/v1/validation-queue", json=admission_payload())
    assert added.status_code == 201
    assert added.json()["lifecycle_status"] == "discovered"
    listed = client.get("/api/v1/validation-queue")
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 1
    assert listed.json()["items"][0]["opportunity_id"] == "opp-api"


def test_additive_api_review_approve_return_and_reject(client) -> None:
    client.post("/api/v1/validation-queue", json=admission_payload())
    reviewed = client.post("/api/v1/validation-queue/opp-api/review", json=action_payload(1, 1))
    assert reviewed.status_code == 200
    approved = client.post("/api/v1/validation-queue/opp-api/approve", json=action_payload(2, 2))
    assert approved.json()["founder_decision"]["decision"] == "approve"
    returned = client.post("/api/v1/validation-queue/opp-api/return-to-review", json=action_payload(3, 3))
    assert returned.json()["lifecycle_status"] == "under_review"
    rejected = client.post("/api/v1/validation-queue/opp-api/reject", json=action_payload(4, 4))
    assert rejected.json()["founder_decision"]["decision"] == "reject"


def test_search_does_not_automatically_register_lifecycle(client, api_repository, monkeypatch) -> None:
    monkeypatch.setattr("app.web.find_best_opportunities", lambda **kwargs: [])
    response = client.post("/api/v1/opportunities/search", json={"query": "camera"})
    assert response.status_code == 200
    assert api_repository.list_queue(statuses=(), limit=10) == ()
    count = api_repository._connection.execute(
        "SELECT COUNT(*) FROM opportunity_lifecycles"
    ).fetchone()[0]
    assert count == 0


def test_duplicate_and_stale_version_map_to_conflict(client) -> None:
    assert client.post("/api/v1/validation-queue", json=admission_payload()).status_code == 201
    duplicate = admission_payload("opp-other")
    assert client.post("/api/v1/validation-queue", json=duplicate).status_code == 409
    stale = client.post("/api/v1/validation-queue/opp-api/review", json=action_payload(99, 1))
    assert stale.status_code == 409


def test_return_to_review_duplicate_maps_to_explicit_conflict(client, api_repository) -> None:
    client.post("/api/v1/validation-queue", json=admission_payload())
    client.post("/api/v1/validation-queue/opp-api/review", json=action_payload(1, 1))
    client.post("/api/v1/validation-queue/opp-api/approve", json=action_payload(2, 2))
    api_repository._connection.execute("DROP INDEX uq_active_validation_discovery_reference")
    api_repository._connection.execute(
        """INSERT INTO opportunity_lifecycles
        (opportunity_id, discovery_reference, status, version, created_at, updated_at,
         archived_at, archived_by, archive_reason)
        VALUES ('legacy-duplicate', 'ebay:item-api', 'discovered', 1, ?, ?, NULL, NULL, NULL)""",
        (NOW.isoformat(), NOW.isoformat()),
    )
    api_repository._connection.commit()
    response = client.post(
        "/api/v1/validation-queue/opp-api/return-to-review",
        json=action_payload(3, 3),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "duplicate non-archived validation exists"
