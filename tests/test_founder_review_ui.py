from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient

from app.application.review import (
    CreateReviewSession,
    ReviewCommandContext,
    ReviewSessionQueryService,
    ReviewWorkflowService,
)
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from app.web import app, get_review_session_query_service, get_review_workflow_service
from tests.test_review_session_persistence import NOW, candidate, identity


def seed(path, *, raw_text="100"):
    persistence = SQLiteVerifiedSignalPersistence(path)
    item = replace(candidate(), raw_text=raw_text)
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    service.create_session(CreateReviewSession(
        session_id="review-1",
        artifact_id="artifact-1",
        candidate_ids=("candidate-1",),
        operator_id="founder-1",
        created_at=NOW,
        command_id="create-1",
        contexts=(ReviewCommandContext(
            session_id="review-1",
            candidate_id="candidate-1",
            market_observation_identity=identity(),
            signal_name="search volume",
            signal_direction="positive",
            artifact_identity="artifact-1",
            created_at=NOW,
        ),),
    ))
    persistence.close()


def client_for(path):
    def query_dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try:
            yield ReviewSessionQueryService(persistence.sessions, persistence.ledger)
        finally:
            persistence.close()

    def workflow_dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try:
            yield ReviewWorkflowService(persistence.ledger, persistence=persistence)
        finally:
            persistence.close()

    app.dependency_overrides[get_review_session_query_service] = query_dependency
    app.dependency_overrides[get_review_workflow_service] = workflow_dependency
    return TestClient(app)


def test_queue_and_detail_browser_routes_render_without_mutation() -> None:
    client = TestClient(app)
    queue = client.get("/reviews")
    detail = client.get("/reviews/review-1")

    assert queue.status_code == detail.status_code == 200
    assert "text/html" in queue.headers["content-type"]
    assert "Founder Review Queue" in queue.text
    assert "Founder Review Detail" in detail.text
    assert 'data-session-id="review-1"' in detail.text
    assert "loadQueue();" in queue.text
    assert "loadDetail();" in detail.text
    assert "method:\"POST\"" in detail.text
    assert "method:\"POST\"" not in queue.text


def test_queue_ui_uses_read_api_and_preserves_required_columns() -> None:
    html = TestClient(app).get("/reviews").text
    assert 'fetch("/api/v1/reviews")' in html
    for label in (
        "Session ID", "Status", "Revision", "Candidates", "Pending",
        "Completed", "Created", "Started", "Completed at", "Action",
    ):
        assert label in html
    assert "data.items" in html
    assert "items.forEach" in html
    assert "Open details" in html


def test_detail_ui_exposes_all_explicit_command_forms_and_paths() -> None:
    html = TestClient(app).get("/reviews/review-1").text
    for action in ("start", "approve", "correct", "skip", "complete", "cancel"):
        assert f'data-action="{action}"' in html or f'["approve","correct","skip"]' in html
    assert "/api/v1/reviews/${encodeURIComponent(sessionId)}/${action}" in html
    assert "/api/v1/reviews/${encodeURIComponent(sessionId)}/detail" in html
    assert "expected_revision:authoritative.revision" in html
    assert "await loadDetail" in html


def test_detail_read_dto_contains_authoritative_candidate_artifact_and_context(tmp_path) -> None:
    path = tmp_path / "detail.db"
    seed(path, raw_text='<img src=x onerror="alert(1)">')
    client = client_for(path)
    try:
        response = client.get("/api/v1/reviews/review-1/detail")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "review-1"
    assert [item["candidate_id"] for item in data["candidates"]] == ["candidate-1"]
    item = data["candidates"][0]
    assert item["raw_text"] == '<img src=x onerror="alert(1)">'
    assert item["normalized_value"] == 100
    assert item["confidence"] == "0.9"
    assert item["artifact"] == {
        "artifact_id": "artifact-1",
        "artifact_type": "screenshot",
        "origin": "itemscout",
        "source_type": "itemscout_screenshot",
        "mime_type": "image/png",
        "width": 100,
        "height": 100,
        "file_size": 10,
        "captured_at": NOW.isoformat(),
        "schema_version": "artifact-v1",
        "preview_available": False,
    }
    assert item["context"]["signal_name"] == "search volume"
    assert item["context"]["signal_direction"] == "positive"
    assert item["context"]["market_observation_identity"]["normalized_query"] == "mouse"


def test_detail_ui_uses_safe_rendering_and_has_no_artifact_url() -> None:
    html = TestClient(app).get("/reviews/review-1").text
    assert "innerHTML" not in html
    assert ".textContent" in html
    assert "replaceChildren" in html
    assert "Artifact preview unavailable" in html
    assert "preview_available" not in html
    assert "<img" not in html
    assert "market_observation_identity" in html


def test_retry_metadata_and_error_status_ux_contract() -> None:
    html = TestClient(app).get("/reviews/review-1").text
    assert "const retryState=new Map()" in html
    assert "retryState.get(key) || buildCommand(form)" in html
    assert "verification_id=uuid()" in html
    assert "signal_id=uuid()" in html
    assert "const timestamp=new Date().toISOString()" in html
    assert "retryState.delete(key)" in html
    assert "Reset retry" in html
    for code in ("404", "409", "422", "503"):
        assert f"status === {code}" in html
    assert "Authoritative Session reloaded" in html
    assert "SQLite" not in html
    assert "stack" not in html.lower()


def test_accessibility_and_responsive_baseline() -> None:
    queue = TestClient(app).get("/reviews").text
    detail = TestClient(app).get("/reviews/review-1").text
    for html in (queue, detail):
        assert 'role="status"' in html
        assert 'aria-live="polite"' in html
        assert ":focus-visible" in html
        assert "@media" in html
        assert "<main>" in html
        assert "<h1>" in html
    assert "<label" in detail
    assert 'type="submit"' in detail
    assert "status-label" in detail


def test_browser_api_flow_create_start_approve_complete_and_authoritative_refetch(tmp_path) -> None:
    path = tmp_path / "browser-flow.db"
    seed(path)
    client = client_for(path)
    try:
        page = client.get("/reviews/review-1")
        first = client.get("/api/v1/reviews/review-1/detail")
        started = client.post("/api/v1/reviews/review-1/start", json={
            "expected_revision": 1,
            "command_id": "ui-start-1",
            "operator_id": "founder-1",
            "started_at": (NOW + timedelta(minutes=1)).isoformat(),
        })
        approved = client.post("/api/v1/reviews/review-1/approve", json={
            "candidate_id": "candidate-1",
            "expected_revision": 2,
            "command_id": "ui-approve-1",
            "verification_id": "ui-verification-1",
            "operator_id": "founder-1",
            "verified_at": (NOW + timedelta(minutes=2)).isoformat(),
            "signal_id": "ui-signal-1",
        })
        completed = client.post("/api/v1/reviews/review-1/complete", json={
            "expected_revision": 3,
            "command_id": "ui-complete-1",
            "operator_id": "founder-1",
            "completed_at": (NOW + timedelta(minutes=3)).isoformat(),
        })
        final = client.get("/api/v1/reviews/review-1/detail")
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == first.status_code == 200
    assert started.status_code == approved.status_code == completed.status_code == 200
    assert final.status_code == 200
    assert first.json()["revision"] == 1
    assert final.json()["revision"] == 4
    assert final.json()["status"] == "completed"
    assert final.json()["candidates"][0]["status"] == "approved"
