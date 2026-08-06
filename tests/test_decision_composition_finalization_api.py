from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
import sqlite3

import app.web as web
from app.application.dashboard_api import ProductionOpportunityDecisionDashboardProvider
from app.application.decision_composition import FinalizeDecisionComposition
from app.application.decision_composition import (
    DecisionCompositionCommitError,
    DecisionCompositionIdentityConflictError,
    DecisionCompositionPersistenceError,
    DecisionCompositionProjectionError,
    DecisionCompositionVersionConflictError,
    MalformedDecisionCompositionError,
    MissingDecisionCompositionSourceError,
    UnsupportedDecisionCompositionVersionError,
)
from app.application.decision_composition_api import FinalizeOpportunityDecisionComposition
from app.application.decision_readiness import DecisionReadinessService
from app.domain.market_intelligence import MarketEvidenceStatus
from app.infrastructure.review import SQLiteReviewSessionRepository
from app.web import (
    app,
    get_decision_composition_finalizer,
    get_opportunity_decision_dashboard_provider,
)
from test_competition_intelligence import NOW
from test_decision_composition_finalization import (
    add_competition_snapshot,
    finalizer,
    listing_identity,
    persisted_state,
    repositories,
    seed_required_sources,
)
from test_opportunity_market_identity_binding import service
from test_production_safety_snapshot_binding import safety_command
from test_market_observation_repository import external


class ReviewBindings:
    def __init__(self, bindings):
        self._bindings = tuple(bindings)

    def list_opportunity_bindings(self, opportunity_id):
        return self._bindings


def valid_review_binding(validation, market_identity):
    item = validation.get_queue_item("opp-bound")
    return SimpleNamespace(
        opportunity_id=item.opportunity_id,
        discovery_reference=item.discovery_reference,
        market_observation_identity=market_identity,
        schema_version="opportunity-review-binding-v1",
    )


def use_case(validation, market, reviews=None):
    identity = validation.get_market_identity_binding("opp-bound")
    if reviews is None and identity is not None:
        reviews = ReviewBindings(
            (valid_review_binding(validation, identity.market_observation_identity),)
        )
    return FinalizeOpportunityDecisionComposition(
        FinalizeDecisionComposition(
            source_repository=validation,
            assessment_repository=market,
            composition_repository=validation,
            review_repository=reviews,
        ),
        clock=lambda: NOW,
    )


def post_client(validation, market):
    app.dependency_overrides[get_decision_composition_finalizer] = lambda: use_case(
        validation, market
    )
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_successful_finalization_returns_exact_201_dto_and_only_composition_writes() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    before = persisted_state(validation._connection)
    client = post_client(validation, market)
    try:
        response = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"generated_at": NOW.isoformat(), "requested_by": "operator-1"},
        )
    finally:
        clear_overrides()
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "composition_id", "opportunity_id", "composition_version", "generated_at",
        "schema_version", "policy_version", "composition_schema_version",
        "metadata_policy_version", "external_signal_ids", "status",
    }
    assert body["opportunity_id"] == "opp-bound"
    assert body["composition_version"] == 1
    assert body["generated_at"] == NOW.isoformat()
    assert body["external_signal_ids"] == []
    assert body["status"] == "finalized"
    after = persisted_state(validation._connection)
    changed = {table for table in before if before[table] != after[table]}
    assert changed == {"decision_composition_history", "decision_composition_current"}
    validation.close(); market.close()


def test_missing_review_binding_blocks_readiness_and_composition_without_writes() -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    reviews = ReviewBindings(())
    readiness = DecisionReadinessService(validation, market, reviews).execute("opp-bound")
    app.dependency_overrides[get_decision_composition_finalizer] = lambda: use_case(
        validation, market, reviews
    )
    try:
        response = TestClient(app).post(
            "/api/v1/opportunities/opp-bound/decision-compositions", json={}
        )
    finally:
        clear_overrides()

    assert readiness["sources"]["opportunity_review_binding"]["status"] == "missing"
    assert readiness["finalize_allowed"] is False
    assert response.status_code == 409
    assert response.json()["detail"] == "opportunity review binding not found"
    assert validation.get_decision_composition_history("opp-bound") == ()
    validation.close(); market.close()


@pytest.mark.parametrize(
    ("changes", "detail"),
    (
        ({"opportunity_id": "other"}, "review binding opportunity identity mismatch"),
        ({"discovery_reference": "other"}, "review binding discovery reference mismatch"),
        ({"market_observation_identity": replace(listing_identity(), marketplace_item_id="other")},
         "review binding market identity mismatch"),
    ),
)
def test_invalid_review_binding_lineage_blocks_composition(changes, detail) -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    binding = valid_review_binding(validation, identity)
    reviews = ReviewBindings((SimpleNamespace(**{**vars(binding), **changes}),))
    readiness = DecisionReadinessService(validation, market, reviews).execute("opp-bound")
    app.dependency_overrides[get_decision_composition_finalizer] = lambda: use_case(
        validation, market, reviews
    )
    try:
        response = TestClient(app).post(
            "/api/v1/opportunities/opp-bound/decision-compositions", json={}
        )
    finally:
        clear_overrides()

    assert readiness["sources"]["opportunity_review_binding"]["status"] == "error"
    assert readiness["finalize_allowed"] is False
    assert response.status_code == 409
    assert response.json()["detail"] == detail
    assert validation.get_decision_composition_history("opp-bound") == ()
    validation.close(); market.close()


def test_production_composition_injects_and_closes_review_repository(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", tmp_path / "production.db")
    dependency = web.get_decision_composition_finalizer()
    use_case_value = next(dependency)
    reviews = use_case_value._finalizer._reviews

    assert isinstance(reviews, SQLiteReviewSessionRepository)
    with pytest.raises(StopIteration):
        next(dependency)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        reviews._connection.execute("SELECT 1")


def test_post_then_production_dashboard_get_returns_200_and_get_is_read_only() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    client = post_client(validation, market)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = lambda: (
        ProductionOpportunityDecisionDashboardProvider(validation, assessment_repository=market)
    )
    try:
        created = client.post("/api/v1/opportunities/opp-bound/decision-compositions", json={})
        before_get = persisted_state(validation._connection)
        dashboard = client.get("/api/v1/opportunities/opp-bound/decision-dashboard")
        after_get = persisted_state(validation._connection)
    finally:
        clear_overrides()
    assert created.status_code == 201
    assert dashboard.status_code == 200
    assert before_get == after_get
    validation.close(); market.close()


def test_explicit_empty_selection_is_preserved_and_omitted_uses_default() -> None:
    for payload, expected in (({"external_signal_ids": []}, []), ({}, ["api-signal-1"])):
        validation, market = repositories(); seed_required_sources(validation, market)
        signal = replace(
            external(), identity=listing_identity(), signal_id="api-signal-1",
            candidate_id="api-candidate-1", verification_id="api-verification-1",
            operator_id="operator-1", verified_at=NOW,
            evidence=replace(external().evidence, status=MarketEvidenceStatus.HUMAN_VERIFIED),
        )
        market.save(signal)
        client = post_client(validation, market)
        try:
            response = client.post(
                "/api/v1/opportunities/opp-bound/decision-compositions", json=payload
            )
        finally:
            clear_overrides()
        assert response.status_code == 201
        assert response.json()["external_signal_ids"] == expected
        validation.close(); market.close()


def test_repeated_identical_post_is_409_without_advancing_current() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    client = post_client(validation, market)
    try:
        first = client.post("/api/v1/opportunities/opp-bound/decision-compositions", json={})
        second = client.post("/api/v1/opportunities/opp-bound/decision-compositions", json={})
    finally:
        clear_overrides()
    assert first.status_code == 201
    assert second.status_code == 409
    assert len(validation.get_decision_composition_history("opp-bound")) == 1
    assert validation.get_latest_decision_composition("opp-bound").composition_version == 1
    validation.close(); market.close()


def test_changed_authoritative_provenance_creates_next_version() -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    client = post_client(validation, market)
    try:
        first = client.post("/api/v1/opportunities/opp-bound/decision-compositions", json={})
        add_competition_snapshot(market, identity, "api-2", NOW.replace(hour=NOW.hour + 1))
        second = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"generated_at": NOW.replace(hour=NOW.hour + 1).isoformat()},
        )
    finally:
        clear_overrides()
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["composition_version"] == 2
    assert len(validation.get_decision_composition_history("opp-bound")) == 2
    validation.close(); market.close()


def test_opportunity_and_selected_signal_not_found_map_to_404() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    client = post_client(validation, market)
    try:
        opportunity = client.post("/api/v1/opportunities/missing/decision-compositions", json={})
        signal = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"external_signal_ids": ["missing-signal"]},
        )
    finally:
        clear_overrides()
    assert opportunity.status_code == 404
    assert signal.status_code == 404
    validation.close(); market.close()


def test_invalid_request_maps_to_422() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    client = post_client(validation, market)
    try:
        duplicate = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"external_signal_ids": ["same", "same"]},
        )
        naive = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"generated_at": "2026-08-03T00:00:00"},
        )
        fabricated = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions",
            json={"confidence": "1", "outcome": "invest"},
        )
    finally:
        clear_overrides()
    assert duplicate.status_code == 422
    assert naive.status_code == 422
    assert fabricated.status_code == 422
    validation.close(); market.close()


def test_missing_required_authoritative_source_maps_to_409() -> None:
    validation, market = repositories()
    service(validation).add(safety_command())
    client = post_client(validation, market)
    try:
        response = client.post(
            "/api/v1/opportunities/opp-bound/decision-compositions", json={}
        )
    finally:
        clear_overrides()
    assert response.status_code == 409
    assert validation.get_decision_composition_history("opp-bound") == ()
    validation.close(); market.close()


class FailingUseCase:
    def __init__(self, error):
        self.error = error

    def execute(self, command):
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected_status"),
    (
        (DecisionCompositionIdentityConflictError("identity conflict"), 409),
        (DecisionCompositionVersionConflictError("version conflict"), 409),
        (UnsupportedDecisionCompositionVersionError("unsupported version"), 409),
        (MissingDecisionCompositionSourceError("source missing"), 409),
        (MalformedDecisionCompositionError("source malformed"), 409),
        (DecisionCompositionPersistenceError("history failed"), 503),
        (DecisionCompositionProjectionError("projection failed"), 503),
        (DecisionCompositionCommitError("commit failed"), 503),
    ),
)
def test_application_error_taxonomy_maps_deterministically(error, expected_status) -> None:
    app.dependency_overrides[get_decision_composition_finalizer] = lambda: FailingUseCase(error)
    try:
        response = TestClient(app).post(
            "/api/v1/opportunities/opp-bound/decision-compositions", json={}
        )
    finally:
        clear_overrides()
    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)
