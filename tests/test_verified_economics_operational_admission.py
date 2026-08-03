from pathlib import Path

from fastapi.testclient import TestClient

from app.application.verified_economics_admission import FinalizeVerifiedEconomicsAdmission
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_verified_economics_admission_service
from test_opportunity_market_identity_binding import command, identity, service
from test_verified_economics import complete_input


def payload(command_id="econ-command-1"):
    inputs = complete_input()
    result = {"command_id": command_id, "operator_id": "founder-1",
              "snapshot_at": "2026-01-03T01:02:03+00:00"}
    for name in ("purchase_cost", "shipping_cost", "marketplace_fee_rate", "payment_fee_rate",
                 "fixed_fee", "tax_rate", "duty_cost", "other_cost", "expected_sale_price"):
        item = getattr(inputs, name)
        evidence = item.evidence
        value = {"evidence": {"status": evidence.status.value, "source": evidence.source,
                              "observed_at": evidence.observed_at.isoformat() if evidence.observed_at else None,
                              "reference": evidence.reference}}
        if hasattr(item, "amount"):
            value.update(amount=str(item.amount) if item.amount is not None else None, currency=item.currency)
        else:
            value["rate"] = str(item.rate) if item.rate is not None else None
        result[name] = value
    return result


def client(repository):
    app.dependency_overrides[get_verified_economics_admission_service] = lambda: FinalizeVerifiedEconomicsAdmission(repository)
    return TestClient(app)


def test_admission_exact_round_trip_replay_and_conflicts(tmp_path: Path):
    database = tmp_path / "economics.db"
    repository = SQLiteValidationQueueRepository(database)
    service(repository).add(command(identity()))
    web = client(repository)
    try:
        first = web.post("/api/v1/opportunities/opp-bound/verified-economics", json=payload())
        replay = web.post("/api/v1/opportunities/opp-bound/verified-economics", json=payload())
        changed = payload(); changed["purchase_cost"]["amount"] = "999.00"
        conflict = web.post("/api/v1/opportunities/opp-bound/verified-economics", json=changed)
        duplicate = web.post("/api/v1/opportunities/opp-bound/verified-economics", json=payload("another-command"))
        assert first.status_code == 201
        assert replay.status_code == 200 and replay.json() == first.json()
        assert first.json()["purchase_cost"]["amount"] == str(complete_input().purchase_cost.amount)
        assert conflict.status_code == duplicate.status_code == 409
        assert repository._connection.execute("SELECT COUNT(*) FROM verified_economics_snapshots").fetchone()[0] == 1
        assert repository._connection.execute("SELECT COUNT(*) FROM verified_economics_admission_receipts").fetchone()[0] == 1
    finally:
        app.dependency_overrides.clear(); repository.close()
    restarted = SQLiteValidationQueueRepository(database)
    assert restarted.get_verified_economics_snapshot("opp-bound").inputs == complete_input()
    restarted.close()


def test_validation_not_found_and_atomic_rollback():
    repository = SQLiteValidationQueueRepository(":memory:")
    web = client(repository)
    try:
        assert web.post("/api/v1/opportunities/missing/verified-economics", json=payload()).status_code == 404
        service(repository).add(command(identity()))
        invalid = payload(); invalid["purchase_cost"]["amount"] = 10.25
        assert web.post("/api/v1/opportunities/opp-bound/verified-economics", json=invalid).status_code == 422
        naive = payload(); naive["snapshot_at"] = "2026-01-01T00:00:00"
        assert web.post("/api/v1/opportunities/opp-bound/verified-economics", json=naive).status_code == 422
        repository._connection.execute("""CREATE TRIGGER fail_economics_receipt BEFORE INSERT ON
        verified_economics_admission_receipts BEGIN SELECT RAISE(ABORT, 'private sqlite detail'); END""")
        failed = web.post("/api/v1/opportunities/opp-bound/verified-economics", json=payload())
        assert failed.status_code == 503 and "private sqlite detail" not in failed.text
        assert repository.get_verified_economics_snapshot("opp-bound") is None
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_receipt_is_immutable_and_request_forbids_decision_metadata():
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command(identity()))
    web = client(repository)
    try:
        body = payload(); body["readiness"] = "ready"
        assert web.post("/api/v1/opportunities/opp-bound/verified-economics", json=body).status_code == 422
        assert web.post("/api/v1/opportunities/opp-bound/verified-economics", json=payload()).status_code == 201
        import sqlite3
        for sql in ("UPDATE verified_economics_admission_receipts SET operator_id='x'",
                    "DELETE FROM verified_economics_admission_receipts"):
            try: repository._connection.execute(sql)
            except sqlite3.IntegrityError as error: assert "immutable" in str(error)
            else: raise AssertionError("immutable receipt mutation succeeded")
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_opportunity_page_has_explicit_safe_economics_contract():
    source = TestClient(app).get("/opportunities/opp-1").text
    assert "Verified Economics" in source
    assert "verified-economics" in source
    assert "innerHTML" not in source
