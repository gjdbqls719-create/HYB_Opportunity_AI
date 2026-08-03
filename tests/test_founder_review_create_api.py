from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from app.application.review import ReviewWorkflowService
from app.infrastructure.review import SQLiteReviewSessionRepository, SQLiteVerifiedSignalPersistence
from app.web import app, get_review_workflow_service
from tests.test_review_session_persistence import candidate


NOW = datetime(2026, 8, 18, 9, tzinfo=timezone.utc)


def client_for(path) -> TestClient:
    def dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try:
            yield ReviewWorkflowService(persistence.ledger, persistence=persistence)
            assert not persistence._connection.in_transaction
        finally:
            persistence.close()

    app.dependency_overrides[get_review_workflow_service] = dependency
    return TestClient(app)


def seed_candidate(path) -> None:
    persistence = SQLiteVerifiedSignalPersistence(path)
    try:
        persistence.ledger.save_candidate(candidate())
    finally:
        persistence.close()


def request_body(**changes):
    body = {
        "session_id": "review-1",
        "artifact_id": "artifact-1",
        "candidate_ids": ["candidate-1"],
        "operator_id": "founder-1",
        "created_at": NOW.isoformat(),
        "command_id": "create-review-1",
        "contexts": [
            {
                "candidate_id": "candidate-1",
                "market_observation_identity": {
                    "scope": "search_query",
                    "market": "KR",
                    "marketplace": "coupang",
                    "canonical_product_id": None,
                    "marketplace_item_id": None,
                    "normalized_query": "mouse",
                    "category": "electronics",
                    "variant_identity": None,
                    "condition": "new",
                    "window_started_at": NOW.isoformat(),
                    "window_ended_at": NOW.isoformat(),
                },
                "signal_name": "search volume",
                "signal_direction": "positive",
                "artifact_identity": "artifact-1",
                "created_at": NOW.isoformat(),
            }
        ],
    }
    body.update(changes)
    return body


def counts(path):
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "review_session_history",
                "review_session_current",
                "review_command_context_history",
                "review_command_context_current",
                "review_command_receipts",
            )
        }
    finally:
        connection.close()


def test_trusted_create_persists_session_context_and_receipt_atomically(tmp_path) -> None:
    path = tmp_path / "create.db"
    seed_candidate(path)
    client = client_for(path)
    try:
        response = client.post("/api/v1/reviews", json=request_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "session_id": "review-1",
        "status": "open",
        "revision": 1,
        "candidate_count": 1,
        "pending_count": 1,
        "completed_count": 0,
        "created_at": NOW.isoformat(),
        "started_at": None,
        "completed_at": None,
        "schema_version": "review-session-v1",
    }
    assert counts(path) == {
        "review_session_history": 1,
        "review_session_current": 1,
        "review_command_context_history": 1,
        "review_command_context_current": 1,
        "review_command_receipts": 1,
    }

    repository = SQLiteReviewSessionRepository(path)
    try:
        context = repository.get_context("review-1", "candidate-1")
        receipt = repository.get_receipt("create-review-1")
        assert context is not None
        assert context.artifact_identity == "artifact-1"
        assert context.market_observation_identity.normalized_query == "mouse"
        assert receipt is not None
        assert receipt.transition_type == "create"
        assert receipt.resulting_revision == 1
    finally:
        repository.close()


def test_identical_create_replays_exact_response_after_restart(tmp_path) -> None:
    path = tmp_path / "replay.db"
    seed_candidate(path)
    first_client = client_for(path)
    try:
        first = first_client.post("/api/v1/reviews", json=request_body())
    finally:
        app.dependency_overrides.clear()
    second_client = client_for(path)
    try:
        replay = second_client.post("/api/v1/reviews", json=request_body())
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    assert counts(path) == {
        "review_session_history": 1,
        "review_session_current": 1,
        "review_command_context_history": 1,
        "review_command_context_current": 1,
        "review_command_receipts": 1,
    }


def test_changed_create_payload_and_incomplete_contexts_map_to_409(tmp_path) -> None:
    path = tmp_path / "conflicts.db"
    seed_candidate(path)
    client = client_for(path)
    try:
        first = client.post("/api/v1/reviews", json=request_body())
        changed = client.post(
            "/api/v1/reviews",
            json=request_body(operator_id="founder-2"),
        )
        incomplete = client.post(
            "/api/v1/reviews",
            json=request_body(
                session_id="review-2",
                command_id="create-review-2",
                contexts=[],
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 201
    assert changed.status_code == 409
    assert incomplete.status_code == 422


def test_context_failure_rolls_back_receipt_and_session(tmp_path) -> None:
    path = tmp_path / "rollback.db"
    seed_candidate(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """CREATE TRIGGER fail_trusted_context
            BEFORE INSERT ON review_command_context_history
            BEGIN SELECT RAISE(ABORT, 'context failure'); END"""
        )
        connection.commit()
    finally:
        connection.close()

    client = client_for(path)
    try:
        response = client.post("/api/v1/reviews", json=request_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert counts(path) == {
        "review_session_history": 0,
        "review_session_current": 0,
        "review_command_context_history": 0,
        "review_command_context_current": 0,
        "review_command_receipts": 0,
    }


def test_create_rejects_naive_times_and_unknown_candidate_without_partial_writes(tmp_path) -> None:
    path = tmp_path / "validation.db"
    seed_candidate(path)
    client = client_for(path)
    naive = request_body(created_at="2026-08-18T09:00:00")
    unknown = request_body(
        session_id="review-2",
        candidate_ids=["missing-candidate"],
        command_id="create-review-2",
    )
    unknown["contexts"][0]["candidate_id"] = "missing-candidate"
    try:
        naive_response = client.post("/api/v1/reviews", json=naive)
        unknown_response = client.post("/api/v1/reviews", json=unknown)
    finally:
        app.dependency_overrides.clear()

    assert naive_response.status_code == 422
    assert unknown_response.status_code == 409
    assert counts(path) == {
        "review_session_history": 0,
        "review_session_current": 0,
        "review_command_context_history": 0,
        "review_command_context_current": 0,
        "review_command_receipts": 0,
    }
