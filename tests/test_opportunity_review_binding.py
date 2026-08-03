from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.application.opportunity_review_binding import OpportunityReviewBindingConflictError
from app.application.opportunity_validation import AddToValidationQueueCommand, OpportunityValidationService
from app.application.review import ReviewWorkflowService
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.review import SQLiteVerifiedSignalPersistence
from app.web import app, get_review_workflow_service
from tests.test_founder_review_create_api import request_body
from tests.test_review_session_persistence import candidate

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)

def identity():
    return MarketObservationIdentity(MarketObservationScope.LISTING, "KR", "coupang", None, "item-1", None, "electronics", None, "new", NOW, NOW)

def seed_opportunity(path):
    repository = SQLiteValidationQueueRepository(path)
    OpportunityValidationService(queue_repository=repository, lifecycle_repository=repository).add(AddToValidationQueueCommand(
        opportunity_id="opp-1", discovery_reference="coupang:item-1", marketplace="coupang", title="Mouse",
        admission_recommendation="WATCH", admission_score=70, admission_roi=20, currency="KRW",
        admission_safety_status="READY", operator_id="founder-1", reason="selected", captured_at=NOW,
        market_observation_identity=identity()))
    repository.close()

def body(**changes):
    value = request_body(opportunity_id="opp-1", created_at=NOW.isoformat())
    context = value["contexts"][0]
    context["created_at"] = NOW.isoformat()
    context["market_observation_identity"] = {
        "scope":"listing", "market":"KR", "marketplace":"coupang", "canonical_product_id":None,
        "marketplace_item_id":"item-1", "normalized_query":None, "category":"electronics",
        "variant_identity":None, "condition":"new", "window_started_at":NOW.isoformat(), "window_ended_at":NOW.isoformat()}
    value.update(changes); return value

def client(path):
    def dependency():
        persistence = SQLiteVerifiedSignalPersistence(path)
        try: yield ReviewWorkflowService(persistence.ledger, persistence=persistence)
        finally: persistence.close()
    app.dependency_overrides[get_review_workflow_service] = dependency
    return TestClient(app)

def seed_candidate(path):
    persistence = SQLiteVerifiedSignalPersistence(path)
    try: persistence.ledger.save_candidate(candidate())
    finally: persistence.close()

def test_binding_is_atomic_append_only_and_restart_safe(tmp_path):
    path=tmp_path/"binding.db"; seed_opportunity(path); seed_candidate(path)
    browser=client(path)
    response=browser.post("/api/v1/reviews", json=body())
    assert response.status_code == 201
    assert browser.post("/api/v1/reviews/review-1/start", json={"expected_revision":1,"command_id":"start-1","operator_id":"founder-1","started_at":NOW.isoformat()}).status_code == 200
    assert browser.post("/api/v1/reviews/review-1/approve", json={"candidate_id":"candidate-1","expected_revision":2,"command_id":"approve-1","verification_id":"verification-1","operator_id":"founder-1","verified_at":NOW.isoformat(),"signal_id":"signal-1"}).status_code == 200
    app.dependency_overrides.clear()
    restarted=SQLiteVerifiedSignalPersistence(path)
    try:
        binding=restarted.sessions.get_opportunity_binding("review-1")
        assert binding.opportunity_id == "opp-1" and binding.discovery_reference == "coupang:item-1"
        assert binding.market_observation_identity == identity()
        with pytest.raises(FrozenInstanceError): binding.opportunity_id="changed"
        assert restarted._connection.execute("SELECT COUNT(*) FROM opportunity_review_binding_history").fetchone()[0] == 1
        assert restarted.opportunities.get_bound_review_external_signal_ids("opp-1") == ("signal-1",)
        with pytest.raises(sqlite3.IntegrityError):
            restarted._connection.execute("UPDATE opportunity_review_binding_history SET opportunity_id='x'")
    finally: restarted.close()

def test_identity_conflict_rolls_back_complete_review_admission(tmp_path):
    path=tmp_path/"rollback.db"; seed_opportunity(path); seed_candidate(path)
    payload=body(); payload["contexts"][0]["market_observation_identity"]["marketplace_item_id"]="other"
    response=client(path).post("/api/v1/reviews", json=payload); app.dependency_overrides.clear()
    assert response.status_code == 409
    connection=sqlite3.connect(path)
    try:
        for table in ("review_session_history","review_session_current","review_command_receipts","opportunity_review_binding_history","opportunity_review_binding_current"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally: connection.close()

def test_duplicate_concurrent_create_produces_one_binding(tmp_path):
    path=tmp_path/"concurrent.db"; seed_opportunity(path); seed_candidate(path)
    def create():
        c=client(path)
        try: return c.post("/api/v1/reviews", json=body()).status_code
        finally: app.dependency_overrides.clear()
    with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(lambda _:create(), range(2)))
    assert all(value == 201 for value in statuses)
    repository=SQLiteVerifiedSignalPersistence(path)
    try: assert len(repository.sessions.list_opportunity_bindings("opp-1")) == 1
    finally: repository.close()

def test_binding_projection_failure_rolls_back_entire_admission(tmp_path):
    path=tmp_path/"projection.db"; seed_opportunity(path); seed_candidate(path)
    connection=sqlite3.connect(path)
    connection.execute("CREATE TRIGGER fail_binding_projection BEFORE INSERT ON opportunity_review_binding_current BEGIN SELECT RAISE(ABORT, 'binding projection failure'); END")
    connection.commit(); connection.close()
    response=client(path).post("/api/v1/reviews", json=body()); app.dependency_overrides.clear()
    assert response.status_code == 503
    connection=sqlite3.connect(path)
    try:
        for table in ("review_session_history","review_session_current","review_command_context_history","review_command_receipts","opportunity_review_binding_history","opportunity_review_binding_current"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally: connection.close()
