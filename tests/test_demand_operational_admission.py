from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.application.demand_observation_admission import FinalizeDemandObservationAdmission
from app.application.decision_readiness import DecisionReadinessService
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_demand_admission_service
from test_opportunity_market_identity_binding import command, identity as bound_identity, service


def body(command_id="demand-command-1"):
    identity=bound_identity(); identity_data={name:(getattr(identity,name).value if name=="scope" else getattr(identity,name).isoformat() if name.startswith("window_") else getattr(identity,name)) for name in ("scope","market","marketplace","canonical_product_id","marketplace_item_id","normalized_query","category","variant_identity","condition","window_started_at","window_ended_at")}; observed=identity.window_ended_at.isoformat()
    evidence={}
    for name,value,unit in (("search_volume",2001,"count"),("review_count",201,"count"),("rating","4.60","stars"),("coupang_popularity_rank",3,"rank"),("itemscout_popularity_rank",7,"rank")):
        evidence[name]={"value":value,"source":"authoritative-demand-capture","reference":f"capture:{name}","observed_at":observed,"status":"observed","confidence":"0.80","collection_method":"operator_capture","unit":unit}
    return {"command_id":command_id,"operator_id":"operator-1","submitted_at":observed,"observation_id":"demand-observation-1","identity":identity_data,"observed_at":observed,"evidence":evidence}


def setup(database=":memory:"):
    opportunities=SQLiteValidationQueueRepository(database);observations=SQLiteMarketObservationRepository(database);service(opportunities).add(command(bound_identity()));app.dependency_overrides[get_demand_admission_service]=lambda:FinalizeDemandObservationAdmission(opportunities,observations);return opportunities,observations,TestClient(app)


def test_exact_round_trip_analysis_replay_and_restart(tmp_path:Path):
    database=tmp_path/"demand.db";opportunities,observations,client=setup(database)
    try:
        first=client.post("/api/v1/opportunities/opp-bound/demand-observations",json=body());replay=client.post("/api/v1/opportunities/opp-bound/demand-observations",json=body())
        assert first.status_code==201 and replay.status_code==200 and replay.json()==first.json()
        assert first.json()["assessment"]["demand_level"]=="high" and first.json()["assessment"]["confidence"]=="0.80"
        assert first.json()["observation"]["evidence"]["rating"]["value"]=="4.60"
    finally: app.dependency_overrides.clear();observations.close();opportunities.close()
    restarted=SQLiteMarketObservationRepository(database);assert restarted.get_latest_demand_assessment_snapshot(bound_identity()).assessment.demand_level.value=="high";restarted.close()


def test_identity_validation_rollback_and_bounded_errors():
    opportunities,observations,client=setup()
    try:
        wrong=body();wrong["identity"]["market"]="OTHER";assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=wrong).status_code==409
        invalid=body();invalid["evidence"]["rating"]["value"]=4.6;assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=invalid).status_code==422
        naive=body();naive["observed_at"]="2026-01-01T00:00:00";assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=naive).status_code==422
        observations._connection.execute("""CREATE TRIGGER fail_demand_receipt BEFORE INSERT ON demand_admission_receipts BEGIN SELECT RAISE(ABORT,'private sqlite');END""")
        failed=client.post("/api/v1/opportunities/opp-bound/demand-observations",json=body());assert failed.status_code==503 and "private sqlite" not in failed.text
        assert observations.get_history("demand",bound_identity())==() and observations.get_latest("demand",bound_identity()) is None
    finally: app.dependency_overrides.clear();observations.close();opportunities.close()


def test_changed_command_duplicate_and_readiness_ui():
    opportunities,observations,client=setup();reviews=SimpleNamespace(list_opportunity_bindings=lambda opportunity_id:(SimpleNamespace(market_observation_identity=bound_identity()),));readiness=DecisionReadinessService(opportunities,observations,reviews)
    try:
        assert readiness.execute("opp-bound")["sources"]["demand_assessment"]["status"]=="missing"
        assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=body()).status_code==201
        changed=body();changed["evidence"]["search_volume"]["value"]=9999;assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=changed).status_code==409
        assert client.post("/api/v1/opportunities/opp-bound/demand-observations",json=body("another")).status_code==409
        assert readiness.execute("opp-bound")["sources"]["demand_assessment"]["status"]=="ready"
        source=TestClient(app).get("/opportunities/opp-bound").text;assert "Demand Observation" in source and "demand-observations" in source and "innerHTML" not in source
    finally: app.dependency_overrides.clear();observations.close();opportunities.close()
