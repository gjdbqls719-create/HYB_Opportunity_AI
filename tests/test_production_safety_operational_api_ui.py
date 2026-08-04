from datetime import timedelta

from fastapi.testclient import TestClient

from app.application.production_safety_api import EvaluateProductionSafetyApi, GetProductionSafetyOperationalDetail
from app.infrastructure.production_safety_evaluation import SQLiteProductionSafetyEvaluationRepository
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from app.web import app, get_production_safety_api_service, get_production_safety_detail_service
from test_production_safety_evaluation_persistence import service as evaluation_service
from test_snapshot_chain_binding_persistence import BOUND, boundary as chain_boundary, command as chain_command, prepare


def seeded(path):
    prepare(path)
    with SQLiteSnapshotChainBindingRepository(path) as chains:
        chain_boundary(chains).execute(chain_command())
    repository = SQLiteProductionSafetyEvaluationRepository(path)
    opportunities = repository.verified_economics_repository
    return repository, EvaluateProductionSafetyApi(evaluation_service(repository), opportunities, repository), GetProductionSafetyOperationalDetail(repository, opportunities)


def payload(**changes):
    value = {
        "command_id": "safety-command-1",
        "snapshot_chain_binding_id": "chain-binding-1",
        "selected_product_snapshot_id": "product-1",
        "requested_at": (BOUND + timedelta(seconds=10)).isoformat(),
    }
    value.update(changes)
    return value


def test_first_commit_replay_and_authoritative_read_dto(tmp_path):
    repository, evaluate, detail = seeded(tmp_path / "api.db")
    app.dependency_overrides[get_production_safety_api_service] = lambda: evaluate
    app.dependency_overrides[get_production_safety_detail_service] = lambda: detail
    try:
        client = TestClient(app)
        first = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload())
        replay = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload())
        read = client.get("/api/v1/opportunities/opportunity-1/production-safety-evaluations")
    finally:
        app.dependency_overrides.clear(); repository.close()
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json()["evaluation_id"] == replay.json()["evaluation_id"]
    assert first.json()["replayed"] is False and replay.json()["replayed"] is True
    assert read.status_code == 200
    assert read.json()["bindings"][0]["product_snapshot_ids"] == ["product-1", "product-2"]
    assert read.json()["current"]["evaluation_id"] == first.json()["evaluation_id"]


def test_http_validation_not_found_and_conflict(tmp_path):
    repository, evaluate, detail = seeded(tmp_path / "errors.db")
    app.dependency_overrides[get_production_safety_api_service] = lambda: evaluate
    try:
        client = TestClient(app)
        naive = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload(requested_at="2026-08-04T10:00:00"))
        missing_chain = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload(snapshot_chain_binding_id="missing"))
        missing_product = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload(selected_product_snapshot_id="missing"))
        first = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload())
        conflict = client.post("/api/v1/opportunities/opportunity-1/production-safety-evaluations", json=payload(selected_product_snapshot_id="product-2"))
    finally:
        app.dependency_overrides.clear(); repository.close()
    assert naive.status_code == 422
    assert missing_chain.status_code == missing_product.status_code == 404
    assert first.status_code == 201 and conflict.status_code == 409


def test_opportunity_detail_has_explicit_safe_accessible_retry_ui():
    source = TestClient(app).get("/opportunities/opportunity-1").text
    assert "Production Safety" in source
    assert 'id="safety-binding"' in source and 'id="safety-product"' in source
    assert "No latest, first, lowest-price" in source
    assert "Reset retry command" in source
    assert 'aria-live="polite"' in source and 'role="status"' in source
    assert "textContent" in source and "innerHTML" not in source
    assert "if(!retry)retry=" in source
    assert "await load();await fetch" in source
    assert 'method:"POST"' in source
