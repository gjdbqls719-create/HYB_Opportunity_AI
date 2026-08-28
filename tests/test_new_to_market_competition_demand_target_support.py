from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.operational_opportunity_eligibility import (
    OperationalOpportunityBindingConflictError,
    get_operational_opportunity_eligibility,
)
from app.application.competition_observation_admission import (
    FinalizeCompetitionObservationAdmission,
)
from app.application.demand_observation_admission import (
    FinalizeDemandObservationAdmission,
)
from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    MarketEvidence,
    MarketEvidenceStatus,
    analyze_competition,
    analyze_demand,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.new_to_market_domestic_selling import (
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import (
    app,
    get_competition_admission_service,
    get_demand_admission_service,
)
from test_opportunity_market_identity_binding import identity as bound_identity
from test_new_to_market_domestic_selling_foundation import (
    REQUESTED_AT,
    _close,
    _command,
    _owner,
    _prepare_o1,
)


OBSERVED_AT = REQUESTED_AT + timedelta(minutes=10)


def _target_o2(tmp_path):
    path, resources, _ = _prepare_o1(tmp_path)
    repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(path)
    try:
        publication = _owner(repository)[0].execute(_command())
    finally:
        repository.close()
        _close(resources)
    return path, publication


def _evidence(value):
    return MarketEvidence(
        value=value,
        source="coupang-operator-capture",
        reference="evidence/kr/coupang-query.png",
        observed_at=OBSERVED_AT,
        status=MarketEvidenceStatus.OBSERVED,
        confidence=Decimal("0.90"),
        market="KR",
        marketplace="coupang",
        collection_method="operator_capture",
        schema_version="market-evidence-v1",
        keyword="car seat organizer",
        category="automotive accessories",
        marketplace_item_id="comparable-coupang-item-1",
        canonical_product_id=None,
        unit="count",
    )


def _api_evidence(value, unit="count", *, market="KR", marketplace="coupang"):
    return {
        "value": value,
        "source": "coupang-operator-capture",
        "reference": "evidence/kr/coupang-query.png",
        "observed_at": OBSERVED_AT.isoformat(),
        "status": "observed",
        "confidence": "0.90",
        "collection_method": "operator_capture",
        "market": market,
        "marketplace": marketplace,
        "keyword": "car seat organizer",
        "category": "automotive accessories",
        "marketplace_item_id": "comparable-coupang-item-1",
        "canonical_product_id": None,
        "unit": unit,
    }


def _target_body(kind, target_id, command_id=None):
    evidence = (
        {
            "competitor_count": _api_evidence(20),
            "rocket_seller_count": _api_evidence(4),
            "price_spread": _api_evidence("20.00", "KRW"),
            "median_price": _api_evidence("100.00", "KRW"),
        }
        if kind == "competition"
        else {
            "search_volume": _api_evidence(2001),
            "review_count": _api_evidence(201),
            "rating": _api_evidence("4.60", "stars"),
            "coupang_popularity_rank": _api_evidence(3, "rank"),
            "itemscout_popularity_rank": _api_evidence(7, "rank"),
        }
    )
    return {
        "contract_version": "2.0.0",
        "command_id": command_id or f"target-{kind}-command-1",
        "operator_id": "founder",
        "submitted_at": (OBSERVED_AT + timedelta(minutes=1)).isoformat(),
        "observation_id": f"target-{kind}-observation-1",
        "subject": {
            "kind": "new_to_market_domestic_selling_target",
            "domestic_selling_target_id": target_id,
        },
        "observed_at": OBSERVED_AT.isoformat(),
        "evidence": evidence,
    }


def _api_setup(path):
    opportunities = SQLiteValidationQueueRepository(path)
    observations = SQLiteMarketObservationRepository(path)
    app.dependency_overrides[get_competition_admission_service] = lambda: (
        FinalizeCompetitionObservationAdmission(opportunities, observations)
    )
    app.dependency_overrides[get_demand_admission_service] = lambda: (
        FinalizeDemandObservationAdmission(opportunities, observations)
    )
    return opportunities, observations, TestClient(app)


def test_operational_eligibility_resolves_target_binding_without_market_binding(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    try:
        eligibility = get_operational_opportunity_eligibility(
            repository, publication.lifecycle.opportunity_id
        )
        assert eligibility is not None
        assert eligibility.market_binding is None
        assert eligibility.target_binding == publication.target_binding
    finally:
        repository.close()


def test_operational_eligibility_missing_archived_dual_and_no_o1_fallback(tmp_path):
    path, publication = _target_o2(tmp_path)
    repository = SQLiteValidationQueueRepository(path)
    source_market_binding = repository.get_market_identity_binding("opportunity-v2-1")

    class Fake:
        def __init__(self, lifecycle, market=None, target=None):
            self.lifecycle, self.market, self.target = lifecycle, market, target

        def get(self, _):
            return self.lifecycle

        def get_market_identity_binding(self, _):
            return self.market

        def get_target_binding(self, _):
            return self.target

    try:
        source = get_operational_opportunity_eligibility(repository, "opportunity-v2-1")
        assert source is not None and source.target_binding is None
        assert source.market_binding == source_market_binding
        assert get_operational_opportunity_eligibility(repository, "missing") is None
        missing_binding = get_operational_opportunity_eligibility(
            Fake(publication.lifecycle), publication.lifecycle.opportunity_id
        )
        assert missing_binding is not None and missing_binding.subject is None
        archived = type("ArchivedLifecycle", (), {"is_archived": True})()
        assert get_operational_opportunity_eligibility(Fake(archived), "o2") is None
        with pytest.raises(OperationalOpportunityBindingConflictError):
            get_operational_opportunity_eligibility(
                Fake(publication.lifecycle, source_market_binding, publication.target_binding),
                publication.lifecycle.opportunity_id,
            )
    finally:
        repository.close()


def test_competition_and_demand_can_use_target_subject_with_coupang_provenance(tmp_path):
    _, publication = _target_o2(tmp_path)
    target = publication.target_binding.target_identity

    competition = CompetitionObservation(
        "target-competition-1",
        target,
        OBSERVED_AT,
        "competition-target-v1",
        {"competitor_count": _evidence(20)},
    )
    demand = DemandObservation(
        "target-demand-1",
        target,
        OBSERVED_AT,
        "demand-target-v1",
        {"search_volume": _evidence(2001)},
    )

    assert competition.identity == target
    assert demand.identity == target
    assert competition.evidence["competitor_count"].marketplace == "coupang"
    assert demand.evidence["search_volume"].marketplace == "coupang"
    assert target.domestic_selling_target_id != "comparable-coupang-item-1"


def test_openapi_exposes_distinct_target_subject_requests():
    document = TestClient(app).get("/openapi.json").json()
    schemas = document["components"]["schemas"]

    assert "TargetCompetitionObservationAdmissionRequest" in schemas
    assert "TargetDemandObservationAdmissionRequest" in schemas
    target = schemas["NewToMarketAssessmentSubjectRequest"]
    assert "marketplace_item_id" not in target.get("properties", {})
    assert "canonical_product_id" not in target.get("properties", {})


def test_default_app_composition_isolated_from_genuine_production_database():
    production = (
        Path(__file__).resolve().parents[1] / "data" / "hyb_opportunity.db"
    ).resolve()

    def state():
        sidecars = tuple(
            candidate.name
            for suffix in ("-wal", "-shm", "-journal")
            if (candidate := Path(f"{production}{suffix}")).exists()
        )
        if not production.exists():
            return None, None, None, sidecars

        item = production.stat()
        digest = hashlib.sha256(production.read_bytes()).hexdigest()
        return digest, item.st_size, item.st_mtime_ns, sidecars

    before = state()
    assert Path(web_module.DEFAULT_DATABASE_PATH).resolve() != production
    with pytest.raises(RuntimeError, match="genuine production SQLite"):
        sqlite3.connect(production)

    response = TestClient(app).post(
        "/api/v1/opportunities/missing/competition-observations",
        json=_target_body("competition", "isolated-target", "isolated-command"),
    )

    assert response.status_code == 404
    assert state() == before


@pytest.mark.parametrize(
    "kind,metric,bad_value",
    (
        ("competition", None, "not-a-decimal"),
        ("competition", "median_price", "not-a-decimal"),
        ("competition", "median_price", "NaN"),
        ("competition", "median_price", "Infinity"),
        ("demand", None, "not-a-decimal"),
        ("demand", "rating", "not-a-decimal"),
        ("demand", "rating", "NaN"),
        ("demand", "sales_proxy", "-Infinity"),
    ),
)
def test_target_decimal_input_invalidity_is_422(tmp_path, kind, metric, bad_value):
    path, publication = _target_o2(tmp_path)
    target = publication.target_binding.target_identity
    opportunities, observations, _ = _api_setup(path)
    client = TestClient(app, raise_server_exceptions=False)
    route = f"/api/v1/opportunities/{publication.lifecycle.opportunity_id}/{kind}-observations"
    body = _target_body(kind, target.domestic_selling_target_id)
    if metric is None:
        body["evidence"][next(iter(body["evidence"]))]["confidence"] = bad_value
    elif metric == "sales_proxy":
        body["evidence"] = {"sales_proxy": _api_evidence(bad_value, "units")}
    else:
        body["evidence"][metric]["value"] = bad_value
    try:
        response = client.post(route, json=body)
        assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.clear()
        observations.close()
        opportunities.close()


@pytest.mark.parametrize("kind", ("competition", "demand"))
def test_target_api_fresh_replay_conflict_market_safety_and_restart(tmp_path, kind):
    path, publication = _target_o2(tmp_path)
    target = publication.target_binding.target_identity
    opportunities, observations, client = _api_setup(path)
    route = f"/api/v1/opportunities/{publication.lifecycle.opportunity_id}/{kind}-observations"
    try:
        body = _target_body(kind, target.domestic_selling_target_id)
        first = client.post(route, json=body)
        replay = client.post(route, json=body)
        changed = json.loads(json.dumps(body))
        changed["evidence"][next(iter(changed["evidence"]))]["value"] = 999
        conflict = client.post(route, json=changed)
        mismatch = _target_body(kind, "different-target", f"{kind}-mismatch")
        wrong_target = client.post(route, json=mismatch)
        foreign = _target_body(kind, target.domestic_selling_target_id, f"{kind}-foreign")
        for item in foreign["evidence"].values():
            item["market"] = "US"
            item["marketplace"] = "ebay"
        foreign_result = client.post(route, json=foreign)
        wrong_opportunity = client.post(
            f"/api/v1/opportunities/missing/{kind}-observations",
            json=_target_body(kind, target.domestic_selling_target_id, f"{kind}-missing"),
        )

        assert first.status_code == 201, first.text
        assert replay.status_code == 200 and replay.json() == first.json()
        assert conflict.status_code == 409
        assert wrong_target.status_code == 409
        assert foreign_result.status_code == 422
        assert wrong_opportunity.status_code == 404
        result = first.json()["observation"]
        assert result["subject"]["domestic_selling_target_id"] == target.domestic_selling_target_id
        assert result["evidence"][next(iter(result["evidence"]))]["marketplace"] == "coupang"
        assert "marketplace_item_id" not in result["subject"]
    finally:
        app.dependency_overrides.clear()
        observations.close()
        opportunities.close()

    restarted = SQLiteMarketObservationRepository(path)
    try:
        snapshot = (
            restarted.get_latest_competition_assessment_snapshot(target)
            if kind == "competition"
            else restarted.get_latest_demand_assessment_snapshot(target)
        )
        assert snapshot is not None and snapshot.identity == target
        assert snapshot.schema_version == "market-assessment-target-v1"
    finally:
        restarted.close()


def test_target_persistence_is_append_only_and_mixed_variant_corruption_fails(tmp_path):
    path, publication = _target_o2(tmp_path)
    target = publication.target_binding.target_identity
    opportunities, observations, client = _api_setup(path)
    route = f"/api/v1/opportunities/{publication.lifecycle.opportunity_id}/competition-observations"
    try:
        response = client.post(
            route, json=_target_body("competition", target.domestic_selling_target_id)
        )
        assert response.status_code == 201
        with pytest.raises(sqlite3.IntegrityError):
            observations._connection.execute(
                "UPDATE market_observation_history SET observed_at=observed_at"
            )
        observations._connection.rollback()
        observations._connection.execute(
            "DROP TRIGGER trg_market_observation_history_no_update"
        )
        row = observations._connection.execute(
            "SELECT payload_json FROM market_observation_history WHERE observation_id=?",
            ("target-competition-observation-1",),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["identity"] = {
            "scope": "search_query", "market": "KR", "marketplace": "coupang",
            "canonical_product_id": None, "marketplace_item_id": None,
            "normalized_query": "car seat organizer", "category": None,
            "variant_identity": None, "condition": None,
            "window_started_at": OBSERVED_AT.isoformat(),
            "window_ended_at": OBSERVED_AT.isoformat(),
        }
        observations._connection.execute(
            "UPDATE market_observation_history SET payload_json=? WHERE observation_id=?",
            (json.dumps(payload), "target-competition-observation-1"),
        )
        observations._connection.commit()
        with pytest.raises(ValueError, match="variant is malformed"):
            observations.get_observation_by_id("target-competition-observation-1")
    finally:
        app.dependency_overrides.clear()
        observations.close()
        opportunities.close()


def test_target_subject_does_not_change_analyzer_results(tmp_path):
    _, publication = _target_o2(tmp_path)
    target = publication.target_binding.target_identity
    historical = bound_identity()
    competition_metrics = {
        "competitor_count": _evidence(20),
        "rocket_seller_count": _evidence(4),
        "price_spread": _evidence(Decimal("20.00")),
        "median_price": _evidence(Decimal("100.00")),
    }
    demand_metrics = {"search_volume": _evidence(2001)}
    historical_competition_evidence = {
        name: replace(item, market=historical.market, marketplace=historical.marketplace)
        for name, item in competition_metrics.items()
    }
    historical_demand_evidence = replace(
        _evidence(2001), market=historical.market, marketplace=historical.marketplace
    )
    target_competition = CompetitionObservation(
        "tc", target, OBSERVED_AT, "competition-target-v1", competition_metrics
    )
    market_competition = CompetitionObservation(
        "mc", historical, OBSERVED_AT, "competition-v1",
        historical_competition_evidence,
    )
    target_demand = DemandObservation(
        "td", target, OBSERVED_AT, "demand-target-v1", demand_metrics
    )
    market_demand = DemandObservation(
        "md", historical, OBSERVED_AT, "demand-v1",
        {"search_volume": historical_demand_evidence},
    )
    assert analyze_competition(target_competition, generated_at=OBSERVED_AT) == (
        analyze_competition(market_competition, generated_at=OBSERVED_AT)
    )
    assert analyze_demand(target_demand, generated_at=OBSERVED_AT) == (
        analyze_demand(market_demand, generated_at=OBSERVED_AT)
    )
