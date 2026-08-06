from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.application.decision_readiness import DecisionReadinessService
from app.web import app, get_decision_readiness_service
from tests.test_decision_composition_finalization import finalizer, repositories, seed_required_sources
from tests.test_opportunity_market_identity_binding import command, identity, service


class Reviews:
    def __init__(self, market_identity): self.identity=market_identity
    def list_opportunity_bindings(self, opportunity_id):
        return (SimpleNamespace(
            opportunity_id=opportunity_id,
            discovery_reference="ebay:item-1",
            market_observation_identity=self.identity,
            schema_version="opportunity-review-binding-v1",
        ),)


def test_missing_sources_are_truthful_and_block_finalization():
    validation,market=repositories();service(validation).add(command(identity()))
    result=DecisionReadinessService(validation,market,Reviews(identity())).execute("opp-bound")
    assert result["sources"]["verified_economics"]["status"] == "missing"
    assert result["sources"]["production_safety"]["status"] == "missing"
    assert result["sources"]["competition_assessment"]["status"] == "missing"
    assert result["sources"]["demand_assessment"]["status"] == "missing"
    assert result["sources"]["external_signals"]["status"] == "optional"
    assert result["finalize_allowed"] is False
    assert len(result["blocking_reasons"]) == 4
    validation.close();market.close()


def test_all_authoritative_sources_allow_finalize_and_report_version():
    validation,market=repositories();market_identity=seed_required_sources(validation,market)
    readiness=DecisionReadinessService(validation,market,Reviews(market_identity))
    before=readiness.execute("opp-bound")
    assert before["finalize_allowed"] is True
    assert before["sources"]["composition"]["status"] == "not_finalized"
    finalizer(validation,market).execute("opp-bound",generated_at=market_identity.window_ended_at,schema_version="decision-input-v1",policy_version="decision-policy-v1")
    after=readiness.execute("opp-bound")
    assert after["sources"]["composition"]["status"] == "finalized"
    assert after["latest_composition_version"] == 1
    validation.close();market.close()


def test_unsupported_source_version_is_error():
    validation,market=repositories();market_identity=seed_required_sources(validation,market)
    original=validation.get_verified_economics_snapshot
    validation.get_verified_economics_snapshot=lambda opportunity_id:replace(original(opportunity_id),schema_version="unsupported")
    result=DecisionReadinessService(validation,market,Reviews(market_identity)).execute("opp-bound")
    assert result["sources"]["verified_economics"]["status"] == "error"
    assert result["finalize_allowed"] is False
    validation.close();market.close()


def test_readiness_endpoint_and_ui_contract():
    class Ready:
        def execute(self,opportunity_id): return {"opportunity_id":opportunity_id,"sources":{},"latest_composition_version":None,"finalize_allowed":False,"blocking_reasons":["missing"]}
    app.dependency_overrides[get_decision_readiness_service]=lambda:Ready()
    try: response=TestClient(app).get("/api/v1/opportunities/opp-1/decision-readiness")
    finally: app.dependency_overrides.clear()
    source=TestClient(app).get("/opportunities/opp-1").text
    assert response.status_code == 200
    assert "Decision Readiness" in source
    assert "Finalize Decision Composition" in source
    assert "finalize.addEventListener" in source
    assert "await loadReadiness()" in source
    assert "decision-dashboard" in source
    assert "innerHTML" not in source


def test_page_get_contains_no_automatic_finalization():
    source=TestClient(app).get("/opportunities/opp-1").text
    assert 'method:"POST"' in source
    assert 'finalize.addEventListener("click"' in source
    assert "load()})();" in source
