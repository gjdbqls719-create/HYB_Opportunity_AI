from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.application.review import (
    CreateReviewSession,
    ReviewCommandContext,
    ReviewSessionQueryService,
    ReviewWorkflowService,
    StartReviewCommand,
)
from app.infrastructure.review import SQLiteReviewSessionRepository, SQLiteVerifiedSignalPersistence
from app.web import app, get_review_session_query_service, get_review_workflow_service
from tests.test_review_session_persistence import NOW, candidate, identity


STARTED_AT = NOW + timedelta(minutes=1)
WRITTEN_AT = NOW + timedelta(minutes=2)
COMPLETED_AT = NOW + timedelta(minutes=3)


def context(session_id="review-1", candidate_id="candidate-1"):
    return ReviewCommandContext(
        session_id=session_id,
        candidate_id=candidate_id,
        market_observation_identity=identity(),
        signal_name="search volume",
        signal_direction="positive",
        artifact_identity="artifact-1",
        created_at=NOW,
    )


def setup_review(path, *, session_id="review-1"):
    persistence = SQLiteVerifiedSignalPersistence(path)
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        session_id=session_id,
        artifact_id="artifact-1",
        candidate_ids=(item.candidate_id,),
        operator_id="founder-1",
        created_at=NOW,
        command_id=f"create-{session_id}",
        contexts=(context(session_id),),
    ))
    started = service.start_review(StartReviewCommand(
        session_id, opened.revision, f"start-{session_id}", "founder-1", STARTED_AT
    ))
    persistence.close()
    return started


def client_for(path):
    def workflow_dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try:
            yield ReviewWorkflowService(persistence.ledger, persistence=persistence)
            assert not persistence._connection.in_transaction
        finally:
            persistence.close()

    def query_dependency():
        repository = SQLiteReviewSessionRepository(path)
        try:
            yield ReviewSessionQueryService(repository)
        finally:
            repository.close()

    app.dependency_overrides[get_review_workflow_service] = workflow_dependency
    app.dependency_overrides[get_review_session_query_service] = query_dependency
    return TestClient(app)


def approve_body(**changes):
    body = {
        "candidate_id": "candidate-1",
        "expected_revision": 2,
        "command_id": "approve-1",
        "verification_id": "verification-1",
        "operator_id": "founder-1",
        "verified_at": WRITTEN_AT.isoformat(),
        "signal_id": "signal-1",
        "comment": "trusted review",
        "confidence": "0.8",
    }
    body.update(changes)
    return body


def correct_body(**changes):
    body = approve_body(
        command_id="correct-1",
        verification_id="verification-correct-1",
        signal_id="signal-correct-1",
    )
    body["corrected_value"] = 1200
    body.update(changes)
    return body


def skip_body(**changes):
    body = {
        "candidate_id": "candidate-1",
        "expected_revision": 2,
        "command_id": "skip-1",
        "operator_id": "founder-1",
        "reason": "not decision-grade",
        "skipped_at": WRITTEN_AT.isoformat(),
    }
    body.update(changes)
    return body


def complete_body(**changes):
    body = {
        "expected_revision": 3,
        "command_id": "complete-1",
        "operator_id": "founder-1",
        "completed_at": COMPLETED_AT.isoformat(),
    }
    body.update(changes)
    return body


def write_state(path):
    connection = sqlite3.connect(path)
    try:
        tables = (
            "human_verification_history",
            "human_verification_current",
            "market_observation_history",
            "market_observation_current",
            "review_session_history",
            "review_session_current",
            "review_command_context_history",
            "review_command_context_current",
            "review_command_receipts",
        )
        return {
            table: tuple(connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
            for table in tables
        }
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("route", "body", "expected_status", "expected_value"),
    (
        ("approve", approve_body(), "approved", 100),
        ("correct", correct_body(), "corrected", 1200),
    ),
)
def test_approve_and_correct_use_context_and_create_verification_signal_receipt(
    tmp_path, route, body, expected_status, expected_value
) -> None:
    path = tmp_path / f"{route}.db"
    setup_review(path)
    client = client_for(path)
    try:
        response = client.post(f"/api/v1/reviews/review-1/{route}", json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["revision"] == 3
    assert response.json()["completed_count"] == 1

    persistence = SQLiteVerifiedSignalPersistence(path)
    try:
        verification = persistence.ledger.get_latest_verification("candidate-1")
        receipt = persistence.sessions.get_receipt(body["command_id"])
        signals = persistence.observations.get_human_verified_external_signals_by_ids(
            identity(), (body["signal_id"],)
        )
        session = persistence.sessions.get("review-1")
        assert verification is not None
        assert verification.verified_value == expected_value
        assert len(signals) == 1
        assert signals[0].signal_name == "search volume"
        assert signals[0].signal_direction.value == "positive"
        assert receipt is not None
        assert receipt.transition_type == expected_status
        assert receipt.verification_id == body["verification_id"]
        assert receipt.external_signal_id == body["signal_id"]
        assert session.candidate_statuses[0][1].value == expected_status
    finally:
        persistence.close()


def test_skip_creates_only_session_and_receipt_then_complete_advances_revision(tmp_path) -> None:
    path = tmp_path / "skip-complete.db"
    setup_review(path)
    client = client_for(path)
    try:
        skipped = client.post("/api/v1/reviews/review-1/skip", json=skip_body())
        completed = client.post(
            "/api/v1/reviews/review-1/complete", json=complete_body()
        )
    finally:
        app.dependency_overrides.clear()

    assert skipped.status_code == completed.status_code == 200
    assert skipped.json()["revision"] == 3
    assert completed.json()["status"] == "completed"
    assert completed.json()["revision"] == 4
    assert completed.json()["completed_at"] == COMPLETED_AT.isoformat()

    persistence = SQLiteVerifiedSignalPersistence(path)
    try:
        assert persistence.ledger.get_latest_verification("candidate-1") is None
        assert persistence.observations.get_latest_human_verified_external_signals(
            identity()
        ) == ()
        skip_receipt = persistence.sessions.get_receipt("skip-1")
        complete_receipt = persistence.sessions.get_receipt("complete-1")
        assert skip_receipt.transition_type == "skip"
        assert complete_receipt.transition_type == "complete"
        assert persistence.sessions.get("review-1").revision == 4
    finally:
        persistence.close()


@pytest.mark.parametrize(
    "route,body",
    (
        ("approve", approve_body()),
        ("correct", correct_body()),
        ("skip", skip_body()),
    ),
)
def test_write_replay_is_exact_and_restart_safe(tmp_path, route, body) -> None:
    path = tmp_path / f"replay-{route}.db"
    setup_review(path)
    first_client = client_for(path)
    try:
        first = first_client.post(f"/api/v1/reviews/review-1/{route}", json=body)
    finally:
        app.dependency_overrides.clear()
    before = write_state(path)
    restarted_client = client_for(path)
    try:
        replay = restarted_client.post(f"/api/v1/reviews/review-1/{route}", json=body)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert write_state(path) == before


def test_complete_receipt_replays_after_restart_without_writes(tmp_path) -> None:
    path = tmp_path / "replay-complete.db"
    setup_review(path)
    client = client_for(path)
    try:
        skipped = client.post("/api/v1/reviews/review-1/skip", json=skip_body())
        first = client.post(
            "/api/v1/reviews/review-1/complete", json=complete_body()
        )
    finally:
        app.dependency_overrides.clear()
    before = write_state(path)
    restarted_client = client_for(path)
    try:
        replay = restarted_client.post(
            "/api/v1/reviews/review-1/complete", json=complete_body()
        )
    finally:
        app.dependency_overrides.clear()

    assert skipped.status_code == first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.json()["revision"] == 4
    assert write_state(path) == before


def test_write_conflict_stale_operator_transition_and_naive_time_mapping(tmp_path) -> None:
    path = tmp_path / "errors.db"
    setup_review(path)
    client = client_for(path)
    try:
        stale = client.post(
            "/api/v1/reviews/review-1/approve",
            json=approve_body(expected_revision=99, command_id="stale-1"),
        )
        operator = client.post(
            "/api/v1/reviews/review-1/skip",
            json=skip_body(operator_id="other-founder", command_id="operator-1"),
        )
        pending = client.post(
            "/api/v1/reviews/review-1/complete",
            json=complete_body(expected_revision=2, command_id="pending-1"),
        )
        naive = client.post(
            "/api/v1/reviews/review-1/approve",
            json=approve_body(verified_at="2026-08-15T09:02:00", command_id="naive-1"),
        )
        missing = client.post(
            "/api/v1/reviews/missing/approve",
            json=approve_body(command_id="missing-1"),
        )
        first = client.post("/api/v1/reviews/review-1/approve", json=approve_body())
        changed = client.post(
            "/api/v1/reviews/review-1/approve",
            json=approve_body(comment="changed"),
        )
    finally:
        app.dependency_overrides.clear()

    assert stale.status_code == 409
    assert operator.status_code == 409
    assert pending.status_code == 409
    assert naive.status_code == 422
    assert missing.status_code == 404
    assert first.status_code == 200
    assert changed.status_code == 409


@pytest.mark.parametrize(
    ("table", "operation"),
    (
        ("human_verification_history", "INSERT"),
        ("human_verification_current", "INSERT"),
        ("market_observation_history", "INSERT"),
        ("market_observation_current", "INSERT"),
        ("review_command_receipts", "INSERT"),
        ("review_session_history", "INSERT"),
        ("review_session_current", "UPDATE"),
    ),
)
def test_approve_rollback_matrix(tmp_path, table, operation) -> None:
    path = tmp_path / f"rollback-{table}.db"
    setup_review(path)
    before = write_state(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            f"""CREATE TRIGGER fail_write BEFORE {operation} ON {table}
            BEGIN SELECT RAISE(ABORT, 'forced write failure'); END"""
        )
        connection.commit()
    finally:
        connection.close()
    client = client_for(path)
    try:
        response = client.post(
            "/api/v1/reviews/review-1/approve", json=approve_body()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "forced write failure" not in response.json()["detail"]
    assert write_state(path) == before


def test_read_api_after_write_is_read_only_and_restart_round_trips(tmp_path) -> None:
    path = tmp_path / "read-only.db"
    setup_review(path)
    client = client_for(path)
    try:
        approved = client.post(
            "/api/v1/reviews/review-1/approve", json=approve_body()
        )
        before = write_state(path)
        first = client.get("/api/v1/reviews/review-1")
        second = client.get("/api/v1/reviews/review-1")
    finally:
        app.dependency_overrides.clear()

    assert approved.status_code == first.status_code == second.status_code == 200
    assert first.json() == second.json() == approved.json()
    assert write_state(path) == before

    restarted = SQLiteReviewSessionRepository(path)
    try:
        restored = restarted.get("review-1")
        assert restored.revision == 3
        assert restored.candidate_statuses[0][1].value == "approved"
    finally:
        restarted.close()
