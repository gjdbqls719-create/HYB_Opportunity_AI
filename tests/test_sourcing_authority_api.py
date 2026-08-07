from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.application.sourcing import (
    AdmitFounderSourcing,
    ReviseFounderSourcingQuote,
    SourcingAuthorityProductionEntry,
)
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository
from app.web import app, get_sourcing_authority_entry
import app.web as web_module
from test_sourcing_authority_contract import NOW


def payload(**changes):
    value = {
        "command_id": "sourcing-command-1",
        "requested_at": NOW.isoformat(),
        "verified_at": (NOW - timedelta(minutes=5)).isoformat(),
        "operator_id": "founder-1",
        "selling_product_lineage": {
            "opportunity_id": "opp-1",
            "discovery_reference": "discovery-1",
            "candidate_id": "candidate-1",
            "candidate_opportunity_binding_id": "binding-1",
            "product_observation_snapshot_id": "product-snapshot-1",
            "market_observation_identity": {
                "scope": "listing", "market": "KR", "marketplace": "coupang",
                "canonical_product_id": None, "marketplace_item_id": "selling-1",
                "normalized_query": None, "category": None,
                "variant_identity": "black", "condition": "new",
                "window_started_at": NOW.isoformat(), "window_ended_at": NOW.isoformat(),
            },
        },
        "supplier_platform": "1688",
        "external_supplier_reference": "supplier-ext-1",
        "supplier_display_name": "Factory A",
        "external_product_reference": "listing-ext-1",
        "option_reference": "black-220v", "sku_reference": "sku-1",
        "source_url": "https://example.test/product/1",
        "product_observed_at": NOW.isoformat(),
        "quoted_unit_price": {"availability": "known", "amount": "12.3400", "currency": "CNY"},
        "minimum_order_quantity": {"availability": "known", "quantity": 10},
        "quoted_quantity": {"availability": "known", "quantity": 100},
        "shipping_terms": [
            {"scope": "supplier_side", "cost": {"availability": "known", "amount": "20.50", "currency": "CNY"}},
            {"scope": "international_freight", "cost": {"availability": "unknown", "amount": None, "currency": None}},
            {"scope": "domestic_inbound", "cost": {"availability": "not_applicable", "amount": None, "currency": None}},
        ],
        "lead_time_availability": "known", "lead_time_days": 14,
        "quote_observed_at": NOW.isoformat(), "quote_valid_until": None,
        "quote_evidence": {"kind": "manual_entry", "source_reference": "founder:quote", "observed_at": NOW.isoformat(), "artifact_reference": None},
        "match_status": "verified_match",
        "match_evidence": {"kind": "manual_entry", "source_reference": "founder:match", "observed_at": NOW.isoformat(), "artifact_reference": None},
        "proposal_score": "91.25", "proposal_version": "product-matching-v2",
    }
    value.update(changes)
    return value


def revision_payload(**changes):
    value = {
        "command_id": "revision-command-1", "expected_revision": 1,
        "requested_at": (NOW + timedelta(hours=1)).isoformat(),
        "operator_id": "founder-1",
        "quoted_unit_price": {"availability": "known", "amount": "11.90", "currency": "CNY"},
        "minimum_order_quantity": {"availability": "known", "quantity": 20},
        "quoted_quantity": {"availability": "known", "quantity": 200},
        "shipping_terms": payload()["shipping_terms"],
        "lead_time_availability": "unknown", "lead_time_days": None,
        "quote_observed_at": NOW.isoformat(), "quote_valid_until": None,
        "quote_evidence": payload()["quote_evidence"],
    }
    value.update(changes)
    return value


class Counter:
    def __init__(self, value): self.value, self.calls = value, 0
    def __call__(self): self.calls += 1; return self.value


def entry(repository, *, fail=False):
    def source(value):
        return (lambda: (_ for _ in ()).throw(AssertionError("dependency called"))) if fail else Counter(value)
    generators = tuple(source(value) for value in ("supplier-1", "product-1", "quote-1", "match-1", "admission-1"))
    admitted = source(NOW + timedelta(minutes=1)); committed = source(NOW + timedelta(minutes=2))
    return SourcingAuthorityProductionEntry(
        AdmitFounderSourcing(repository, supplier_id_generator=generators[0],
            sourcing_product_id_generator=generators[1], quote_id_generator=generators[2],
            match_verification_id_generator=generators[3], admission_id_generator=generators[4],
            admission_clock=admitted, committed_clock=committed),
        ReviseFounderSourcingQuote(repository, admission_clock=admitted, committed_clock=committed),
    ), generators, admitted, committed


def client(value):
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: value
    return TestClient(app)


def test_fresh_admission_returns_authoritative_persisted_response(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "sourcing-api.db")
    production, _, _, _ = entry(repository)
    web = client(production)
    try:
        response = web.post("/api/v1/sourcing/admissions", json=payload())
        assert response.status_code == 201
        body = response.json()
        assert body["admission_id"] == "admission-1"
        assert body["supplier"]["supplier_id"] == "supplier-1"
        assert body["sourcing_product"]["sourcing_product_id"] == "product-1"
        assert body["quote"]["quote_id"] == "quote-1"
        assert body["match_verification"]["verification_id"] == "match-1"
        assert body["requested_at"] == NOW.isoformat()
        assert body["verified_at"] == (NOW - timedelta(minutes=5)).isoformat()
        assert body["admitted_at"] == (NOW + timedelta(minutes=1)).isoformat()
        assert body["committed_at"] == (NOW + timedelta(minutes=2)).isoformat()
        assert repository.get_admission("admission-1").admitted_at.isoformat() == body["admitted_at"]
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_exact_and_restart_replay_reuse_every_authoritative_fact(tmp_path):
    path = tmp_path / "replay.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    first_entry, _, _, _ = entry(repository)
    web = client(first_entry)
    first = web.post("/api/v1/sourcing/admissions", json=payload())
    before = tuple(repository._connection.execute(
        "SELECT (SELECT COUNT(*) FROM founder_sourcing_admission_history), (SELECT COUNT(*) FROM sourcing_admission_receipts)"
    ).fetchone())
    replay_entry, _, _, _ = entry(repository, fail=True)
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: replay_entry
    replay = web.post("/api/v1/sourcing/admissions", json=payload())
    assert first.status_code == 201 and replay.status_code == 200
    expected = first.json(); expected["replayed"] = True
    assert replay.json() == expected
    assert before == (1, 1)
    repository.close()
    restarted = SQLiteSourcingAuthorityRepository(path)
    restarted_entry, _, _, _ = entry(restarted, fail=True)
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: restarted_entry
    assert web.post("/api/v1/sourcing/admissions", json=payload()).json() == expected
    app.dependency_overrides.clear(); restarted.close()


@pytest.mark.parametrize("field", (
    "admission_id", "supplier_id", "sourcing_product_id", "quote_id",
    "match_verification_id", "admitted_at", "committed_at", "unexpected",
))
def test_server_owned_and_extra_fields_are_rejected(field):
    body = payload(); body[field] = "injected"
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: object()
    try:
        response = TestClient(app).post("/api/v1/sourcing/admissions", json=body)
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("change", (
    {"requested_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"verified_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"quoted_unit_price": {"availability": "known", "amount": "99.00", "currency": "CNY"}},
))
def test_changed_authoritative_payload_conflicts(change, tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "changed.db")
    production = entry(repository)[0]; web = client(production)
    try:
        assert web.post("/api/v1/sourcing/admissions", json=payload()).status_code == 201
        assert web.post("/api/v1/sourcing/admissions", json=payload(**change)).status_code == 409
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_unknown_not_applicable_moq_and_artifact_are_lossless(tmp_path):
    artifact = {
        "artifact_id": "artifact-1", "artifact_type": "screenshot",
        "artifact_origin": "manual", "source_type": "manual_input",
        "sha256": "a" * 64, "captured_at": NOW.isoformat(),
        "width": 100, "height": 200, "mime_type": "image/png",
        "file_size": 123, "schema_version": "artifact-v1",
    }
    body = payload(
        minimum_order_quantity={"availability": "unknown", "quantity": None},
        quoted_quantity={"availability": "not_applicable", "quantity": None},
    )
    body["quote_evidence"] = {
        "kind": "artifact", "source_reference": "quote-artifact",
        "observed_at": NOW.isoformat(), "artifact_reference": artifact,
    }
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "facts.db")
    web = client(entry(repository)[0])
    try:
        response = web.post("/api/v1/sourcing/admissions", json=body)
        assert response.status_code == 201
        quote = response.json()["quote"]
        assert quote["minimum_order_quantity"] == {"availability": "unknown", "quantity": None}
        assert quote["quoted_quantity"] == {"availability": "not_applicable", "quantity": None}
        assert quote["shipping_terms"][1]["cost"] == {"availability": "unknown", "amount": None, "currency": None}
        assert quote["evidence"]["artifact_reference"] == artifact
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_verified_match_required_and_unknown_admission_maps_http():
    repository = SQLiteSourcingAuthorityRepository(":memory:")
    web = client(entry(repository)[0])
    try:
        assert web.post("/api/v1/sourcing/admissions", json=payload(match_status="needs_review")).status_code == 422
        assert web.post("/api/v1/sourcing/admissions/missing/quote-revisions", json=revision_payload()).status_code == 404
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_quote_revision_fresh_exact_and_restart_replay(tmp_path):
    path = tmp_path / "revision.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    web = client(entry(repository)[0])
    first = web.post("/api/v1/sourcing/admissions", json=payload()).json()
    fresh = web.post(f"/api/v1/sourcing/admissions/{first['admission_id']}/quote-revisions", json=revision_payload())
    assert fresh.status_code == 201
    assert fresh.json()["quote"]["quote_id"] == first["quote"]["quote_id"]
    assert fresh.json()["revision"] == fresh.json()["quote"]["revision"] == 2
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: entry(repository, fail=True)[0]
    replay = web.post(f"/api/v1/sourcing/admissions/{first['admission_id']}/quote-revisions", json=revision_payload())
    expected = fresh.json(); expected["replayed"] = True
    assert replay.status_code == 200 and replay.json() == expected
    repository.close()
    restarted = SQLiteSourcingAuthorityRepository(path)
    app.dependency_overrides[get_sourcing_authority_entry] = lambda: entry(restarted, fail=True)[0]
    assert web.post(f"/api/v1/sourcing/admissions/{first['admission_id']}/quote-revisions", json=revision_payload()).json() == expected
    app.dependency_overrides.clear(); restarted.close()


def test_quote_revision_changed_payload_conflicts(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "revision-conflict.db")
    web = client(entry(repository)[0])
    try:
        admission_id = web.post("/api/v1/sourcing/admissions", json=payload()).json()["admission_id"]
        assert web.post(f"/api/v1/sourcing/admissions/{admission_id}/quote-revisions", json=revision_payload()).status_code == 201
        changed = revision_payload(); changed["quoted_quantity"] = {"availability": "known", "quantity": 999}
        assert web.post(f"/api/v1/sourcing/admissions/{admission_id}/quote-revisions", json=changed).status_code == 409
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_receipt_failure_returns_503_and_rolls_back_all_facts():
    repository = SQLiteSourcingAuthorityRepository(":memory:")
    repository._connection.execute("""CREATE TRIGGER fail_sourcing_receipt BEFORE INSERT ON
        sourcing_admission_receipts BEGIN SELECT RAISE(ABORT, 'private sqlite detail'); END""")
    web = client(entry(repository)[0])
    try:
        response = web.post("/api/v1/sourcing/admissions", json=payload())
        assert response.status_code == 503 and "private sqlite detail" not in response.text
        for table in ("sourcing_supplier_history", "sourcing_product_history",
                      "sourcing_match_verification_history", "sourcing_quote_revision_history",
                      "founder_sourcing_admission_history", "sourcing_admission_receipts"):
            assert repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert repository._connection.in_transaction is False
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_domain_invalid_money_and_naive_time_return_422():
    repository = SQLiteSourcingAuthorityRepository(":memory:")
    web = client(entry(repository)[0])
    try:
        invalid = payload(quoted_unit_price={"availability": "unknown", "amount": "0", "currency": "CNY"})
        assert web.post("/api/v1/sourcing/admissions", json=invalid).status_code == 422
        naive = payload(requested_at="2026-08-07T08:00:00")
        assert web.post("/api/v1/sourcing/admissions", json=naive).status_code == 422
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_production_composition_uses_default_database_and_closes(tmp_path, monkeypatch):
    path = tmp_path / "production.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    dependency = get_sourcing_authority_entry()
    production = next(dependency)
    repository = production.admission._repository
    assert isinstance(repository, SQLiteSourcingAuthorityRepository)
    assert repository._connection.execute("PRAGMA database_list").fetchone()[2] == str(path)
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")


def test_partial_dependency_construction_failure_closes_repository(tmp_path, monkeypatch):
    path = tmp_path / "partial.db"; captured = []
    real_repository = SQLiteSourcingAuthorityRepository
    class CapturingRepository(real_repository):
        def __init__(self, value): super().__init__(value); captured.append(self)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(web_module, "SQLiteSourcingAuthorityRepository", CapturingRepository)
    monkeypatch.setattr(web_module, "ReviseFounderSourcingQuote", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken")))
    with pytest.raises(RuntimeError, match="broken"):
        next(get_sourcing_authority_entry())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_request_scoped_concurrent_admission_converges(tmp_path, monkeypatch):
    path = tmp_path / "concurrent.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()
    def execute(_):
        return TestClient(app).post("/api/v1/sourcing/admissions", json=payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, range(2)))
    assert sorted(value.status_code for value in responses) == [200, 201]
    authoritative = [{**value.json(), "replayed": False} for value in responses]
    assert authoritative[0] == authoritative[1]
    with SQLiteSourcingAuthorityRepository(path) as repository:
        assert repository._connection.execute("SELECT COUNT(*) FROM founder_sourcing_admission_history").fetchone()[0] == 1


def test_request_scoped_concurrent_changed_payload_conflicts(tmp_path, monkeypatch):
    path = tmp_path / "concurrent-conflict.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    values = (payload(), payload(verified_at=(NOW + timedelta(seconds=1)).isoformat()))
    def execute(body):
        return TestClient(app).post("/api/v1/sourcing/admissions", json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, values))
    assert sorted(value.status_code for value in responses) == [201, 409]


def test_request_scoped_concurrent_revision_converges_and_conflicts(tmp_path, monkeypatch):
    path = tmp_path / "concurrent-revision.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    web = TestClient(app)
    admission_id = web.post("/api/v1/sourcing/admissions", json=payload()).json()["admission_id"]
    route = f"/api/v1/sourcing/admissions/{admission_id}/quote-revisions"
    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(lambda _: TestClient(app).post(route, json=revision_payload()), range(2)))
    assert sorted(value.status_code for value in same) == [200, 201]

    second_path = tmp_path / "concurrent-revision-conflict.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", second_path)
    admission_id = web.post("/api/v1/sourcing/admissions", json=payload()).json()["admission_id"]
    route = f"/api/v1/sourcing/admissions/{admission_id}/quote-revisions"
    left = revision_payload()
    right = revision_payload(quoted_unit_price={"availability": "known", "amount": "10.90", "currency": "CNY"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = tuple(pool.map(lambda body: TestClient(app).post(route, json=body), (left, right)))
    assert sorted(value.status_code for value in changed) == [201, 409]
