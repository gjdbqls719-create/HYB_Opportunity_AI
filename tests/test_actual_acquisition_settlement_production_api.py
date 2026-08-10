from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.actual_acquisition_settlement import (
    ActualAcquisitionSettlementHistoryError,
    SQLiteActualAcquisitionSettlementRepository,
)
from app.web import app
from test_capital_execution_production_api import _execute_capital_journey
from test_o2_economics_production_chain_api import economics_chain_client
from test_purchase_execution_production_api import _payload as purchase_payload


def _now():
    return datetime.now(timezone.utc).isoformat()


def _evidence(reference, operator="founder-1"):
    return {
        "reference": reference,
        "observed_at": _now(),
        "operator_id": operator,
        "collection_method": "founder_statement_review",
    }


def _known(category, amount="0", currency="KRW", *, fx=None):
    return {
        "category": category,
        "availability": "known",
        "amount": amount,
        "currency": currency,
        "settled_at": _now(),
        "evidence": _evidence(f"artifact://actual/{category}"),
        "unresolved_reason": None,
        "actual_fx": fx,
    }


def _na(category):
    return {
        "category": category,
        "availability": "not_applicable",
        "amount": None,
        "currency": None,
        "settled_at": None,
        "evidence": _evidence(f"artifact://actual/{category}/na"),
        "unresolved_reason": None,
        "actual_fx": None,
    }


def _unknown(category):
    return {
        "category": category,
        "availability": "unknown",
        "amount": None,
        "currency": None,
        "settled_at": None,
        "evidence": None,
        "unresolved_reason": "invoice pending",
        "actual_fx": None,
    }


def _fixed():
    return [
        _known("unit_purchase", "9000"),
        _known("supplier_side_shipping", "1000"),
        _na("international_freight"),
        _known("domestic_inbound", "0"),
        _na("duty_customs"),
    ]


def _settlement_payload(purchase, **changes):
    values = {
        "command_id": "actual-settlement-command-1",
        "purchase_execution_record_id": purchase["record_id"],
        "predecessor_settlement_id": None,
        "target_currency": "KRW",
        "fixed_cost_facts": _fixed(),
        "other_mandatory_costs": {
            "availability": "not_applicable",
            "items": [],
            "scope_evidence": _evidence("artifact://actual/other/none"),
            "unresolved_reason": None,
        },
        "operator_id": "founder-1",
        "requested_at": _now(),
    }
    values.update(changes)
    return values


def _prepare(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    response = result["client"].post(route, json=purchase_payload(result))
    assert response.status_code == 201, response.text
    result["purchase"] = response.json()
    result["settlement_route"] = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/actual-acquisition-settlements"
    )
    return result


def _isolated_side_effect_counts(database):
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        selected = sorted(
            name
            for name in tables
            if name in {"opportunity_actual_economics", "opportunity_actual_economics_events"}
            or "inventory" in name.lower()
        )
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in selected
        }


def test_api_complete_same_currency_restart_replay_and_isolation(economics_chain_client):
    result = _prepare(economics_chain_client)
    payload = _settlement_payload(result["purchase"])
    before = _isolated_side_effect_counts(result["database"])
    fresh = result["client"].post(result["settlement_route"], json=payload)
    assert fresh.status_code == 201, fresh.text
    body = fresh.json()
    assert body["state"] == "complete"
    assert body["revision"] == 1
    assert body["predecessor_settlement_id"] is None
    assert body["purchase_execution_record_id"] == result["purchase"]["record_id"]
    assert body["executed_quantity"] == result["purchase"]["actual_quantity"]
    assert body["executed_quantity_unit"] == result["purchase"]["actual_quantity_unit"]
    assert body["supplier_id"] == result["purchase"]["supplier_id"]
    assert body["quote_id"] == result["purchase"]["quote_id"]
    assert body["fixed_cost_facts"][0]["amount"] == "9000"
    assert body["fixed_cost_facts"][0]["amount"] != result["purchase"][
        "supplier_order_committed_amount"
    ]
    assert body["fixed_cost_facts"][3]["amount"] == "0"
    assert body["fixed_cost_facts"][2]["availability"] == "not_applicable"
    assert body["acquisition_batch_total"] == "10000"
    assert body["acquisition_per_unit"] is not None
    assert datetime.fromisoformat(body["admitted_at"]).utcoffset() is not None
    assert datetime.fromisoformat(body["committed_at"]).utcoffset() is not None
    assert _isolated_side_effect_counts(result["database"]) == before

    with sqlite3.connect(result["database"]) as connection:
        before_rows = connection.execute(
            "SELECT COUNT(*) FROM actual_acquisition_settlement_history"
        ).fetchone()[0]
    replay = TestClient(app).post(result["settlement_route"], json=payload)
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["settlement_id"] == body["settlement_id"]
    assert replay_body["admitted_at"] == body["admitted_at"]
    assert replay_body["committed_at"] == body["committed_at"]
    assert replay_body["replayed"] is True
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM actual_acquisition_settlement_history"
        ).fetchone()[0] == before_rows


def test_v2_supplier_commitment_remains_independent_from_final_settlement(
    economics_chain_client,
):
    result = _execute_capital_journey(
        economics_chain_client,
        execution_contract_version="2.0.0",
        supplier_order_amount="500",
    )
    execution = result["execution"].json()
    purchase = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/purchase-execution-records",
        json={
            "contract_version": "2.0.0",
            "command_id": "actual-chain-purchase-v2",
            "real_money_execution_intent_id": execution["intent_id"],
            "quote_id": execution["quote_id"],
            "quote_revision": execution["quote_revision"],
            "actual_quantity": execution["execution_quantity"],
            "actual_quantity_unit": execution["execution_quantity_unit"],
            "supplier_order_committed_amount": "500",
            "supplier_order_currency": execution["supplier_order_currency"],
            "external_order_reference": "actual-chain-order-v2",
            "founder_id": execution["founder_id"],
            "executed_at": execution["evaluated_at"],
            "evidence_references": [{
                "reference": "artifact://actual-chain/purchase-v2",
                "observed_at": execution["evaluated_at"],
            }],
            "requested_at": _now(),
        },
    )
    assert purchase.status_code == 201, purchase.text
    settlement = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/actual-acquisition-settlements",
        json=_settlement_payload(
            purchase.json(), command_id="actual-chain-settlement-v2"
        ),
    )
    assert settlement.status_code == 201, settlement.text
    assert settlement.json()["state"] == "complete"
    assert settlement.json()["acquisition_batch_total"] == "10000"
    assert settlement.json()["acquisition_batch_total"] != purchase.json()[
        "supplier_order_committed_amount"
    ]


def test_api_blocked_to_complete_revision_journey_and_terminal_conflict(economics_chain_client):
    result = _prepare(economics_chain_client)
    blocked_payload = _settlement_payload(result["purchase"])
    blocked_payload["fixed_cost_facts"][1] = _unknown("supplier_side_shipping")
    blocked = result["client"].post(result["settlement_route"], json=blocked_payload)
    assert blocked.status_code == 201, blocked.text
    blocked_body = blocked.json()
    assert blocked_body["state"] == "blocked"
    assert blocked_body["blocking_reasons"] == ["supplier_side_shipping_unknown"]
    assert blocked_body["acquisition_batch_total"] is None
    assert blocked_body["acquisition_per_unit"] is None

    complete_payload = _settlement_payload(
        result["purchase"],
        command_id="actual-settlement-command-2",
        predecessor_settlement_id=blocked_body["settlement_id"],
    )
    complete = result["client"].post(result["settlement_route"], json=complete_payload)
    assert complete.status_code == 201, complete.text
    complete_body = complete.json()
    assert complete_body["state"] == "complete"
    assert complete_body["revision"] == 2
    assert complete_body["predecessor_settlement_id"] == blocked_body["settlement_id"]

    post_payload = deepcopy(complete_payload)
    post_payload.update(
        command_id="actual-settlement-command-3",
        predecessor_settlement_id=complete_body["settlement_id"],
        requested_at=_now(),
    )
    post = result["client"].post(result["settlement_route"], json=post_payload)
    assert post.status_code == 409
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM actual_acquisition_settlement_history"
        ).fetchone()[0] == 2


def test_api_cross_currency_actual_fx_is_preserved_without_planned_fx(economics_chain_client):
    result = _prepare(economics_chain_client)
    with sqlite3.connect(result["database"]) as connection:
        planned_fx_before = connection.execute(
            "SELECT COUNT(*) FROM fx_observation_history"
        ).fetchone()[0]
    payload = _settlement_payload(result["purchase"])
    payload["fixed_cost_facts"][0] = _known(
        "unit_purchase",
        "10",
        "CNY",
        fx={
            "source_currency": "CNY",
            "target_currency": "KRW",
            "original_amount": "10",
            "target_amount": "1900",
            "applied_rate": "190",
            "provider": "card-provider",
            "payment_channel": "corporate-card",
            "external_reference": "charge-actual-1",
            "settled_at": _now(),
            "evidence": _evidence("artifact://card-charge/1"),
        },
    )
    response = result["client"].post(result["settlement_route"], json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "complete"
    fact = body["fixed_cost_facts"][0]
    assert fact["amount"] == "10"
    assert fact["currency"] == "CNY"
    assert fact["actual_fx"]["normalized_target_amount"] == "1900"
    assert fact["actual_fx"]["external_reference"] == "charge-actual-1"
    assert body["normalized_categories"][0]["target_batch_amount"] == "1900"
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fx_observation_history"
        ).fetchone()[0] == planned_fx_before


def test_api_blocked_missing_fx_missing_purchase_wrong_o2_and_validation(economics_chain_client):
    result = _prepare(economics_chain_client)
    payload = _settlement_payload(result["purchase"])
    payload["fixed_cost_facts"][0] = _known("unit_purchase", "10", "CNY")
    blocked = result["client"].post(result["settlement_route"], json=payload)
    assert blocked.status_code == 201
    assert blocked.json()["state"] == "blocked"
    assert blocked.json()["blocking_reasons"] == ["actual_fx_missing"]

    missing = _settlement_payload(
        result["purchase"],
        command_id="missing-purchase-command",
        purchase_execution_record_id="missing-purchase",
    )
    assert result["client"].post(result["settlement_route"], json=missing).status_code == 404

    wrong = _settlement_payload(
        result["purchase"], command_id="wrong-route-command"
    )
    wrong_response = result["client"].post(
        "/api/v1/opportunities/wrong-o2/actual-acquisition-settlements",
        json=wrong,
    )
    assert wrong_response.status_code == 409

    malformed = _settlement_payload(
        result["purchase"], command_id="malformed-command"
    )
    malformed["fixed_cost_facts"][0]["amount"] = 100
    assert result["client"].post(result["settlement_route"], json=malformed).status_code == 422

    changed = deepcopy(payload)
    changed["target_currency"] = "USD"
    assert result["client"].post(result["settlement_route"], json=changed).status_code == 409


def test_api_same_command_concurrency_creates_one_revision(economics_chain_client):
    result = _prepare(economics_chain_client)
    payload = _settlement_payload(result["purchase"])

    def execute(_):
        return TestClient(app).post(result["settlement_route"], json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, range(2)))
    assert sorted(value.status_code for value in responses) == [200, 201], [
        value.text for value in responses
    ]
    assert responses[0].json()["settlement_id"] == responses[1].json()["settlement_id"]
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM actual_acquisition_settlement_history"
        ).fetchone()[0] == 1


def test_api_persistence_failure_is_503_closed_and_retryable(
    economics_chain_client, monkeypatch
):
    result = _prepare(economics_chain_client)
    payload = _settlement_payload(result["purchase"])
    captured = []
    real_repository = SQLiteActualAcquisitionSettlementRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def save(self, *_args, **_kwargs):
            raise ActualAcquisitionSettlementHistoryError("private sqlite detail")

    monkeypatch.setattr(
        web_module, "SQLiteActualAcquisitionSettlementRepository", FailingRepository
    )
    failed = result["client"].post(result["settlement_route"], json=payload)
    assert failed.status_code == 503
    assert "private sqlite" not in failed.text
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM actual_acquisition_settlement_history"
        ).fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")

    monkeypatch.setattr(
        web_module, "SQLiteActualAcquisitionSettlementRepository", real_repository
    )
    retry = result["client"].post(result["settlement_route"], json=payload)
    assert retry.status_code == 201, retry.text


def test_dependency_owns_one_connection_and_closes(economics_chain_client):
    result = _prepare(economics_chain_client)
    dependency = web_module.get_actual_acquisition_settlement_entry()
    entry = next(dependency)
    repository = entry._owner._repository
    assert repository._purchase._connection is repository._connection
    assert repository._purchase._execution._connection is repository._connection
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")
