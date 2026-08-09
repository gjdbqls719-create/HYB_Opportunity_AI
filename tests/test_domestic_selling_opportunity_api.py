from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.domestic_selling_opportunity import (
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository
from app.web import app
from test_domestic_selling_opportunity_admission import command as domestic_command
from test_domestic_selling_opportunity_sqlite import seed
from test_sourcing_authority_api import payload as sourcing_payload


API_NOW = datetime.now(timezone.utc).replace(microsecond=0)
VERIFIED_AT = API_NOW - timedelta(minutes=2)
REQUESTED_AT = API_NOW - timedelta(minutes=1)


def _market_payload(identity):
    return {
        "scope": identity.scope.value,
        "market": identity.market,
        "marketplace": identity.marketplace,
        "canonical_product_id": identity.canonical_product_id,
        "marketplace_item_id": identity.marketplace_item_id,
        "normalized_query": identity.normalized_query,
        "category": identity.category,
        "variant_identity": identity.variant_identity,
        "condition": identity.condition,
        "window_started_at": identity.window_started_at.isoformat(),
        "window_ended_at": identity.window_ended_at.isoformat(),
    }


def domestic_payload(**changes):
    command = domestic_command()
    target = _market_payload(command.target_market_identity)
    target["window_started_at"] = (API_NOW - timedelta(minutes=4)).isoformat()
    target["window_ended_at"] = (API_NOW - timedelta(minutes=3)).isoformat()
    value = {
        "command_id": command.command_id,
        "source_product_snapshot_id": command.source_product_snapshot_id,
        "target_market_identity": target,
        "operator_id": command.operator_id,
        "product_equivalence_confirmed": command.product_equivalence_confirmed,
        "evidence_reference": command.evidence_reference,
        "verified_at": VERIFIED_AT.isoformat(),
        "requested_at": REQUESTED_AT.isoformat(),
        "policy_name": command.policy_name,
        "policy_version": command.policy_version,
    }
    value.update(changes)
    return value


def domestic_sourcing_payload(admission_id: str, **changes):
    value = sourcing_payload()
    value["selling_product_lineage"] = {
        "kind": "domestic_selling_admission",
        "domestic_selling_admission_id": admission_id,
    }
    value.update(changes)
    return value


@pytest.fixture
def production_client(tmp_path, monkeypatch):
    path = tmp_path / "domestic-selling-api.db"
    seed(path)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client, path
    app.dependency_overrides.clear()


def test_fresh_domestic_admission_returns_exact_committed_publication(production_client):
    client, path = production_client
    response = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["command_id"] == "domestic-command-1"
    assert body["admission_id"]
    assert body["source_opportunity_identity"]["opportunity_id"] == "source-opportunity-1"
    assert body["domestic_opportunity_identity"]["opportunity_id"] != "source-opportunity-1"
    assert body["lifecycle"] == {
        "status": "discovered",
        "version": 1,
    }
    assert body["market_binding"]["market_observation_identity"]["market"] == "KR"
    assert body["product_equivalence"]["confirmed"] is True
    assert body["replayed"] is False
    assert body["requested_at"] == REQUESTED_AT.isoformat()
    assert body["verified_at"] == VERIFIED_AT.isoformat()

    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    try:
        persisted = repository.get_admission(body["admission_id"])
        assert persisted.admission.domestic_opportunity_identity.opportunity_id == (
            body["domestic_opportunity_identity"]["opportunity_id"]
        )
        assert persisted.receipt.committed_at.isoformat() == body["committed_at"]
    finally:
        repository.close()


@pytest.mark.parametrize("field", ("domestic_opportunity_id", "admission_id", "admitted_at", "committed_at"))
def test_domestic_server_owned_fields_are_rejected(production_client, field):
    client, _ = production_client
    body = domestic_payload()
    body[field] = "caller-owned"
    response = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=body,
    )
    assert response.status_code == 422


def test_domestic_missing_source_validation_replay_and_conflicts(production_client):
    client, _ = production_client
    route = "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions"

    missing = client.post(
        "/api/v1/opportunities/missing/domestic-selling-admissions",
        json=domestic_payload(),
    )
    assert missing.status_code == 404

    invalid = domestic_payload()
    invalid["target_market_identity"]["scope"] = "search_query"
    assert client.post(route, json=invalid).status_code == 422

    first = client.post(route, json=domestic_payload())
    replay = client.post(route, json=domestic_payload())
    changed = client.post(route, json=domestic_payload(evidence_reference="changed"))
    alias = client.post(route, json=domestic_payload(command_id="domestic-command-2"))
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}
    assert changed.status_code == 409
    assert alias.status_code == 409


def test_domestic_restart_replay_preserves_rows_and_identities(production_client):
    client, path = production_client
    route = "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions"
    first = client.post(route, json=domestic_payload())
    assert first.status_code == 201

    with TestClient(app) as restarted:
        replay = restarted.post(route, json=domestic_payload())
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}

    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    try:
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_history"
        ).fetchone()[0] == 1
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_receipts"
        ).fetchone()[0] == 1
    finally:
        repository.close()


def test_domestic_admission_concurrent_same_command_converges(production_client):
    _, path = production_client
    route = "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions"

    def execute(_):
        return TestClient(app).post(route, json=domestic_payload())

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 201]
    normalized = [{**response.json(), "replayed": False} for response in responses]
    assert normalized[0] == normalized[1]

    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    try:
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_history"
        ).fetchone()[0] == 1
    finally:
        repository.close()


def test_domestic_sourcing_variant_uses_exact_admission_and_keeps_product_match(production_client):
    client, path = production_client
    domestic = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    ).json()

    request = domestic_sourcing_payload(domestic["admission_id"])
    response = client.post("/api/v1/sourcing/admissions", json=request)
    assert response.status_code == 201
    lineage = response.json()["selling_product_lineage"]
    assert lineage["kind"] == "domestic_selling_admission"
    assert lineage["domestic_selling_admission_id"] == domestic["admission_id"]
    assert lineage["opportunity_id"] == domestic["domestic_opportunity_identity"]["opportunity_id"]
    assert response.json()["match_verification"]["status"] == "verified_match"

    repository = SQLiteSourcingAuthorityRepository(path)
    try:
        persisted = repository.get_admission(response.json()["admission_id"])
        assert persisted.selling_product_lineage.domestic_selling_admission_id == domestic["admission_id"]
    finally:
        repository.close()

    rejected = domestic_sourcing_payload(
        domestic["admission_id"],
        command_id="sourcing-command-unverified",
        match_status="needs_review",
    )
    assert client.post("/api/v1/sourcing/admissions", json=rejected).status_code == 422


def test_api_only_domestic_to_o2_sourcing_replay_and_restart(production_client):
    client, path = production_client
    domestic_route = "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions"
    domestic = client.post(domestic_route, json=domestic_payload())
    sourcing = client.post(
        "/api/v1/sourcing/admissions",
        json=domestic_sourcing_payload(domestic.json()["admission_id"]),
    )
    assert domestic.status_code == 201 and sourcing.status_code == 201
    assert sourcing.json()["selling_product_lineage"]["opportunity_id"] == (
        domestic.json()["domestic_opportunity_identity"]["opportunity_id"]
    )

    with TestClient(app) as restarted:
        domestic_replay = restarted.post(domestic_route, json=domestic_payload())
        sourcing_replay = restarted.post(
            "/api/v1/sourcing/admissions",
            json=domestic_sourcing_payload(domestic.json()["admission_id"]),
        )
    assert domestic_replay.status_code == 200
    assert sourcing_replay.status_code == 200
    assert sourcing_replay.json() == {**sourcing.json(), "replayed": True}

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM founder_sourcing_admission_history"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_wrong_domestic_admission_and_changed_lineage_conflict(production_client):
    client, _ = production_client
    domestic = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    ).json()
    missing = client.post(
        "/api/v1/sourcing/admissions",
        json=domestic_sourcing_payload("missing-domestic-admission"),
    )
    assert missing.status_code == 404

    first = client.post(
        "/api/v1/sourcing/admissions",
        json=domestic_sourcing_payload(domestic["admission_id"]),
    )
    changed = client.post(
        "/api/v1/sourcing/admissions",
        json=domestic_sourcing_payload("missing-domestic-admission"),
    )
    assert first.status_code == 201
    assert changed.status_code == 409


def test_domestic_sourcing_variant_rejects_repeated_o1_or_o2_claims(production_client):
    client, _ = production_client
    body = domestic_sourcing_payload("domestic-admission-1")
    body["selling_product_lineage"]["opportunity_id"] = "source-opportunity-1"
    response = client.post("/api/v1/sourcing/admissions", json=body)
    assert response.status_code == 422


def test_failed_sourcing_does_not_mutate_domestic_admission(production_client):
    client, path = production_client
    domestic = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    ).json()
    invalid = domestic_sourcing_payload(domestic["admission_id"], match_status="needs_review")
    assert client.post("/api/v1/sourcing/admissions", json=invalid).status_code == 422

    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    try:
        assert repository.get_admission(domestic["admission_id"]).admission.admission_id == domestic["admission_id"]
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_history"
        ).fetchone()[0] == 1
    finally:
        repository.close()


def test_legacy_candidate_sourcing_request_shape_remains_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "legacy-sourcing-api.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    with TestClient(app) as client:
        response = client.post("/api/v1/sourcing/admissions", json=sourcing_payload())
    assert response.status_code == 201
    assert "kind" not in response.json()["selling_product_lineage"]
    assert response.json()["selling_product_lineage"]["candidate_id"] == "candidate-1"


def test_domestic_persistence_failure_returns_503_and_rolls_back_o2(tmp_path, monkeypatch):
    path = tmp_path / "domestic-api-rollback.db"
    seed(path)
    real_repository = SQLiteDomesticSellingOpportunityAdmissionRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            self._connection.execute(
                """CREATE TRIGGER fail_domestic_api_receipt BEFORE INSERT ON
                domestic_selling_opportunity_admission_receipts
                BEGIN SELECT RAISE(ABORT, 'private sqlite detail'); END"""
            )

    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(
        web_module,
        "SQLiteDomesticSellingOpportunityAdmissionRepository",
        FailingRepository,
    )
    response = TestClient(app).post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    )
    assert response.status_code == 503
    assert "private sqlite detail" not in response.text

    repository = real_repository(path)
    try:
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_history"
        ).fetchone()[0] == 0
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM domestic_selling_opportunity_admission_receipts"
        ).fetchone()[0] == 0
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM opportunity_lifecycles"
        ).fetchone()[0] == 1
    finally:
        repository.close()


def test_domestic_dependency_closes_on_success_and_partial_construction(tmp_path, monkeypatch):
    path = tmp_path / "domestic-api-cleanup.db"
    seed(path)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)

    dependency = web_module.get_domestic_selling_opportunity_entry()
    entry = next(dependency)
    repository = entry._repository
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")

    captured = []
    real_repository = SQLiteDomesticSellingOpportunityAdmissionRepository

    class CapturingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(
        web_module,
        "SQLiteDomesticSellingOpportunityAdmissionRepository",
        CapturingRepository,
    )
    monkeypatch.setattr(
        web_module,
        "ProductionDomesticSellingOpportunityIdentityGenerator",
        lambda: (_ for _ in ()).throw(RuntimeError("broken composition")),
    )
    with pytest.raises(RuntimeError, match="broken composition"):
        next(web_module.get_domestic_selling_opportunity_entry())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_domestic_concurrent_changed_payload_has_one_winner(tmp_path, monkeypatch):
    path = tmp_path / "domestic-api-concurrent-conflict.db"
    seed(path)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    route = "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions"
    bodies = (domestic_payload(), domestic_payload(evidence_reference="changed"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(
            pool.map(lambda body: TestClient(app).post(route, json=body), bodies)
        )
    assert sorted(response.status_code for response in responses) == [201, 409]
