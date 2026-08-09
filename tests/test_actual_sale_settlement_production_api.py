from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient

import app.web as web_module
from app.web import app
from test_goods_receipt_production_api import _payload as goods_payload
from test_goods_receipt_production_api import _prepare
from test_o2_economics_production_chain_api import economics_chain_client


CATEGORIES = (
    "gross_completed_merchandise", "buyer_shipping",
    "marketplace_funded_discount_support", "seller_funded_discount",
    "tax_collected", "marketplace_fee", "payment_fee", "fixed_fee",
    "refund", "cancellation_reversal", "return_related_fee",
    "advertising", "fulfillment", "storage", "sale_side_inbound_handling",
)


def _evidence(reference, observed_at):
    return {
        "reference": reference,
        "observed_at": observed_at,
        "operator_id": "founder-1",
        "collection_method": "manual_csv",
    }


def _setup(economics_chain_client, *, quantity=10):
    result = _prepare(economics_chain_client, quantity=quantity)
    receipt_response = result["client"].post(
        result["receipt_route"], json=goods_payload(result["purchase"])
    )
    assert receipt_response.status_code == 201, receipt_response.text
    result["goods_receipt"] = receipt_response.json()
    result["sale_route"] = f"/api/v1/opportunities/{result['opportunity_id']}/actual-sale-settlements"
    return result


def _sale_payload(result, **changes):
    inspected = datetime.fromisoformat(result["goods_receipt"]["inspected_at"])
    end = inspected + timedelta(microseconds=1)
    requested = max(datetime.now(timezone.utc), end + timedelta(microseconds=1))
    observed = requested.isoformat()
    facts = []
    for category in CATEGORIES:
        if category == "payment_fee":
            facts.append({
                "category": category,
                "availability": "not_applicable",
                "evidence": _evidence(f"na-{category}", observed),
            })
        else:
            amount = "40000" if category == "gross_completed_merchandise" else "0"
            facts.append({
                "category": category,
                "availability": "known",
                "amount": amount,
                "currency": "KRW",
                "occurred_at": observed,
                "evidence": _evidence(f"evidence-{category}", observed),
            })
    values = {
        "command_id": "actual-sale-command-1",
        "anchor_goods_receipt_id": result["goods_receipt"]["record_id"],
        "predecessor_settlement_id": None,
        "marketplace": "COUPANG",
        "seller_account_reference": "coupang-store-1",
        "marketplace_product_reference": "coupang-product-1",
        "marketplace_option_reference": "option-a",
        "marketplace_sku_reference": "sku-a",
        "external_report_reference": "coupang-report-1",
        "transaction_references": ["coupang-order-1"],
        "period_start": (inspected - timedelta(seconds=1)).isoformat(),
        "period_end": end.isoformat(),
        "fulfilled_outbound_quantity": min(4, result["goods_receipt"]["sellable_quantity"]),
        "cancelled_quantity": 0,
        "refunded_quantity": 0,
        "returned_quantity": 0,
        "quantity_unit": result["goods_receipt"]["quantity_unit"],
        "settlement_currency": "KRW",
        "fixed_monetary_facts": facts,
        "other_sale_side_costs": {
            "availability": "known",
            "items": [],
            "scope_evidence": _evidence("other-cost-scope", observed),
        },
        "payout": {
            "availability": "known",
            "amount": "40000",
            "currency": "KRW",
            "external_reference": "coupang-payout-1",
            "paid_at": observed,
            "evidence": _evidence("payout", observed),
            "reconciliation_state": "not_scope_comparable",
            "reconciliation_explanation": "account payout includes timing items",
            "reconciliation_evidence": _evidence("payout-reconciliation", observed),
        },
        "finality": {
            "confirmed": True,
            "observed_at": observed,
            "evidence": _evidence("finality", observed),
        },
        "operator_id": "founder-1",
        "requested_at": requested.isoformat(),
    }
    values.update(changes)
    return values


def _legacy_count(database):
    with sqlite3.connect(database) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunity_actual_economics'"
        ).fetchone()
        return 0 if exists is None else connection.execute(
            "SELECT COUNT(*) FROM opportunity_actual_economics"
        ).fetchone()[0]


def test_manual_coupang_complete_replay_decimal_strings_and_legacy_isolation(economics_chain_client):
    result = _setup(economics_chain_client)
    payload = _sale_payload(result)
    legacy_before = _legacy_count(result["database"])
    response = result["client"].post(result["sale_route"], json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "complete"
    assert body["marketplace"] == "COUPANG"
    assert body["fulfilled_outbound_quantity"] == 4
    assert body["fixed_monetary_facts"][0]["amount"] == "40000"
    assert body["fixed_monetary_facts"][6]["availability"] == "not_applicable"
    assert body["payout"]["amount"] == "40000"
    assert body["product_key"]["sku_reference"] == result["goods_receipt"]["sku_reference"]
    replay = result["client"].post(result["sale_route"], json=payload)
    assert replay.status_code == 200
    assert replay.json()["settlement_id"] == body["settlement_id"]
    assert replay.json()["replayed"] is True
    changed = deepcopy(payload)
    changed["fulfilled_outbound_quantity"] = 0
    assert result["client"].post(result["sale_route"], json=changed).status_code == 409
    assert _legacy_count(result["database"]) == legacy_before


def test_blocked_to_complete_and_post_complete_conflict(economics_chain_client):
    result = _setup(economics_chain_client)
    blocked = _sale_payload(result)
    blocked["fixed_monetary_facts"][5] = {
        "category": "marketplace_fee",
        "availability": "unknown",
        "unresolved_reason": "fee statement pending",
    }
    first = result["client"].post(result["sale_route"], json=blocked)
    assert first.status_code == 201 and first.json()["state"] == "blocked"
    complete = _sale_payload(
        result,
        command_id="actual-sale-command-2",
        predecessor_settlement_id=first.json()["settlement_id"],
    )
    second = result["client"].post(result["sale_route"], json=complete)
    assert second.status_code == 201 and second.json()["state"] == "complete"
    child = deepcopy(complete)
    child["command_id"] = "actual-sale-command-3"
    child["predecessor_settlement_id"] = second.json()["settlement_id"]
    assert result["client"].post(result["sale_route"], json=child).status_code == 409


def test_zero_sale_complete_oversell_missing_source_and_structural_422(economics_chain_client):
    result = _setup(economics_chain_client)
    zero = _sale_payload(result, fulfilled_outbound_quantity=0, transaction_references=[])
    response = result["client"].post(result["sale_route"], json=zero)
    assert response.status_code == 201 and response.json()["state"] == "complete"

    oversell = _sale_payload(result, fulfilled_outbound_quantity=result["goods_receipt"]["sellable_quantity"] + 1)
    first_end = datetime.fromisoformat(zero["period_end"])
    second_end = datetime.now(timezone.utc)
    assert second_end > first_end
    oversell.update({
        "command_id": "oversell",
        "external_report_reference": "coupang-report-2",
        "transaction_references": ["coupang-order-2"],
        "period_start": first_end.isoformat(),
        "period_end": second_end.isoformat(),
        "requested_at": second_end.isoformat(),
    })
    oversell["finality"]["observed_at"] = second_end.isoformat()
    oversell_response = result["client"].post(result["sale_route"], json=oversell)
    assert oversell_response.status_code == 409, oversell_response.text
    missing = _sale_payload(result, command_id="missing", anchor_goods_receipt_id="missing")
    assert result["client"].post(result["sale_route"], json=missing).status_code == 404
    malformed = _sale_payload(result, command_id="malformed")
    malformed["fixed_monetary_facts"][0]["amount"] = 1.25
    assert result["client"].post(result["sale_route"], json=malformed).status_code == 422


def test_restart_and_bounded_persistence_failure(economics_chain_client, monkeypatch):
    result = _setup(economics_chain_client)
    payload = _sale_payload(result)
    first = result["client"].post(result["sale_route"], json=payload)
    assert first.status_code == 201
    with TestClient(app) as restarted:
        replay = restarted.post(result["sale_route"], json=payload)
    assert replay.status_code == 200 and replay.json()["settlement_id"] == first.json()["settlement_id"]

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr(web_module, "SQLiteActualSaleSettlementRepository", unavailable)
    failed = result["client"].post(result["sale_route"], json={**payload, "command_id": "unavailable"})
    assert failed.status_code == 503
