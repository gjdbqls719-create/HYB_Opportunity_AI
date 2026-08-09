from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.web import app
from test_actual_sale_settlement_production_api import _sale_payload, _setup
from test_o2_economics_production_chain_api import economics_chain_client


def _inventory_route(result):
    return f"/api/v1/opportunities/{result['opportunity_id']}/owned-inventory"


def _advance_window(payload, *, command_id, report, transactions, microseconds=1):
    result = deepcopy(payload)
    start = datetime.fromisoformat(payload["period_end"])
    end = start + timedelta(microseconds=microseconds)
    requested = max(
        datetime.now(timezone.utc),
        end,
    )
    result.update(
        command_id=command_id,
        predecessor_settlement_id=None,
        external_report_reference=report,
        transaction_references=transactions,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        requested_at=requested.isoformat(),
    )
    result["finality"]["observed_at"] = result["requested_at"]
    return result


def test_receipt_complete_blocked_complete_and_zero_sale_api_journey(
    economics_chain_client,
):
    result = _setup(economics_chain_client, quantity=10)
    route = _inventory_route(result)

    receipt_only = result["client"].get(route)
    assert receipt_only.status_code == 200, receipt_only.text
    initial = receipt_only.json()["positions"][0]
    assert (initial["total_sellable_received"], initial["total_outbound_quantity"], initial["sellable_on_hand"]) == (10, 0, 10)
    assert initial["policy_version"] == "2.0.0"

    first_payload = _sale_payload(result, fulfilled_outbound_quantity=4)
    first = result["client"].post(result["sale_route"], json=first_payload)
    assert first.status_code == 201 and first.json()["state"] == "complete"
    after_first = result["client"].get(route).json()["positions"][0]
    assert (after_first["total_outbound_quantity"], after_first["sellable_on_hand"]) == (4, 6)
    assert after_first["contributing_actual_sale_settlement_ids"] == [
        first.json()["settlement_id"]
    ]

    blocked_payload = _advance_window(
        first_payload,
        command_id="blocked-sale-command",
        report="blocked-report",
        transactions=["blocked-order"],
    )
    blocked_payload["fulfilled_outbound_quantity"] = 3
    blocked_payload["fixed_monetary_facts"][5] = {
        "category": "marketplace_fee",
        "availability": "unknown",
        "unresolved_reason": "marketplace statement pending",
    }
    blocked = result["client"].post(result["sale_route"], json=blocked_payload)
    assert blocked.status_code == 201 and blocked.json()["state"] == "blocked", blocked.text
    after_blocked = result["client"].get(route).json()["positions"][0]
    assert (after_blocked["total_outbound_quantity"], after_blocked["sellable_on_hand"]) == (4, 6)
    assert blocked.json()["settlement_id"] not in after_blocked[
        "contributing_actual_sale_settlement_ids"
    ]

    complete_payload = deepcopy(blocked_payload)
    complete_payload.update(
        command_id="complete-sale-command",
        predecessor_settlement_id=blocked.json()["settlement_id"],
        fulfilled_outbound_quantity=2,
    )
    complete_payload["fixed_monetary_facts"][5] = deepcopy(
        first_payload["fixed_monetary_facts"][5]
    )
    complete = result["client"].post(result["sale_route"], json=complete_payload)
    assert complete.status_code == 201 and complete.json()["state"] == "complete"
    after_complete = result["client"].get(route).json()["positions"][0]
    assert (after_complete["total_outbound_quantity"], after_complete["sellable_on_hand"]) == (6, 4)
    assert after_complete["outbound_source_event_count"] == 2

    zero_payload = _advance_window(
        complete_payload,
        command_id="zero-sale-command",
        report="zero-sale-report",
        transactions=[],
    )
    zero_payload["fulfilled_outbound_quantity"] = 0
    zero = result["client"].post(result["sale_route"], json=zero_payload)
    assert zero.status_code == 201 and zero.json()["state"] == "complete"
    final = result["client"].get(route)
    assert final.status_code == 200
    position = final.json()["positions"][0]
    assert (position["total_outbound_quantity"], position["sellable_on_hand"]) == (6, 4)
    assert position["outbound_source_event_count"] == 3
    assert zero.json()["settlement_id"] in position[
        "contributing_actual_sale_settlement_ids"
    ]
    assert all(isinstance(position[name], int) for name in (
        "total_received", "total_sellable_received", "total_damaged_received",
        "total_outbound_quantity", "sellable_on_hand",
        "inbound_source_event_count", "outbound_source_event_count",
    ))

    with TestClient(app) as restarted:
        rebuilt = restarted.get(route)
    assert rebuilt.status_code == 200
    assert rebuilt.json() == final.json()
