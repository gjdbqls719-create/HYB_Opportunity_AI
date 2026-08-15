from copy import deepcopy
from dataclasses import replace
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.capital_readiness import CapitalReadinessProductionEntry
from app.web import app
from test_adr_0066_capital_readiness_sqlite import seed_target_sources
from test_adr_0066_capital_readiness_target_admission import (
    _owner,
    _target_ready_sources,
)
from test_capital_readiness_production_api import _ready_journey
from test_o2_economics_production_chain_api import economics_chain_client
from test_sourcing_authority_contract import NOW


def _payload(conservative, critical, market, **changes):
    value = {
        "command_id": "capital-readiness-api-target-1",
        "conservative_economics_result_id": conservative.result_id,
        "domestic_market_validation_source": {
            "kind": "domestic_market_validation_v2",
            "assessment_id": market.assessment_id,
        },
        "critical_cost_assessment_id": "critical-cost-assessment-1",
        "requested_at": NOW.isoformat(),
    }
    value.update(changes)
    return value


def test_strict_target_request_returns_exact_v2_manifest_and_replays(
    tmp_path,
    monkeypatch,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    route = (
        f"/api/v1/opportunities/{opportunity.opportunity_id}/"
        "capital-readiness-assessments"
    )
    request = _payload(conservative, critical, market)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            response = client.post(route, json=request)
            replay = client.post(route, json=request)
            changed_kind = deepcopy(request)
            changed_kind["domestic_market_validation_source"]["kind"] = (
                "domestic_market_validation_v1"
            )
            conflict = client.post(route, json=changed_kind)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201, response.text
    assert replay.status_code == 200, replay.text
    assert conflict.status_code == 409, conflict.text
    body = response.json()
    assert replay.json() == {**body, "replayed": True}
    assert body["state"] == "ready_for_capital_review"
    assert body["assessment_schema_version"] == "capital-readiness-v3"
    manifest = body["source_manifest"]
    assert manifest["schema_version"] == "capital-readiness-source-manifest-v2"
    assert manifest["domestic_market_validation_source_kind"] == (
        "domestic_market_validation_v2"
    )
    assert manifest["domestic_market_validation_assessment_id"] == (
        market.assessment_id
    )
    assert manifest[
        "domestic_market_validation_source_manifest_fingerprint"
    ] == market.source_manifest_fingerprint
    assert manifest["critical_cost_normalization_id"] == (
        critical.acquisition_normalization_id
    )
    assert "target_identity" not in manifest
    assert "market_observation_identity" not in manifest


def test_discriminated_request_can_explicitly_select_existing_dmv_v1(
    economics_chain_client,
):
    (
        client,
        _,
        opportunity_id,
        _,
        market,
        _,
        chain,
        critical,
        _,
        _,
        _,
    ) = _ready_journey(economics_chain_client)
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json={
            "command_id": "capital-readiness-api-explicit-v1",
            "conservative_economics_result_id": chain["conservative"].json()[
                "result_id"
            ],
            "domestic_market_validation_source": {
                "kind": "domestic_market_validation_v1",
                "assessment_id": market.json()["assessment_id"],
            },
            "critical_cost_assessment_id": critical.json()["assessment_id"],
            "requested_at": NOW.isoformat(),
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "ready_for_capital_review"
    assert body["assessment_schema_version"] == "capital-readiness-v3"
    assert body["source_manifest"][
        "domestic_market_validation_source_kind"
    ] == "domestic_market_validation_v1"
    assert body["source_manifest"][
        "domestic_market_validation_source_manifest_fingerprint"
    ] is None


def test_openapi_preserves_v1_request_and_exposes_strict_command_v2() -> None:
    specification = app.openapi()
    schemas = specification["components"]["schemas"]
    historical = schemas["CapitalReadinessAssessmentRequest"]
    command_v2 = schemas["CapitalReadinessAssessmentRequestV2"]
    source = schemas["CapitalReadinessDomesticMarketValidationSourceRequest"]

    assert set(historical["properties"]) == {
        "command_id",
        "conservative_economics_result_id",
        "domestic_market_validation_assessment_id",
        "critical_cost_assessment_id",
        "requested_at",
    }
    assert historical["additionalProperties"] is False
    assert set(command_v2["properties"]) == {
        "command_id",
        "conservative_economics_result_id",
        "domestic_market_validation_source",
        "critical_cost_assessment_id",
        "requested_at",
    }
    assert command_v2["additionalProperties"] is False
    assert source["properties"]["kind"]["enum"] == [
        "domestic_market_validation_v1",
        "domestic_market_validation_v2",
    ]
    assert source["additionalProperties"] is False


@pytest.mark.parametrize(
    ("blocked_kind", "expected_reason"),
    (
        ("dmv", "domestic_market_not_validated"),
        ("target", "sourcing_lineage_mismatch"),
    ),
)
def test_target_business_mismatches_are_successful_blocked_api_results(
    blocked_kind,
    expected_reason,
):
    repository, opportunity = _target_ready_sources(
        current_use=blocked_kind != "dmv"
    )
    if blocked_kind == "target":
        wrong_lineage = replace(
            repository.admission.selling_product_lineage,
            target_identity=replace(
                repository.admission.selling_product_lineage.target_identity,
                domestic_selling_target_id="different-target",
            ),
        )
        repository.base.admission = replace(
            repository.admission,
            selling_product_lineage=wrong_lineage,
            match_verification=replace(
                repository.admission.match_verification,
                selling_product_lineage=wrong_lineage,
            ),
        )
    entry = CapitalReadinessProductionEntry(repository, _owner(repository))
    app.dependency_overrides[web_module.get_capital_readiness_entry] = lambda: entry
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/opportunities/{opportunity.opportunity_id}/"
                "capital-readiness-assessments",
                json=_payload(
                    repository.conservative,
                    repository.critical,
                    repository.market_v2,
                    command_id=f"blocked-api-{blocked_kind}",
                    critical_cost_assessment_id="critical-assessment-1",
                ),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201, response.text
    assert response.json()["state"] == "blocked"
    assert expected_reason in response.json()["blocking_reasons"]


@pytest.mark.parametrize(
    ("change", "nested"),
    (
        ({"domestic_market_validation_assessment_id": "fake-v1"}, False),
        ({"discovery_reference": "caller-owned"}, False),
        ({"source_manifest": {}}, False),
        ({"state": "ready_for_capital_review"}, False),
        ({"reasons": []}, False),
        ({"profitability": "high"}, False),
        ({"buy": True}, False),
        ({"invest": True}, False),
        ({"capital_decision": "allocate"}, False),
        ({"target_identity": {"domestic_selling_target_id": "caller"}}, True),
        ({"source_manifest_fingerprint": "f" * 64}, True),
        ({"market_observation_identity": {"marketplace": "NAVER"}}, True),
    ),
)
def test_target_request_rejects_caller_owned_or_compatibility_fields(
    tmp_path,
    monkeypatch,
    change,
    nested,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    request = _payload(conservative, critical, market)
    if nested:
        request["domestic_market_validation_source"].update(change)
    else:
        request.update(change)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/opportunities/{opportunity.opportunity_id}/"
                "capital-readiness-assessments",
                json=request,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_target_request_rejects_unknown_kind_and_missing_exact_assessment(
    tmp_path,
    monkeypatch,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    route = (
        f"/api/v1/opportunities/{opportunity.opportunity_id}/"
        "capital-readiness-assessments"
    )
    unknown = _payload(conservative, critical, market)
    unknown["domestic_market_validation_source"]["kind"] = "future_dmv"
    omitted = _payload(
        conservative,
        critical,
        market,
        command_id="capital-readiness-api-target-omitted-kind",
    )
    omitted["domestic_market_validation_source"].pop("kind")
    missing = _payload(
        conservative,
        critical,
        market,
        command_id="capital-readiness-api-target-missing",
    )
    missing["domestic_market_validation_source"]["assessment_id"] = "missing"
    wrong_kind = _payload(
        conservative,
        critical,
        market,
        command_id="capital-readiness-api-target-wrong-kind",
    )
    wrong_kind["domestic_market_validation_source"]["kind"] = (
        "domestic_market_validation_v1"
    )
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            unknown_response = client.post(route, json=unknown)
            omitted_response = client.post(route, json=omitted)
            missing_response = client.post(route, json=missing)
            wrong_kind_response = client.post(route, json=wrong_kind)
    finally:
        app.dependency_overrides.clear()

    assert unknown_response.status_code == 422
    assert omitted_response.status_code == 422
    assert missing_response.status_code == 404
    assert wrong_kind_response.status_code == 404


def test_api_restart_replay_ignores_later_dmv_corruption_but_fresh_use_fails(
    tmp_path,
    monkeypatch,
):
    database, opportunity, conservative, critical, market = seed_target_sources(
        tmp_path
    )
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    route = (
        f"/api/v1/opportunities/{opportunity.opportunity_id}/"
        "capital-readiness-assessments"
    )
    request = _payload(conservative, critical, market)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            first = client.post(route, json=request)
        assert first.status_code == 201, first.text
        with sqlite3.connect(database) as connection:
            connection.execute(
                "DROP TRIGGER trg_domestic_market_validation_v2_history_no_update"
            )
            row = connection.execute(
                "SELECT payload_json FROM domestic_market_validation_v2_history "
                "WHERE assessment_id=?",
                (market.assessment_id,),
            ).fetchone()
            connection.execute(
                "UPDATE domestic_market_validation_v2_history SET payload_json=? "
                "WHERE assessment_id=?",
                (row[0] + " ", market.assessment_id),
            )
            connection.execute(
                "CREATE TRIGGER "
                "trg_domestic_market_validation_v2_history_no_update "
                "BEFORE UPDATE ON domestic_market_validation_v2_history "
                "BEGIN SELECT RAISE(ABORT, "
                "'domestic_market_validation_v2_history is append-only'); END"
            )
        with TestClient(app) as restarted:
            replay = restarted.post(route, json=request)
            fresh = deepcopy(request)
            fresh["command_id"] = "capital-readiness-api-target-fresh"
            unavailable = restarted.post(route, json=fresh)
    finally:
        app.dependency_overrides.clear()

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == (
        "capital readiness persistence unavailable"
    )
