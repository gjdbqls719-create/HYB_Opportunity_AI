from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.operational_opportunity_eligibility import (
    get_operational_opportunity_eligibility,
)
from app.domain.opportunity import OpportunityLifecycle
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app
from test_competition_operational_admission import body as competition_payload
from test_demand_operational_admission import body as demand_payload
from test_domestic_selling_opportunity_api import domestic_payload
from test_domestic_selling_opportunity_sqlite import seed
from test_verified_economics_operational_admission import payload as economics_payload


@pytest.fixture
def o2_client(tmp_path, monkeypatch):
    database = tmp_path / "o2-operational-ingress.db"
    seed(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        domestic = client.post(
            "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
            json=domestic_payload(),
        )
        assert domestic.status_code == 201
        yield client, database, domestic.json()
    app.dependency_overrides.clear()


def _market_request(payload, market_identity):
    result = deepcopy(payload)
    result["identity"] = market_identity
    return result


def _o2_details(client):
    domestic = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    )
    assert domestic.status_code == 201
    result = domestic.json()
    return (
        result["domestic_opportunity_identity"]["opportunity_id"],
        result["market_binding"]["market_observation_identity"],
    )


def _ingress_request(ingress, opportunity_id, market_identity):
    if ingress == "competition":
        return (
            f"/api/v1/opportunities/{opportunity_id}/competition-observations",
            _market_request(competition_payload(), market_identity),
        )
    if ingress == "demand":
        return (
            f"/api/v1/opportunities/{opportunity_id}/demand-observations",
            _market_request(demand_payload(), market_identity),
        )
    return (
        f"/api/v1/opportunities/{opportunity_id}/verified-economics",
        economics_payload(),
    )


@pytest.mark.parametrize("ingress", ("competition", "demand", "economics"))
def test_o2_operational_ingress_does_not_require_validation_queue_membership(
    o2_client,
    ingress,
):
    client, database, domestic = o2_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    market_identity = domestic["market_binding"]["market_observation_identity"]

    route, payload = _ingress_request(ingress, opportunity_id, market_identity)

    response = client.post(route, json=payload)

    assert response.status_code == 201
    with web_module.sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM validation_queue_admission_snapshots "
            "WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()[0] == 0


@pytest.mark.parametrize("ingress", ("competition", "demand", "economics"))
def test_o2_ingress_preserves_replay_restart_and_changed_command_conflict(
    o2_client,
    ingress,
):
    client, database, domestic = o2_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    market_identity = domestic["market_binding"]["market_observation_identity"]
    route, payload = _ingress_request(ingress, opportunity_id, market_identity)

    first = client.post(route, json=payload)
    replay = client.post(route, json=payload)
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == first.json()

    changed = deepcopy(payload)
    if ingress == "competition":
        changed["evidence"]["competitor_count"]["value"] = 99
    elif ingress == "demand":
        changed["evidence"]["search_volume"]["value"] = 9999
    else:
        changed["purchase_cost"]["amount"] = "999.00"
    assert client.post(route, json=changed).status_code == 409

    with TestClient(app) as restarted:
        restarted_replay = restarted.post(route, json=payload)
    assert restarted_replay.status_code == 200
    assert restarted_replay.json() == first.json()

    with web_module.sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM validation_queue_admission_snapshots "
            "WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()[0] == 0
        receipt_table = {
            "competition": "competition_admission_receipts",
            "demand": "demand_admission_receipts",
            "economics": "verified_economics_admission_receipts",
        }[ingress]
        assert connection.execute(f"SELECT COUNT(*) FROM {receipt_table}").fetchone()[0] == 1


@pytest.mark.parametrize("ingress", ("competition", "demand"))
def test_o2_market_scoped_ingress_requires_exact_kr_binding(o2_client, ingress):
    client, _, domestic = o2_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    market_identity = domestic["market_binding"]["market_observation_identity"]
    route, payload = _ingress_request(ingress, opportunity_id, market_identity)
    payload["identity"]["market"] = "US"
    payload["identity"]["marketplace"] = "ebay"

    assert client.post(route, json=payload).status_code == 409


@pytest.mark.parametrize("ingress", ("competition", "demand", "economics"))
def test_missing_exact_opportunity_remains_404(o2_client, ingress):
    client, _, domestic = o2_client
    market_identity = domestic["market_binding"]["market_observation_identity"]
    route, payload = _ingress_request(ingress, "missing-o2", market_identity)

    assert client.post(route, json=payload).status_code == 404


@pytest.mark.parametrize("ingress", ("competition", "demand", "economics"))
def test_lifecycle_without_market_binding_is_not_operationally_eligible(
    o2_client,
    ingress,
):
    client, database, domestic = o2_client
    lifecycle = OpportunityLifecycle(
        "domestic-opportunity-without-binding",
        "domestic-selling-admission:missing-binding",
    )
    repository = SQLiteValidationQueueRepository(database)
    try:
        repository.create(
            lifecycle,
            lifecycle.creation_transition(
                operator_id="system",
                reason="missing-binding-regression-fixture",
            ),
        )
    finally:
        repository.close()
    market_identity = domestic["market_binding"]["market_observation_identity"]
    route, payload = _ingress_request(ingress, lifecycle.opportunity_id, market_identity)

    assert client.post(route, json=payload).status_code == 409


def test_api_only_o2_market_and_verified_economics_continuation(o2_client):
    client, database, domestic = o2_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    market_identity = domestic["market_binding"]["market_observation_identity"]

    competition_route, competition = _ingress_request(
        "competition", opportunity_id, market_identity
    )
    demand_route, demand = _ingress_request("demand", opportunity_id, market_identity)
    economics_route, economics = _ingress_request(
        "economics", opportunity_id, market_identity
    )
    economics["expected_sale_price"]["amount"] = "155.00"

    competition_response = client.post(competition_route, json=competition)
    demand_response = client.post(demand_route, json=demand)
    economics_response = client.post(economics_route, json=economics)

    assert competition_response.status_code == 201
    assert demand_response.status_code == 201
    assert economics_response.status_code == 201
    assert competition_response.json()["observation"]["identity"] == market_identity
    assert economics_response.json()["opportunity_id"] == opportunity_id
    assert economics_response.json()["expected_sale_price"]["amount"] == "155.00"

    market = SQLiteMarketObservationRepository(database)
    try:
        persisted_demand = market.get_observation_by_id(
            demand_response.json()["observation"]["observation_id"]
        )
        assert persisted_demand.identity.market == "KR"
        assert persisted_demand.identity == market.get_observation_by_id(
            competition_response.json()["observation"]["observation_id"]
        ).identity
    finally:
        market.close()

    validation = SQLiteValidationQueueRepository(database)
    try:
        assert validation.get_queue_item(opportunity_id) is None
        assert validation.get_verified_economics_snapshot(opportunity_id).opportunity_id == opportunity_id
        assert validation.get_verified_economics_snapshot("source-opportunity-1") is None
    finally:
        validation.close()


def test_archived_lifecycle_remains_ineligible():
    repository = SimpleNamespace(
        get=lambda opportunity_id: SimpleNamespace(is_archived=True),
        get_market_identity_binding=lambda opportunity_id: pytest.fail(
            "archived Opportunity must not load a Market binding"
        ),
    )

    assert get_operational_opportunity_eligibility(repository, "archived") is None
