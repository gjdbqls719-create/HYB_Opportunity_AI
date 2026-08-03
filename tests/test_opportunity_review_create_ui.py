from fastapi.testclient import TestClient

from app.application.opportunity_review_ui import OpportunityReviewUIQueryService
from app.application.review import ReviewWorkflowService
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from app.web import app, get_opportunity_review_ui_query_service, get_review_workflow_service
from tests.test_opportunity_review_binding import body, seed_candidate, seed_opportunity


def configured_client(path):
    def query_dependency():
        persistence=SQLiteVerifiedSignalPersistence(path)
        try: yield OpportunityReviewUIQueryService(persistence.opportunities,persistence.sessions,persistence.ledger)
        finally: persistence.close()
    def workflow_dependency():
        persistence=SQLiteVerifiedSignalPersistence(path)
        try: yield ReviewWorkflowService(persistence.ledger,persistence=persistence)
        finally: persistence.close()
    app.dependency_overrides[get_opportunity_review_ui_query_service]=query_dependency
    app.dependency_overrides[get_review_workflow_service]=workflow_dependency
    return TestClient(app)


def test_opportunity_browser_routes_and_safe_templates():
    client=TestClient(app)
    assert client.get("/opportunities").status_code == 200
    assert client.get("/opportunities/opp-1").status_code == 200
    source=(client.get("/opportunities/opp-1").text + client.get("/opportunities").text)
    assert "innerHTML" not in source
    assert "textContent" in source
    assert 'role="status"' in source
    assert "@media" in source


def test_opportunity_list_and_detail_expose_authoritative_sources(tmp_path):
    path=tmp_path/"ui.db";seed_opportunity(path);seed_candidate(path);client=configured_client(path)
    try:
        listed=client.get("/api/v1/opportunities")
        detail=client.get("/api/v1/opportunities/opp-1/review-detail")
    finally: app.dependency_overrides.clear()
    assert listed.status_code == detail.status_code == 200
    assert listed.json()["items"][0]["review_bound"] is False
    payload=detail.json()
    assert payload["market_identity"]["marketplace_item_id"] == "item-1"
    assert payload["candidates"][0]["candidate_id"] == "candidate-1"
    assert payload["review"] is None


def test_create_bound_review_then_detail_prevents_second_create(tmp_path):
    path=tmp_path/"create.db";seed_opportunity(path);seed_candidate(path);client=configured_client(path)
    try:
        created=client.post("/api/v1/reviews",json=body())
        detail=client.get("/api/v1/opportunities/opp-1/review-detail")
        duplicate=client.post("/api/v1/reviews",json=body(session_id="review-2",command_id="create-2"))
    finally: app.dependency_overrides.clear()
    assert created.status_code == 201
    assert detail.json()["review"] == {**created.json()}
    assert duplicate.status_code == 409


def test_detail_404_and_create_flow_contract():
    client=TestClient(app)
    source=client.get("/opportunities/opp-1").text
    assert 'fetch("/api/v1/reviews"' in source
    assert 'location.assign("/reviews")' in source
    assert "opportunity_id:opportunityId" in source
    assert "crypto.randomUUID()" in source
    assert "let detail=null,retry=null" in source
