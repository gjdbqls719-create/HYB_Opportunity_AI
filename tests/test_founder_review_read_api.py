from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from app.application.review import (
    ReviewSessionPersistenceError,
    ReviewSessionQueryService,
    ReviewTransitionMetadata,
)
from app.domain.market_intelligence import ReviewSession, ReviewSessionStatus
from app.infrastructure.review import SQLiteReviewSessionRepository
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_review_session_query_service


NOW = datetime(2026, 8, 16, 9, tzinfo=timezone.utc)


def session(session_id="review-1") -> ReviewSession:
    return ReviewSession(
        session_id=session_id,
        artifact_id=f"artifact-{session_id}",
        candidate_ids=(f"{session_id}-candidate-1", f"{session_id}-candidate-2"),
        status=ReviewSessionStatus.OPEN,
        created_at=NOW,
        completed_at=None,
        operator_id="founder-1",
        schema_version="review-session-v1",
    )


def metadata(session_id="review-1") -> ReviewTransitionMetadata:
    return ReviewTransitionMetadata(
        event_id=f"event-{session_id}",
        command_id=f"command-{session_id}",
        transition_type="create",
        occurred_at=NOW,
        command_fingerprint=f"fingerprint-{session_id}",
    )


def table_state(path) -> tuple[tuple[str, int], ...]:
    connection = sqlite3.connect(path)
    names = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    result = tuple(
        (name, connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        for name in names
    )
    assert not connection.in_transaction
    connection.close()
    return result


def client_for(path):
    def dependency():
        repository = SQLiteReviewSessionRepository(path)
        try:
            yield ReviewSessionQueryService(repository)
            assert not repository._connection.in_transaction
        finally:
            repository.close()

    app.dependency_overrides[get_review_session_query_service] = dependency
    return TestClient(app)


def test_list_and_detail_use_deterministic_dto_serialization(tmp_path) -> None:
    path = tmp_path / "reviews.db"
    repository = SQLiteReviewSessionRepository(path)
    repository.create(session("review-2"), metadata("review-2"))
    repository.create(session("review-1"), metadata("review-1"))
    repository.close()
    client = client_for(path)
    try:
        first = client.get("/api/v1/reviews")
        repeated = client.get("/api/v1/reviews")
        detail = client.get("/api/v1/reviews/review-1")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == repeated.status_code == detail.status_code == 200
    assert first.json() == repeated.json()
    assert [item["session_id"] for item in first.json()["items"]] == [
        "review-1",
        "review-2",
    ]
    assert first.json()["total_count"] == 2
    assert detail.json() == {
        "session_id": "review-1",
        "status": "open",
        "revision": 1,
        "candidate_count": 2,
        "pending_count": 2,
        "completed_count": 0,
        "created_at": NOW.isoformat(),
        "started_at": None,
        "completed_at": None,
        "schema_version": "review-session-v1",
    }


def test_get_requests_are_read_only_across_all_persisted_areas(tmp_path) -> None:
    path = tmp_path / "read-only.db"
    review_persistence = SQLiteVerifiedSignalPersistence(path)
    review_persistence.sessions.create(session(), metadata())
    review_persistence.close()
    lifecycle_repository = SQLiteValidationQueueRepository(path)
    lifecycle_repository.close()
    before = table_state(path)
    client = client_for(path)
    try:
        assert client.get("/api/v1/reviews").status_code == 200
        assert client.get("/api/v1/reviews/review-1").status_code == 200
    finally:
        app.dependency_overrides.clear()
    after = table_state(path)

    assert before == after
    names = {name for name, _ in after}
    assert {
        "review_session_history",
        "review_session_current",
        "review_command_receipts",
        "human_verification_history",
        "human_verification_current",
        "market_observation_history",
        "market_observation_current",
        "opportunity_lifecycles",
        "opportunity_lifecycle_transitions",
    } <= names


def test_missing_session_maps_to_404(tmp_path) -> None:
    path = tmp_path / "missing.db"
    SQLiteReviewSessionRepository(path).close()
    client = client_for(path)
    try:
        response = client.get("/api/v1/reviews/missing")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


class FailingQueryService:
    def list(self, query):
        raise ReviewSessionPersistenceError("review storage unavailable")

    def get(self, query):
        raise ReviewSessionPersistenceError("review storage unavailable")


def test_persistence_failures_map_to_503() -> None:
    app.dependency_overrides[get_review_session_query_service] = lambda: FailingQueryService()
    try:
        client = TestClient(app)
        listed = client.get("/api/v1/reviews")
        detail = client.get("/api/v1/reviews/review-1")
    finally:
        app.dependency_overrides.clear()
    assert listed.status_code == detail.status_code == 503
    assert listed.json()["detail"] == "review storage unavailable"
