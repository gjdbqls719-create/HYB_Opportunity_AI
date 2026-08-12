from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient

from app.application.candidate_promotion import CandidatePromotionProductionEntry
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from app.infrastructure.product_observation import SQLiteProductSnapshotCaptureRepository
from app.web import app, get_candidate_promotion_entry
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_product_snapshot_capture_production_entry import (
    capture_request, close_all, prepare, production_entry,
)


def test_candidate_promotion_v2_openapi_has_no_legacy_decision_inputs():
    schemas = TestClient(app).get("/openapi.json").json()["components"]["schemas"]

    properties = schemas["CandidatePromotionV2Request"]["properties"]

    assert properties["contract_version"]["const"] == "2.0.0"
    assert {
        "admission_recommendation",
        "admission_score",
        "admission_roi",
        "admission_safety_status",
        "title",
        "currency",
        "opportunity_id",
    }.isdisjoint(properties)


def _v2_payload(**changes):
    value = {
        "contract_version": "2.0.0", "promotion_command_id": "promotion-v2-command-1",
        "candidate_id": "candidate-1", "finalized_group_id": "group-opaque-1",
        "representative_product_snapshot_id": "product-snapshot-1",
        "operator_id": "founder",
        "reason": "selected exact product provenance for deeper validation",
        "requested_at": ISSUED_AT.isoformat(),
    }
    value.update(changes)
    return value


def _prepared_v2(tmp_path):
    path = tmp_path / "promotion-v2.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    production_entry(candidates, sources[2], captures,
        Counter(ISSUED_AT + timedelta(minutes=1))).execute(capture_request(issuance))
    promotions = SQLiteCandidatePromotionRepository(path)
    entry = CandidatePromotionProductionEntry(
        candidate_repository=candidates, product_snapshot_capture_repository=captures,
        promotion_repository=promotions,
        opportunity_id_generator=Counter("opportunity-v2-1"),
        binding_id_generator=Counter("binding-v2-1"),
        admission_id_generator=Counter("admission-v2-1"),
        clock=Counter(ISSUED_AT + timedelta(minutes=2)),
    )
    return sources, candidates, captures, promotions, entry


def _close(resources):
    sources, candidates, captures, promotions, _ = resources
    app.dependency_overrides.clear()
    promotions.close(); captures.close(); candidates.close(); close_all(*sources)


def test_candidate_promotion_v2_http_persists_exact_product_lineage(tmp_path):
    resources = _prepared_v2(tmp_path)
    sources, candidates, captures, promotions, entry = resources
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    try:
        response = TestClient(app).post("/api/v1/candidate-promotions", json=_v2_payload())
        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["opportunity_id"], body["binding_id"], body["admission_id"]) == (
            "opportunity-v2-1", "binding-v2-1", "admission-v2-1")
        assert body["product_snapshot_capture_command_id"] == "capture-command-1"
        assert body["product_snapshot_ids"] == ["product-snapshot-1", "product-snapshot-2"]
        assert body["representative_product_snapshot_id"] == "product-snapshot-1"
        assert body["admission_kind"] == "founder_selected_for_deeper_validation"
        assert {"admission_recommendation", "admission_score", "admission_roi",
                "admission_safety_status"}.isdisjoint(body)
        item = promotions.get_queue_item("opportunity-v2-1")
        assert item.admission_basis.product_snapshot_ids == (
            "product-snapshot-1", "product-snapshot-2")
        assert item.title == body["title"] == "Observed Product"
    finally:
        _close(resources)


def test_candidate_promotion_v2_replay_and_changed_payload(tmp_path):
    resources = _prepared_v2(tmp_path)
    promotions, entry = resources[3], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    client = TestClient(app)
    try:
        first = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        replay = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        changed = client.post("/api/v1/candidate-promotions", json=_v2_payload(reason="changed"))
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert changed.status_code == 409
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM candidate_promotion_v2_admission_history").fetchone()[0] == 1
    finally:
        _close(resources)


def test_candidate_promotion_v2_same_subject_alias_is_append_only(tmp_path):
    resources = _prepared_v2(tmp_path)
    promotions, entry = resources[3], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    client = TestClient(app)
    try:
        first = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        alias = client.post("/api/v1/candidate-promotions", json=_v2_payload(
            promotion_command_id="promotion-v2-alias",
            requested_at=(ISSUED_AT + timedelta(hours=1)).isoformat(),
        ))
        assert first.status_code == 201
        assert alias.status_code == 200
        assert alias.json()["opportunity_id"] == first.json()["opportunity_id"]
        assert alias.json()["binding_id"] == first.json()["binding_id"]
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_history").fetchone()[0] == 1
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_receipts").fetchone()[0] == 2
    finally:
        _close(resources)


def test_candidate_promotion_v2_wrong_representative_fails_closed(tmp_path):
    resources = _prepared_v2(tmp_path)
    promotions, entry = resources[3], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    try:
        response = TestClient(app).post("/api/v1/candidate-promotions",
            json=_v2_payload(representative_product_snapshot_id="product-snapshot-2"))
        assert response.status_code == 409
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_history").fetchone()[0] == 0
    finally:
        _close(resources)


def test_candidate_promotion_v2_missing_capture_and_wrong_group_fail_closed(tmp_path):
    resources = _prepared_v2(tmp_path)
    promotions, captures, entry = resources[3], resources[2], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    client = TestClient(app)
    try:
        wrong_group = client.post("/api/v1/candidate-promotions",
            json=_v2_payload(finalized_group_id="missing-group"))
        assert wrong_group.status_code == 409
        captures._connection.execute(
            "DROP TRIGGER trg_product_snapshot_capture_receipts_no_delete"
        )
        captures._connection.execute(
            "DELETE FROM product_snapshot_capture_receipts WHERE command_id='capture-command-1'"
        )
        captures._connection.commit()
        missing = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        assert missing.status_code == 404
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_history").fetchone()[0] == 0
    finally:
        _close(resources)


def test_candidate_promotion_v1_and_v2_never_alias(tmp_path):
    resources = _prepared_v2(tmp_path)
    promotions, entry = resources[3], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    client = TestClient(app)
    legacy = {
        "promotion_command_id": "legacy-promotion", "candidate_id": "candidate-1",
        "title": "legacy", "admission_recommendation": "WATCH",
        "admission_score": 1, "admission_roi": 1, "currency": "USD",
        "admission_safety_status": "READY", "operator_id": "founder",
        "reason": "historical v1 test", "requested_at": ISSUED_AT.isoformat(),
    }
    try:
        assert client.post("/api/v1/candidate-promotions", json=legacy).status_code == 201
        conflict = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        assert conflict.status_code == 409
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_history").fetchone()[0] == 1
        assert promotions._connection.execute(
            "SELECT COUNT(*) FROM candidate_promotion_v2_admission_history").fetchone()[0] == 0
    finally:
        _close(resources)


def test_candidate_promotion_v2_commit_failure_rolls_back_and_retry_succeeds(
    tmp_path, monkeypatch
):
    resources = _prepared_v2(tmp_path)
    promotions, entry = resources[3], resources[4]
    app.dependency_overrides[get_candidate_promotion_entry] = lambda: entry
    client = TestClient(app)
    original = promotions._commit_promotion
    try:
        monkeypatch.setattr(
            promotions, "_commit_promotion",
            lambda: (_ for _ in ()).throw(sqlite3.OperationalError("commit failed")),
        )
        failed = client.post("/api/v1/candidate-promotions", json=_v2_payload())
        assert failed.status_code == 503
        for table in (
            "opportunity_candidate_promotion_history",
            "opportunity_candidate_promotion_v2_source_history",
            "candidate_promotion_v2_admission_history",
            "opportunity_candidate_promotion_receipts",
        ):
            assert promotions._connection.execute(
                f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        monkeypatch.setattr(promotions, "_commit_promotion", original)
        assert client.post("/api/v1/candidate-promotions", json=_v2_payload()).status_code == 201
    finally:
        _close(resources)
