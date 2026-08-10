from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient

import app.web as web_module
from app.web import app
from test_actual_acquisition_settlement_production_api import _settlement_payload
from test_actual_outcome_production_api import _journey
from test_actual_sale_settlement_production_api import _sale_payload
from test_goods_receipt_production_api import _payload as goods_payload, _prepare
from test_o2_economics_production_chain_api import economics_chain_client


def _variance_journey(economics_chain_client, *, quantity=10, sale_changes=None, sale_mutator=None):
    result = _journey(
        economics_chain_client,
        quantity=quantity,
        sale_changes=sale_changes,
        sale_mutator=sale_mutator,
    )
    outcome = result["client"].post(result["outcome_route"], json=result["outcome_payload"])
    assert outcome.status_code == 201, outcome.text
    result["outcome"] = outcome.json()
    result["variance_route"] = (
        f"/api/v1/opportunities/{result['opportunity_id']}/economics-variances"
    )
    result["variance_payload"] = {
        "command_id": "variance-command-1",
        "conservative_economics_result_id": result["chain"]["conservative"].json()["result_id"],
        "actual_outcome_id": result["outcome"]["outcome_id"],
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def _legacy_counts(database):
    names = (
        "opportunity_actual_economics",
        "opportunity_actual_economics_events",
        "economics_variance_history",
    )
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in names
            if name in tables
        }


def test_api_fully_resolved_comparable_eligible_replay_restart_and_order(
    economics_chain_client,
):
    result = _variance_journey(
        economics_chain_client,
        quantity=10,
        sale_changes={"fulfilled_outbound_quantity": 10},
    )
    legacy_before = _legacy_counts(result["database"])
    first = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["comparison_state"] == "comparable"
    assert body["calibration_eligibility"] == "eligible"
    assert body["calibration_reasons"] == []
    assert [value["metric_name"] for value in body["core_metrics"]] == [
        "acquisition_cost_per_unit",
        "gross_sale_price_per_sold_unit",
        "marketplace_fee_per_sold_unit",
        "payment_fee_per_sold_unit",
        "fixed_fee_per_sold_unit",
        "profit",
        "margin",
        "acquisition_roi",
    ]
    assert [value["metric_name"] for value in body["acquisition_component_metrics"]] == [
        "acquisition_unit_purchase",
        "acquisition_supplier_side_shipping",
        "acquisition_international_freight",
        "acquisition_domestic_inbound",
    ]
    assert all(value["classification"] != "comparable" for value in body["actual_only_contributors"])
    assert body["hindsight_eligible"] is True
    payment = next(
        value
        for value in body["core_metrics"]
        if value["metric_name"] == "payment_fee_per_sold_unit"
    )
    assert payment["comparability"] == "comparable"
    assert payment["actual_value"] == "0"
    assert payment["reason_codes"] == ["actual_source_not_applicable"]
    profit = next(value for value in body["core_metrics"] if value["metric_name"] == "profit")
    assert profit["predicted_scope_total"] is not None
    assert profit["actual_scope_total"] is not None
    assert profit["scope_total_variance"] is not None
    assert body["exposure_context"]["remaining_sellable_quantity"] == 0
    assert body["actual_scope_context"]["sold_quantity"] == 10
    assert body["scenario_context"]["scenario_name"] == "founder-explicit-unit-scenario"
    assert body["predicted_only_context"]
    assert body["core_metrics"][0]["favorability"] in {"favorable", "unfavorable", "neutral"}
    assert profit["favorability"] in {"favorable", "unfavorable", "neutral"}

    replay = TestClient(app).post(result["variance_route"], json=result["variance_payload"])
    assert replay.status_code == 200, replay.text
    assert replay.json()["variance_id"] == body["variance_id"]
    assert replay.json()["replayed"] is True
    assert _legacy_counts(result["database"]) == legacy_before

    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM conservative_actual_variance_history"
        ).fetchone()[0] == 1


def test_api_partial_zero_sales_missing_conflicts_alias_and_strict_dto(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    first = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert first.status_code == 201, first.text
    assert first.json()["calibration_eligibility"] == "provisional"
    assert "remaining_inventory_exposure" in first.json()["calibration_reasons"]

    alias_payload = deepcopy(result["variance_payload"])
    alias_payload["command_id"] = "variance-command-alias"
    alias_payload["requested_at"] = (
        datetime.fromisoformat(alias_payload["requested_at"]) + timedelta(microseconds=1)
    ).isoformat()
    alias = result["client"].post(result["variance_route"], json=alias_payload)
    assert alias.status_code == 200
    assert alias.json()["aliased"] is True

    changed = deepcopy(result["variance_payload"])
    changed["requested_at"] = datetime.now(timezone.utc).isoformat()
    assert result["client"].post(result["variance_route"], json=changed).status_code == 409
    missing = deepcopy(result["variance_payload"])
    missing.update(command_id="missing-command", actual_outcome_id="missing")
    assert result["client"].post(result["variance_route"], json=missing).status_code == 404
    assert result["client"].post(
        "/api/v1/opportunities/wrong-o2/economics-variances",
        json=result["variance_payload"],
    ).status_code == 409
    assert result["client"].post(
        result["variance_route"], json={**result["variance_payload"], "variance": "forbidden"}
    ).status_code == 422


def test_api_zero_sales_preserves_acquisition_and_never_fakes_sale_values(
    economics_chain_client,
):
    def zero_gross(payload):
        for fact in payload["fixed_monetary_facts"]:
            if fact["category"] == "gross_completed_merchandise":
                fact["amount"] = "0"

    result = _variance_journey(
        economics_chain_client,
        sale_changes={"fulfilled_outbound_quantity": 0, "transaction_references": []},
        sale_mutator=zero_gross,
    )
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["comparison_state"] == "partially_comparable"
    assert body["calibration_eligibility"] == "provisional"
    assert {"zero_sales_scope", "core_metric_unavailable"} <= set(body["calibration_reasons"])
    assert body["core_metrics"][0]["comparability"] == "comparable"
    assert all(value["actual_value"] is None for value in body["core_metrics"][1:])
    assert all(value["variance"] is None for value in body["core_metrics"][1:])


def test_api_actual_only_cost_is_context_not_predicted_zero(
    economics_chain_client,
):
    def advertising_cost(payload):
        for fact in payload["fixed_monetary_facts"]:
            if fact["category"] == "advertising":
                fact["amount"] = "500"

    result = _variance_journey(economics_chain_client, sale_mutator=advertising_cost)
    response = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert response.status_code == 201, response.text
    body = response.json()
    contributor = next(
        value for value in body["actual_only_contributors"] if value["category"] == "advertising"
    )
    assert contributor["amount"] == "500"
    assert contributor["classification"] == "unmodeled_in_prediction"
    assert "actual_only_costs_present" in body["calibration_reasons"]
    profit = next(value for value in body["core_metrics"] if value["metric_name"] == "profit")
    assert profit["actual_scope_total"] == result["outcome"]["actual_realized_profit"]


def test_api_distinct_scenario_is_distinct_variance_and_actual_values_are_isolated(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    first = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert first.status_code == 201, first.text
    source_id = result["chain"]["source"].json()["composition_id"]
    second_conservative_payload = {
        "command_id": "conservative-command-second-scenario",
        "source_composition_id": source_id,
        "scenario": {
            "scenario_name": "founder-second-scenario",
            "scenario_version": "1.0.0",
            "sale_price_factor": "0.80",
            "assumption_owner": "founder",
        },
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    second_conservative = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/conservative-economics",
        json=second_conservative_payload,
    )
    assert second_conservative.status_code == 201, second_conservative.text
    second_payload = {
        **result["variance_payload"],
        "command_id": "variance-command-second-scenario",
        "conservative_economics_result_id": second_conservative.json()["result_id"],
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    second = result["client"].post(result["variance_route"], json=second_payload)
    assert second.status_code == 201, second.text
    assert second.json()["variance_id"] != first.json()["variance_id"]
    assert second.json()["scenario_context"]["scenario_name"] == "founder-second-scenario"
    assert [value["actual_value"] for value in second.json()["core_metrics"]] == [
        value["actual_value"] for value in first.json()["core_metrics"]
    ]


def test_api_damaged_inventory_makes_only_roi_scope_mismatch(economics_chain_client):
    result = _prepare(economics_chain_client, quantity=10)
    receipt = result["client"].post(
        result["receipt_route"],
        json=goods_payload(
            result["purchase"],
            received_quantity=10,
            sellable_quantity=9,
            damaged_quantity=1,
        ),
    )
    assert receipt.status_code == 201, receipt.text
    result["goods_receipt"] = receipt.json()
    result["sale_route"] = f"/api/v1/opportunities/{result['opportunity_id']}/actual-sale-settlements"
    acquisition = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/actual-acquisition-settlements",
        json=_settlement_payload(result["purchase"]),
    )
    assert acquisition.status_code == 201, acquisition.text
    sale = result["client"].post(result["sale_route"], json=_sale_payload(result))
    assert sale.status_code == 201, sale.text
    outcome = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/actual-outcomes",
        json={
            "command_id": "damaged-outcome-command",
            "actual_acquisition_settlement_id": acquisition.json()["settlement_id"],
            "actual_sale_settlement_ids": [sale.json()["settlement_id"]],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert outcome.status_code == 201, outcome.text
    variance = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/economics-variances",
        json={
            "command_id": "damaged-variance-command",
            "conservative_economics_result_id": result["chain"]["conservative"].json()["result_id"],
            "actual_outcome_id": outcome.json()["outcome_id"],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert variance.status_code == 201, variance.text
    body = variance.json()
    roi = next(value for value in body["core_metrics"] if value["metric_name"] == "acquisition_roi")
    assert roi["comparability"] == "scope_mismatch"
    assert roi["variance_percentage_points"] is None
    assert body["comparison_state"] == "partially_comparable"
    assert body["exposure_context"]["damaged_quantity"] == 1


def test_api_currency_and_source_policy_conflicts_are_409(
    economics_chain_client,
    monkeypatch,
):
    result = _variance_journey(economics_chain_client)
    real_repository = web_module.SQLiteConservativeActualVarianceRepository

    class MutatingRepository(real_repository):
        mutation = None

        def get_conservative_result(self, result_id):
            value = super().get_conservative_result(result_id)
            if value is not None:
                object.__setattr__(value, self.mutation[0], self.mutation[1])
            return value

    monkeypatch.setattr(web_module, "SQLiteConservativeActualVarianceRepository", MutatingRepository)
    MutatingRepository.mutation = ("economics_currency", "USD")
    currency = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert currency.status_code == 409
    MutatingRepository.mutation = ("policy_version", "unsupported")
    policy_payload = {**result["variance_payload"], "command_id": "unsupported-policy-command"}
    policy = result["client"].post(result["variance_route"], json=policy_payload)
    assert policy.status_code == 409
    monkeypatch.setattr(web_module, "SQLiteConservativeActualVarianceRepository", real_repository)


def test_api_one_conservative_against_later_outcome_creates_distinct_immutable_pair(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    first_variance = result["client"].post(
        result["variance_route"], json=result["variance_payload"]
    )
    assert first_variance.status_code == 201, first_variance.text
    first_body = first_variance.json()

    second_sale_payload = _sale_payload(result)
    first_end = datetime.fromisoformat(result["sale"]["period_end"])
    second_sale_payload.update(
        command_id="actual-sale-command-second-window",
        external_report_reference="coupang-report-2",
        transaction_references=["coupang-order-2"],
        period_start=(first_end + timedelta(microseconds=1)).isoformat(),
        period_end=(first_end + timedelta(microseconds=2)).isoformat(),
        requested_at=datetime.now(timezone.utc).isoformat(),
    )
    second_sale = result["client"].post(result["sale_route"], json=second_sale_payload)
    assert second_sale.status_code == 201, second_sale.text
    second_outcome = result["client"].post(
        result["outcome_route"],
        json={
            "command_id": "actual-outcome-command-second-window",
            "actual_acquisition_settlement_id": result["acquisition"]["settlement_id"],
            "actual_sale_settlement_ids": [
                result["sale"]["settlement_id"],
                second_sale.json()["settlement_id"],
            ],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert second_outcome.status_code == 201, second_outcome.text
    second_variance = result["client"].post(
        result["variance_route"],
        json={
            **result["variance_payload"],
            "command_id": "variance-command-second-window",
            "actual_outcome_id": second_outcome.json()["outcome_id"],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert second_variance.status_code == 201, second_variance.text
    assert second_variance.json()["variance_id"] != first_body["variance_id"]
    assert second_variance.json()["actual_outcome_id"] != first_body["actual_outcome_id"]
    replay_first = result["client"].post(
        result["variance_route"], json=result["variance_payload"]
    )
    assert replay_first.status_code == 200
    assert replay_first.json() == {**first_body, "replayed": True}
