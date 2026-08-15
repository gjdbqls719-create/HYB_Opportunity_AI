from copy import deepcopy

from fastapi.testclient import TestClient

import app.web as web_module
from app.web import app
from test_new_to_market_competition_demand_target_support import _target_o2
from test_sourcing_authority_api import payload as sourcing_payload
from test_verified_economics_operational_admission import payload as economics_payload


def _target_sourcing_payload(admission_id: str, **changes):
    value = sourcing_payload()
    value["selling_product_lineage"] = {
        "kind": "new_to_market_domestic_selling_admission",
        "new_to_market_domestic_selling_admission_id": admission_id,
    }
    value.update(changes)
    return value


def test_target_sourcing_api_resolves_exact_adr_0060_admission(tmp_path, monkeypatch):
    path, publication = _target_o2(tmp_path)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/sourcing/admissions",
                json=_target_sourcing_payload(publication.admission.admission_id),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    lineage = response.json()["selling_product_lineage"]
    assert lineage == {
        "kind": "new_to_market_domestic_selling_admission",
        "new_to_market_domestic_selling_admission_id": (
            publication.admission.admission_id
        ),
        "opportunity_id": (
            publication.admission.domestic_opportunity_identity.opportunity_id
        ),
        "discovery_reference": (
            publication.admission.domestic_opportunity_identity.discovery_reference
        ),
        "target_identity": {
            "domestic_selling_target_id": (
                publication.admission.target_identity.domestic_selling_target_id
            ),
            "market": "KR",
            "kind": "new_to_market_domestic_selling_target",
            "schema_version": "new-to-market-domestic-selling-target-identity-v1",
        },
        "schema_version": "new-to-market-domestic-selling-product-lineage-v1",
    }
    assert response.json()["match_verification"]["status"] == "verified_match"
    assert response.json()["admission_schema_version"] == (
        "founder-sourcing-admission-v4"
    )


def test_target_bound_o2_admits_explicit_verified_economics_unchanged(
    tmp_path,
    monkeypatch,
):
    path, publication = _target_o2(tmp_path)
    opportunity_id = publication.admission.domestic_opportunity_identity.opportunity_id
    request = economics_payload("target-economics-command-1")
    request["expected_sale_price"] = deepcopy(request["expected_sale_price"])
    request["expected_sale_price"]["amount"] = "333.00"
    request["expected_sale_price"]["evidence"].update(
        {
            "status": "estimated",
            "source": "founder-target-price-review",
            "reference": "target-price-review:0065-1",
        }
    )

    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", path)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/opportunities/{opportunity_id}/verified-economics",
                json=request,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["opportunity_id"] == opportunity_id
    assert body["expected_sale_price"] == request["expected_sale_price"]
    assert "target_identity" not in body
    assert "market_observation_identity" not in body
