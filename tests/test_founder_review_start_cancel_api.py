from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from app.application.review import (
    ReviewHistoryError,
    ReviewTransitionMetadata,
    ReviewWorkflowService,
)
from app.domain.market_intelligence import ReviewSession, ReviewSessionStatus
from app.infrastructure.review import (
    SQLiteReviewSessionRepository,
    SQLiteVerifiedSignalPersistence,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_review_workflow_service


NOW = datetime(2026, 8, 17, 9, tzinfo=timezone.utc)
LATER = datetime(2026, 8, 17, 10, tzinfo=timezone.utc)


def session(session_id: str = "review-1") -> ReviewSession:
    return ReviewSession(
        session_id=session_id,
        artifact_id=f"artifact-{session_id}",
        candidate_ids=(f"{session_id}-candidate-1",),
        status=ReviewSessionStatus.OPEN,
        created_at=NOW,
        completed_at=None,
        operator_id="founder-1",
        schema_version="review-session-v1",
    )


def metadata(session_id: str = "review-1") -> ReviewTransitionMetadata:
    return ReviewTransitionMetadata(
        event_id=f"event-{session_id}",
        command_id=f"create-{session_id}",
        transition_type="create",
        occurred_at=NOW,
        command_fingerprint=f"fingerprint-{session_id}",
    )


def seed(path, *sessions: ReviewSession) -> None:
    repository = SQLiteReviewSessionRepository(path)
    try:
        for value in sessions:
            repository.create(value, metadata(value.session_id))
    finally:
        repository.close()


def client_for(path) -> TestClient:
    def dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try:
            yield ReviewWorkflowService(
                persistence.ledger,
                persistence=persistence,
            )
            assert not persistence._connection.in_transaction
        finally:
            persistence.close()

    app.dependency_overrides[get_review_workflow_service] = dependency
    return TestClient(app)


def database_state(path) -> dict[str, tuple[tuple[object, ...], ...]]:
    connection = sqlite3.connect(path)
    try:
        names = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        state: dict[str, tuple[tuple[object, ...], ...]] = {}
        for name in names:
            columns = tuple(
                row[1]
                for row in connection.execute(f'PRAGMA table_info("{name}")')
            )
            order = ", ".join(f'"{column}"' for column in columns)
            rows = connection.execute(
                f'SELECT * FROM "{name}" ORDER BY {order}'
            ).fetchall()
            state[name] = tuple(tuple(row) for row in rows)
        assert not connection.in_transaction
        return state
    finally:
        connection.close()


def test_start_and_cancel_return_session_dto_and_replay_exact_result(tmp_path) -> None:
    path = tmp_path / "review-write.db"
    seed(path, session("start-session"), session("cancel-session"))
    client = client_for(path)
    try:
        start_body = {
            "expected_revision": 1,
            "command_id": "start-command-1",
            "operator_id": "founder-1",
            "started_at": LATER.isoformat(),
        }
        started = client.post(
            "/api/v1/reviews/start-session/start",
            json=start_body,
        )
        replayed_start = client.post(
            "/api/v1/reviews/start-session/start",
            json=start_body,
        )

        cancel_body = {
            "expected_revision": 1,
            "command_id": "cancel-command-1",
            "operator_id": "founder-1",
            "reason": "Source evidence is no longer relevant",
            "cancelled_at": LATER.isoformat(),
        }
        cancelled = client.post(
            "/api/v1/reviews/cancel-session/cancel",
            json=cancel_body,
        )
        replayed_cancel = client.post(
            "/api/v1/reviews/cancel-session/cancel",
            json=cancel_body,
        )
    finally:
        app.dependency_overrides.clear()

    assert started.status_code == replayed_start.status_code == 200
    assert started.json() == replayed_start.json()
    assert started.json()["status"] == "in_progress"
    assert started.json()["revision"] == 2
    assert started.json()["started_at"] == LATER.isoformat()

    assert cancelled.status_code == replayed_cancel.status_code == 200
    assert cancelled.json() == replayed_cancel.json()
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["revision"] == 2
    assert cancelled.json()["completed_at"] == LATER.isoformat()

    repository = SQLiteReviewSessionRepository(path)
    try:
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM review_command_receipts"
        ).fetchone()[0] == 2
        cancel_metadata = repository.get_cancel_metadata("cancel-session")
        assert cancel_metadata is not None
        assert cancel_metadata.reason == "Source evidence is no longer relevant"
        assert cancel_metadata.operator_id == "founder-1"
        assert cancel_metadata.cancelled_at == LATER
        assert cancel_metadata.revision == 2
        assert cancel_metadata.schema_version == "review-cancel-metadata-v1"
    finally:
        repository.close()


def test_start_and_cancel_write_only_review_transition_areas(tmp_path) -> None:
    path = tmp_path / "write-scope.db"
    seed(path, session("start-session"), session("cancel-session"))
    SQLiteVerifiedSignalPersistence(path).close()
    SQLiteValidationQueueRepository(path).close()
    before = database_state(path)
    client = client_for(path)
    try:
        assert client.post(
            "/api/v1/reviews/start-session/start",
            json={
                "expected_revision": 1,
                "command_id": "start-command-2",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        ).status_code == 200
        assert client.post(
            "/api/v1/reviews/cancel-session/cancel",
            json={
                "expected_revision": 1,
                "command_id": "cancel-command-2",
                "operator_id": "founder-1",
                "reason": "Cancelled during MVP validation",
                "cancelled_at": LATER.isoformat(),
            },
        ).status_code == 200
    finally:
        app.dependency_overrides.clear()
    after = database_state(path)

    allowed = {
        "review_session_history",
        "review_session_current",
        "review_command_receipts",
        "review_cancel_metadata",
    }
    for table_name, rows in before.items():
        if table_name not in allowed:
            assert after[table_name] == rows

    unchanged_review_areas = {
        "review_command_context_history",
        "review_command_context_current",
        "human_verification_history",
        "human_verification_current",
        "market_observation_history",
        "market_observation_current",
        "opportunity_lifecycles",
        "opportunity_lifecycle_transitions",
        "decision_composition_history",
        "decision_composition_current",
    }
    assert unchanged_review_areas <= before.keys()
    for table_name in unchanged_review_areas:
        assert after[table_name] == before[table_name]


def test_review_transition_http_error_mapping(tmp_path) -> None:
    path = tmp_path / "errors.db"
    seed(path, session())
    client = client_for(path)
    try:
        missing = client.post(
            "/api/v1/reviews/missing/start",
            json={
                "expected_revision": 1,
                "command_id": "missing-start",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        )
        stale = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 99,
                "command_id": "stale-start",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        )
        wrong_operator = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "wrong-operator-start",
                "operator_id": "other-founder",
                "started_at": LATER.isoformat(),
            },
        )
        naive_time = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "naive-start",
                "operator_id": "founder-1",
                "started_at": "2026-08-17T10:00:00",
            },
        )
        malformed = client.post(
            "/api/v1/reviews/review-1/cancel",
            json={
                "expected_revision": 1,
                "command_id": "",
                "operator_id": "founder-1",
                "reason": "",
                "cancelled_at": LATER.isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert missing.status_code == 404
    assert stale.status_code == 409
    assert wrong_operator.status_code == 409
    assert naive_time.status_code == 422
    assert malformed.status_code == 422


def test_same_command_with_changed_payload_maps_to_409(tmp_path) -> None:
    path = tmp_path / "command-conflict.db"
    seed(path, session())
    client = client_for(path)
    try:
        first = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "reused-command",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        )
        conflict = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "reused-command",
                "operator_id": "founder-1",
                "started_at": datetime(2026, 8, 17, 11, tzinfo=timezone.utc).isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert conflict.status_code == 409


class FailingWorkflowService:
    def start_review(self, command):
        raise ReviewHistoryError("review history unavailable")

    def cancel_review(self, command):
        raise ReviewHistoryError("review history unavailable")


class SQLiteFailingWorkflowService:
    def start_review(self, command):
        raise sqlite3.OperationalError("sensitive sqlite detail")


def test_persistence_failure_maps_to_503() -> None:
    app.dependency_overrides[get_review_workflow_service] = lambda: FailingWorkflowService()
    try:
        client = TestClient(app)
        started = client.post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "start-failure",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        )
        cancelled = client.post(
            "/api/v1/reviews/review-1/cancel",
            json={
                "expected_revision": 1,
                "command_id": "cancel-failure",
                "operator_id": "founder-1",
                "reason": "Persistence unavailable",
                "cancelled_at": LATER.isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert started.status_code == cancelled.status_code == 503
    assert started.json()["detail"] == "review history unavailable"


def test_raw_sqlite_failure_maps_to_503_without_exposing_database_detail() -> None:
    app.dependency_overrides[get_review_workflow_service] = (
        lambda: SQLiteFailingWorkflowService()
    )
    try:
        response = TestClient(app).post(
            "/api/v1/reviews/review-1/start",
            json={
                "expected_revision": 1,
                "command_id": "sqlite-failure",
                "operator_id": "founder-1",
                "started_at": LATER.isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "review persistence unavailable"
