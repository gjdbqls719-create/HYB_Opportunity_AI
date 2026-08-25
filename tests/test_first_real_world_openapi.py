import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.web import app


def _schema():
    return TestClient(app).get("/openapi.json").json()["components"]["schemas"]


def _enum_values(schemas, property_schema):
    if "$ref" in property_schema:
        return schemas[property_schema["$ref"].split("/")[-1]]["enum"]
    return property_schema["enum"]


def test_actual_acquisition_openapi_exposes_canonical_categories_and_states():
    schemas = _schema()
    fixed = schemas["ActualAcquisitionFixedCostRequest"]["properties"]
    other = schemas["OtherMandatoryAcquisitionCostsRequest"]["properties"]
    assert _enum_values(schemas, fixed["category"]) == [
        "unit_purchase",
        "supplier_side_shipping",
        "international_freight",
        "domestic_inbound",
        "duty_customs",
    ]
    assert _enum_values(schemas, fixed["availability"]) == [
        "known", "not_applicable", "unknown"
    ]
    assert _enum_values(schemas, other["availability"]) == [
        "known", "not_applicable", "unknown"
    ]
    assert "UNKNOWN is unresolved and is never zero" in fixed["availability"]["description"]


def test_actual_sale_openapi_exposes_categories_availability_and_payout_states():
    schemas = _schema()
    fact = schemas["ActualSaleMonetaryFactRequest"]["properties"]
    payout = schemas["ActualSalePayoutRequest"]["properties"]
    assert len(_enum_values(schemas, fact["category"])) == 15
    assert _enum_values(schemas, fact["availability"]) == [
        "known", "not_applicable", "unknown"
    ]
    assert _enum_values(schemas, payout["reconciliation_state"]) == [
        "reconciled", "not_scope_comparable", "unresolved"
    ]
    assert "independent reconciliation fact" in payout["reconciliation_state"]["description"]
    finality = schemas["ActualSaleFinalityRequest"]["properties"]
    assert "factually final" in finality["confirmed"]["description"]
    assert "blocks COMPLETE" in finality["unresolved_reason"]["description"]


def test_high_risk_requests_forbid_extra_and_document_decimal_strings():
    schemas = _schema()
    for name in (
        "ActualAcquisitionSettlementRequest",
        "ActualSaleSettlementRequest",
        "RealMoneyExecutionIntentRequest",
        "PurchaseExecutionRequest",
    ):
        assert schemas[name]["additionalProperties"] is False
    assert schemas["ActualAcquisitionFixedCostRequest"]["properties"]["amount"]["anyOf"][0]["type"] == "string"
    assert schemas["ActualSaleMonetaryFactRequest"]["properties"]["amount"]["anyOf"][0]["type"] == "string"
    for name in (
        "ActualAcquisitionSettlementRequest",
        "ActualSaleSettlementRequest",
        "RealMoneyExecutionIntentRequest",
        "PurchaseExecutionRequest",
    ):
        assert "example" in schemas[name]
        assert set(schemas[name]["required"])


def test_runbook_uses_only_current_production_routes_and_v2_purchase_contract():
    runbook = (
        Path(__file__).parents[1]
        / "docs"
        / "05_OPERATIONS"
        / "FIRST_REAL_WORLD_VALIDATION_RUNBOOK.md"
    ).read_text(encoding="utf-8")
    openapi_paths = app.openapi()["paths"]
    documented_routes = re.findall(r"`(POST|GET) (/api/v[12]/[^`]+)`", runbook)
    assert documented_routes
    assert {path.split("/")[2] for _, path in documented_routes} == {"v1", "v2"}
    for method, documented_path in documented_routes:
        path = documented_path.replace("{o2}", "{opportunity_id}")
        assert path in openapi_paths
        assert method.lower() in openapi_paths[path]
    assert "contract_version=2.0.0" in runbook
    assert "actual_total_committed_amount" not in runbook
    assert "Do not inspect SQLite" in runbook
    assert "TO CONFIRM IN REAL COUPANG SELLER ACCOUNT" in runbook
