from pathlib import Path

from fastapi.testclient import TestClient

from app.application.competition_observation_admission import FinalizeCompetitionObservationAdmission
from app.application.decision_readiness import DecisionReadinessService
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_competition_admission_service
from test_opportunity_market_identity_binding import command, identity as bound_identity, service
from types import SimpleNamespace


def body(command_id="competition-command-1"):
    identity = bound_identity()
    identity_data = {name: (getattr(identity, name).value if name == "scope" else
        getattr(identity, name).isoformat() if name.startswith("window_") else getattr(identity, name))
        for name in ("scope", "market", "marketplace", "canonical_product_id", "marketplace_item_id",
                     "normalized_query", "category", "variant_identity", "condition", "window_started_at", "window_ended_at")}
    observed = identity.window_ended_at.isoformat()
    evidence = {}
    for name, value, unit in (("competitor_count", 20, "count"), ("rocket_seller_count", 4, "count"),
                              ("price_spread", "20.00", "USD"), ("median_price", "100.00", "USD")):
        evidence[name] = {"value": value, "source": "authoritative-market-capture",
            "reference": f"capture:{name}", "observed_at": observed, "status": "observed",
            "confidence": "0.90", "collection_method": "operator_capture", "unit": unit}
    return {"command_id": command_id, "operator_id": "operator-1", "submitted_at": observed,
            "observation_id": "competition-observation-1", "identity": identity_data,
            "observed_at": observed, "evidence": evidence}


def setup(database=":memory:"):
    opportunities = SQLiteValidationQueueRepository(database)
    observations = SQLiteMarketObservationRepository(database)
    service(opportunities).add(command(bound_identity()))
    app.dependency_overrides[get_competition_admission_service] = lambda: FinalizeCompetitionObservationAdmission(opportunities, observations)
    return opportunities, observations, TestClient(app)


def test_raw_observation_analysis_atomic_persistence_and_exact_replay(tmp_path: Path):
    database = tmp_path / "competition.db"
    opportunities, observations, client = setup(database)
    try:
        first = client.post("/api/v1/opportunities/opp-bound/competition-observations", json=body())
        replay = client.post("/api/v1/opportunities/opp-bound/competition-observations", json=body())
        assert first.status_code == 201
        assert replay.status_code == 200 and replay.json() == first.json()
        assert first.json()["assessment"]["competition_level"] == "medium"
        assert first.json()["assessment"]["confidence"] == "0.90"
        assert first.json()["observation"]["evidence"]["price_spread"]["value"] == "20.00"
    finally:
        app.dependency_overrides.clear(); observations.close(); opportunities.close()
    restarted = SQLiteMarketObservationRepository(database)
    assert restarted.get_latest_competition_assessment_snapshot(bound_identity()).assessment.competition_level.value == "medium"
    restarted.close()


def test_conflicts_validation_and_bounded_failure():
    opportunities, observations, client = setup()
    try:
        wrong = body(); wrong["identity"]["market"] = "OTHER"
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=wrong).status_code == 409
        invalid = body(); invalid["evidence"]["price_spread"]["value"] = 20.0
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=invalid).status_code == 422
        naive = body(); naive["observed_at"] = "2026-01-01T00:00:00"
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=naive).status_code == 422
        observations._connection.execute("""CREATE TRIGGER fail_competition_receipt BEFORE INSERT ON
        competition_admission_receipts BEGIN SELECT RAISE(ABORT, 'private sqlite failure'); END""")
        failed = client.post("/api/v1/opportunities/opp-bound/competition-observations", json=body())
        assert failed.status_code == 503
        assert "private sqlite failure" not in failed.text
        assert observations.get_history("competition", bound_identity()) == ()
    finally:
        app.dependency_overrides.clear(); observations.close(); opportunities.close()


def test_changed_command_and_duplicate_provenance_conflict():
    opportunities, observations, client = setup()
    try:
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=body()).status_code == 201
        changed = body(); changed["evidence"]["competitor_count"]["value"] = 40
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=changed).status_code == 409
        duplicate = body("new-command")
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=duplicate).status_code == 409
    finally:
        app.dependency_overrides.clear(); observations.close(); opportunities.close()


def test_readiness_transition_and_ui_contract():
    opportunities, observations, client = setup()
    reviews = SimpleNamespace(list_opportunity_bindings=lambda opportunity_id:
        (SimpleNamespace(market_observation_identity=bound_identity()),))
    readiness = DecisionReadinessService(opportunities, observations, reviews)
    try:
        assert readiness.execute("opp-bound")["sources"]["competition_assessment"]["status"] == "missing"
        assert client.post("/api/v1/opportunities/opp-bound/competition-observations", json=body()).status_code == 201
        result = readiness.execute("opp-bound")
        assert result["sources"]["competition_assessment"]["status"] == "ready"
        assert result["sources"]["production_safety"]["status"] == "missing"
        source = TestClient(app).get("/opportunities/opp-bound").text
        assert "Competition Observation" in source
        assert "assessment results cannot be selected" in source
        assert "competition-observations" in source
        assert "innerHTML" not in source
    finally:
        app.dependency_overrides.clear(); observations.close(); opportunities.close()
