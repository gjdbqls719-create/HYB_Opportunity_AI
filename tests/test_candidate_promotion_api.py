from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.candidate_promotion import (
    CandidateAlreadyPromotedError,
    CandidateForPromotionNotFoundError,
    CandidatePromotionCommandConflictError,
    CandidatePromotionContextNotFoundError,
    CandidatePromotionIdentityConflictError,
    CandidatePromotionPersistenceError,
    CandidatePromotionProductionEntry,
)
from app.domain.opportunity import OpportunityLifecycleStatus
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.opportunity_validation import (
    ProductionCandidateOpportunityBindingIdentityGenerator,
    ProductionOpportunityIdentityGenerator,
    SQLiteCandidatePromotionRepository,
)
from app.web import app, get_candidate_promotion_entry
import app.web as web
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_promotion_production_entry import promotion_counts
from test_product_snapshot_capture_production_entry import close_all, prepare


def payload(**changes):
    value = {
        "promotion_command_id": "promotion-1",
        "candidate_id": "candidate-1",
        "title": "Camera",
        "admission_recommendation": "WATCH",
        "admission_score": 70,
        "admission_roi": 25,
        "currency": "USD",
        "admission_safety_status": "READY",
        "operator_id": "founder",
        "reason": "admitted",
        "requested_at": ISSUED_AT.isoformat(),
        "opportunity_id": None,
        "note": "promotion note",
    }
    value.update(changes)
    return value


def use(entry):
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def entry(candidates, promotions, opportunity=None, binding=None, clock=None):
    return CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        promotion_repository=promotions,
        opportunity_id_generator=(
            opportunity or Counter("generated-opportunity")
        ),
        binding_id_generator=binding or Counter("generated-binding"),
        clock=clock or Counter(ISSUED_AT + timedelta(minutes=1)),
    )


class Fail:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError("dependency must not run")


def test_candidate_promotion_composition_uses_production_dependencies_and_closes(
    tmp_path, monkeypatch
):
    path = tmp_path / "promotion-composition.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_candidate_promotion_entry()
    value = next(dependency)
    owner = value._promote
    candidates = owner._candidates
    promotions = owner._promotions

    assert isinstance(value, CandidatePromotionProductionEntry)
    assert isinstance(candidates, SQLiteCandidateIssuanceRepository)
    assert isinstance(promotions, SQLiteCandidatePromotionRepository)
    assert isinstance(
        owner._opportunity_id_generator,
        ProductionOpportunityIdentityGenerator,
    )
    assert isinstance(
        owner._binding_id_generator,
        ProductionCandidateOpportunityBindingIdentityGenerator,
    )
    assert owner._clock().tzinfo is not None
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in (candidates, promotions)
    } == {str(path)}

    dependency.close()
    for repository in (candidates, promotions):
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_candidate_promotion_partial_composition_failure_closes_candidate(
    monkeypatch,
):
    closed = []

    class CandidateRepository:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(web, "SQLiteCandidateIssuanceRepository", CandidateRepository)
    monkeypatch.setattr(
        web,
        "SQLiteCandidatePromotionRepository",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )

    with pytest.raises(HTTPException) as caught:
        next(get_candidate_promotion_entry())

    assert caught.value.status_code == 503
    assert closed == [True]


@pytest.mark.parametrize(
    "error",
    (
        CandidatePromotionIdentityConflictError("application failure"),
        CandidatePromotionPersistenceError("repository failure"),
    ),
)
def test_candidate_promotion_dependency_closes_on_execution_failure(
    tmp_path, monkeypatch, error
):
    path = tmp_path / "promotion-dependency-failure.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_candidate_promotion_entry()
    value = next(dependency)
    repositories = (value._promote._candidates, value._promote._promotions)

    with pytest.raises(type(error), match=str(error)):
        dependency.throw(error)

    for repository in repositories:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_candidate_promotion_api_fresh_generated_identity_persists_complete_admission(
    tmp_path,
):
    path = tmp_path / "promotion-api.db"
    sources, candidates, issuance, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    opportunity = Counter("generated-opportunity")
    binding = Counter("generated-binding")
    clock = Counter(ISSUED_AT + timedelta(minutes=1))
    client = use(entry(candidates, promotions, opportunity, binding, clock))
    try:
        response = client.post("/api/v1/candidate-promotions", json=payload())

        assert response.status_code == 201
        body = response.json()
        context = candidates.get_context("candidate-1")
        assert opportunity.calls == binding.calls == clock.calls == 1
        assert body["promotion_command_id"] == "promotion-1"
        assert body["candidate_id"] == "candidate-1"
        assert body["opportunity_id"] == "generated-opportunity"
        assert body["binding_id"] == "generated-binding"
        assert body["discovery_reference"] == (
            issuance.candidate_identity.discovery_reference
        )
        assert body["discovery_command_id"] == context.command_id
        assert body["discovery_execution_id"] == context.discovery_execution_id
        assert body["finalized_group_id"] == issuance.finalized_group_id
        assert body["market_observation_identity"]["scope"] == (
            context.market_observation_identity.scope.value
        )
        assert body["lifecycle_status"] == OpportunityLifecycleStatus.DISCOVERED.value
        assert body["lifecycle_version"] == 1
        assert body["title"] == "Camera"
        assert body["admission_recommendation"] == "WATCH"
        assert body["admission_score"] == 70
        assert body["admission_roi"] == 25
        assert body["currency"] == "USD"
        assert body["admission_safety_status"] == "READY"
        assert datetime.fromisoformat(body["requested_at"]) == ISSUED_AT
        assert datetime.fromisoformat(body["promoted_at"]) == (
            ISSUED_AT + timedelta(minutes=1)
        )
        assert body["committed_at"] == body["promoted_at"]
        assert body["replayed"] is False
        assert promotion_counts(promotions) == (1, 1, 1, 1, 1, 1)
        assert promotions.get_promotion_by_candidate("candidate-1").binding_id == (
            body["binding_id"]
        )
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_candidate_promotion_api_preserves_explicit_opportunity_id(tmp_path):
    path = tmp_path / "promotion-explicit.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    opportunity = Fail()
    binding = Counter("generated-binding")
    client = use(entry(candidates, promotions, opportunity, binding))
    try:
        response = client.post(
            "/api/v1/candidate-promotions",
            json=payload(opportunity_id="caller-opportunity"),
        )

        assert response.status_code == 201
        assert response.json()["opportunity_id"] == "caller-opportunity"
        assert opportunity.calls == 0
        assert binding.calls == 1
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_candidate_promotion_api_exact_replay_and_alias_skip_identity(tmp_path):
    path = tmp_path / "promotion-replay.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    first_client = use(entry(candidates, promotions))
    try:
        first = first_client.post("/api/v1/candidate-promotions", json=payload())
        assert first.status_code == 201
    finally:
        clear_overrides()

    opportunity = Fail()
    binding = Fail()
    replay_clock = Fail()
    replay_client = use(
        entry(candidates, promotions, opportunity, binding, replay_clock)
    )
    try:
        replay = replay_client.post(
            "/api/v1/candidate-promotions", json=payload()
        )
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert opportunity.calls == binding.calls == replay_clock.calls == 0
    finally:
        clear_overrides()

    alias_clock = Counter(ISSUED_AT + timedelta(minutes=2))
    alias_client = use(
        entry(candidates, promotions, opportunity, binding, alias_clock)
    )
    try:
        alias = alias_client.post(
            "/api/v1/candidate-promotions",
            json=payload(
                promotion_command_id="promotion-alias",
                requested_at=(ISSUED_AT + timedelta(hours=1)).isoformat(),
            ),
        )
        assert alias.status_code == 200
        assert alias.json()["opportunity_id"] == first.json()["opportunity_id"]
        assert alias.json()["binding_id"] == first.json()["binding_id"]
        assert alias.json()["promotion_command_id"] == "promotion-alias"
        assert datetime.fromisoformat(alias.json()["committed_at"]) == (
            ISSUED_AT + timedelta(minutes=2)
        )
        assert opportunity.calls == binding.calls == 0
        assert alias_clock.calls == 1
        assert promotion_counts(promotions) == (1, 1, 1, 1, 1, 2)
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_candidate_promotion_api_restart_replay_skips_dependencies(tmp_path):
    path = tmp_path / "promotion-restart.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    client = use(entry(candidates, promotions))
    try:
        first = client.post("/api/v1/candidate-promotions", json=payload())
        assert first.status_code == 201
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()
        close_all(*sources)

    candidates = SQLiteCandidateIssuanceRepository(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    dependencies = tuple(Fail() for _ in range(3))
    client = use(entry(candidates, promotions, *dependencies))
    try:
        replay = client.post("/api/v1/candidate-promotions", json=payload())

        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert all(dependency.calls == 0 for dependency in dependencies)
        assert promotion_counts(promotions) == (1, 1, 1, 1, 1, 1)
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()


@pytest.mark.parametrize(
    ("error", "status_code"),
    (
        (CandidateForPromotionNotFoundError("missing Candidate"), 404),
        (CandidatePromotionContextNotFoundError("missing Context"), 404),
        (CandidatePromotionIdentityConflictError("lineage differs"), 409),
        (CandidateAlreadyPromotedError("subject differs"), 409),
        (CandidatePromotionCommandConflictError("payload differs"), 409),
        (CandidatePromotionPersistenceError("write failed"), 503),
    ),
)
def test_candidate_promotion_api_maps_application_failures(error, status_code):
    class Entry:
        def execute(self, command):
            raise error

    client = use(Entry())
    try:
        response = client.post("/api/v1/candidate-promotions", json=payload())

        assert response.status_code == status_code
        assert response.json()["detail"] == str(error)
    finally:
        clear_overrides()


def test_candidate_promotion_api_malformed_request_is_rejected():
    client = TestClient(app)

    response = client.post(
        "/api/v1/candidate-promotions",
        json=payload(admission_score="not-a-number", unexpected="value"),
    )

    assert response.status_code == 422


def test_candidate_promotion_api_repository_failure_rolls_back_all_writes(
    tmp_path,
):
    path = tmp_path / "promotion-rollback.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)

    def fail_receipt(value):
        raise sqlite3.OperationalError("forced receipt failure")

    promotions._insert_receipt = fail_receipt
    client = use(entry(candidates, promotions))
    try:
        response = client.post("/api/v1/candidate-promotions", json=payload())

        assert response.status_code == 503
        assert promotion_counts(promotions) == (0, 0, 0, 0, 0, 0)
        assert not promotions._connection.in_transaction
    finally:
        clear_overrides()
        promotions.close()
        candidates.close()
        close_all(*sources)


@pytest.mark.parametrize("alias", (False, True))
def test_candidate_promotion_api_concurrent_requests_converge(tmp_path, monkeypatch, alias):
    path = tmp_path / f"promotion-concurrent-{alias}.db"
    sources, candidates, _, _, _ = prepare(path)
    candidates.close()
    close_all(*sources)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)

    requests = (
        payload(),
        payload(
            promotion_command_id=("promotion-2" if alias else "promotion-1"),
            requested_at=(
                ISSUED_AT + (timedelta(hours=1) if alias else timedelta())
            ).isoformat(),
        ),
    )

    def promote(body):
        with TestClient(app) as client:
            return client.post("/api/v1/candidate-promotions", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(promote, requests))

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["opportunity_id"] for response in responses}) == 1
    assert len({response.json()["binding_id"] for response in responses}) == 1
    promotions = SQLiteCandidatePromotionRepository(path)
    try:
        assert promotion_counts(promotions) == (
            (1, 1, 1, 1, 1, 2) if alias else (1, 1, 1, 1, 1, 1)
        )
    finally:
        promotions.close()


def test_candidate_promotion_api_does_not_replace_direct_validation_or_other_apis():
    paths = {route.path for route in app.routes}

    assert "/api/v1/candidate-promotions" in paths
    assert "/api/v1/validation-queue" in paths
    assert "/api/v1/discovery/executions" in paths
    assert "/api/v1/candidates" in paths
    assert "/api/v1/product-snapshots/capture" in paths
    assert "/api/v1/price-analyses" in paths
