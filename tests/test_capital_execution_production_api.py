from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.clock import ProductionUTCClock
from app.infrastructure.capital_gate import (
    CapitalGatePersistenceError,
    SQLiteCapitalGateRepository,
)
from app.infrastructure.capital_requirement import (
    PlannedAcquisitionCapitalRequirementPersistenceError,
    SQLitePlannedAcquisitionCapitalRequirementRepository,
)
from app.infrastructure.founder_capital_approval import (
    FounderCapitalApprovalPersistenceError,
    SQLiteFounderCapitalApprovalRepository,
)
from app.infrastructure.real_money_execution_intent import (
    RealMoneyExecutionIntentPersistenceError,
    SQLiteRealMoneyExecutionIntentRepository,
)
from app.web import app
from test_capital_readiness_production_api import _ready_journey
from test_o2_economics_production_chain_api import economics_chain_client


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _execute_capital_journey(economics_chain_client, *, quantity=10):
    (
        client,
        database,
        opportunity_id,
        _,
        _,
        _,
        chain,
        _,
        _,
        readiness,
        _,
    ) = _ready_journey(economics_chain_client)
    sourcing = economics_chain_client[3]
    quote = sourcing["quote"]
    admission_id = sourcing["admission_id"]
    now = _now()
    intended_payload = {
        "command_id": "capital-intended-command-1",
        "sourcing_admission_id": admission_id,
        "sourcing_admission_revision": sourcing["revision"],
        "quote_id": quote["quote_id"],
        "quote_revision": quote["revision"],
        "quantity": quantity,
        "quantity_unit": "unit",
        "operator_id": "founder-1",
        "declared_at": now,
        "requested_at": now,
    }
    intended = client.post(
        f"/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
        json=intended_payload,
    )
    assert intended.status_code == 201, intended.text

    snapshot_a_payload = {
        "command_id": "capital-snapshot-a-command-1",
        "amount": "1000000000.0000",
        "currency": "KRW",
        "as_of": _now(),
        "operator_id": "founder-1",
        "requested_at": _now(),
    }
    snapshot_a = client.post(
        "/api/v1/deployable-capital-snapshots", json=snapshot_a_payload
    )
    assert snapshot_a.status_code == 201, snapshot_a.text

    requirement_payload = {
        "command_id": "capital-requirement-command-1",
        "intended_order_quantity_id": intended.json()["intent_id"],
        "acquisition_normalization_id": chain["normalization"].json()[
            "normalization_id"
        ],
        "scope_status": "complete",
        "operator_id": "founder-1",
        "verified_at": _now(),
        "requested_at": _now(),
    }
    requirement = client.post(
        f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
        json=requirement_payload,
    )
    assert requirement.status_code == 201, requirement.text
    assert requirement.json()["state"] == "calculable"

    gate_payload = {
        "command_id": "capital-gate-command-1",
        "capital_readiness_assessment_id": readiness.json()["assessment_id"],
        "capital_requirement_id": requirement.json()["requirement_id"],
        "deployable_capital_snapshot_id": snapshot_a.json()["snapshot_id"],
        "requested_at": _now(),
    }
    gate = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        json=gate_payload,
    )
    assert gate.status_code == 201, gate.text
    assert gate.json()["state"] == "pass"

    amount = requirement.json()["planned_acquisition_capital"]
    approved_at = _now()
    approval_payload = {
        "command_id": "capital-approval-command-1",
        "capital_gate_id": gate.json()["gate_id"],
        "founder_id": "founder-1",
        "approved_capital": amount,
        "currency": "KRW",
        "requested_at": approved_at,
        "approved_at": approved_at,
    }
    approval = client.post(
        f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
        json=approval_payload,
    )
    assert approval.status_code == 201, approval.text

    snapshot_b_payload = {
        "command_id": "capital-snapshot-b-command-1",
        "amount": amount,
        "currency": "KRW",
        "as_of": approval.json()["approved_at"],
        "operator_id": "founder-1",
        "requested_at": _now(),
    }
    snapshot_b = client.post(
        "/api/v1/deployable-capital-snapshots", json=snapshot_b_payload
    )
    assert snapshot_b.status_code == 201, snapshot_b.text
    assert snapshot_b.json()["snapshot_id"] != snapshot_a.json()["snapshot_id"]

    execution_payload = {
        "command_id": "capital-execution-command-1",
        "founder_capital_approval_id": approval.json()["approval_id"],
        "quote_id": quote["quote_id"],
        "quote_revision": quote["revision"],
        "current_deployable_capital_snapshot_id": snapshot_b.json()["snapshot_id"],
        "execution_quantity": quantity,
        "execution_quantity_unit": "unit",
        "planned_execution_amount": amount,
        "currency": "KRW",
        "founder_id": "founder-1",
        "current_execution_confirmed": True,
        "confirmed_at": _now(),
        "requested_at": _now(),
    }
    execution = client.post(
        f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
        json=execution_payload,
    )
    assert execution.status_code == 201, execution.text
    assert execution.json()["state"] == "ready_for_manual_execution"
    return {
        "client": client,
        "database": database,
        "opportunity_id": opportunity_id,
        "sourcing": sourcing,
        "readiness": readiness,
        "chain": chain,
        "intended": intended,
        "intended_payload": intended_payload,
        "snapshot_a": snapshot_a,
        "snapshot_a_payload": snapshot_a_payload,
        "requirement": requirement,
        "requirement_payload": requirement_payload,
        "gate": gate,
        "gate_payload": gate_payload,
        "approval": approval,
        "approval_payload": approval_payload,
        "snapshot_b": snapshot_b,
        "snapshot_b_payload": snapshot_b_payload,
        "execution": execution,
        "execution_payload": execution_payload,
    }


def test_production_utc_clock_is_timezone_aware_utc():
    value = ProductionUTCClock()()
    assert value.tzinfo is timezone.utc
    assert value.utcoffset() == timedelta(0)


def test_api_only_o2_reaches_ready_for_manual_execution(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    opportunity_id = result["opportunity_id"]
    sourcing = result["sourcing"]
    requirement = result["requirement"].json()
    approval = result["approval"].json()
    execution = result["execution"].json()

    assert execution["opportunity_id"] == opportunity_id
    assert execution["quote_id"] == sourcing["quote"]["quote_id"]
    assert execution["quote_revision"] == sourcing["quote"]["revision"]
    assert execution["sourcing_admission_id"] == sourcing["admission_id"]
    assert execution["execution_quantity"] == 10
    assert execution["planned_execution_amount"] == requirement[
        "planned_acquisition_capital"
    ]
    assert approval["approved_capital"] == execution["planned_execution_amount"]
    assert execution["founder_capital_approval_id"] == approval["approval_id"]
    assert sourcing["supplier"]["external_supplier_reference"]
    assert sourcing["sourcing_product"]["external_product_reference"]


def test_all_six_routes_replay_and_restart_without_duplicate_history(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    client = result["client"]
    opportunity_id = result["opportunity_id"]
    calls = (
        (
            f"/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
            result["intended_payload"],
            result["intended"],
        ),
        (
            "/api/v1/deployable-capital-snapshots",
            result["snapshot_a_payload"],
            result["snapshot_a"],
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
            result["requirement_payload"],
            result["requirement"],
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
            result["gate_payload"],
            result["gate"],
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
            result["approval_payload"],
            result["approval"],
        ),
        (
            "/api/v1/deployable-capital-snapshots",
            result["snapshot_b_payload"],
            result["snapshot_b"],
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
            result["execution_payload"],
            result["execution"],
        ),
    )
    for route, payload, first in calls:
        replay = client.post(route, json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json() == {**first.json(), "replayed": True}

    with TestClient(app) as restarted:
        for route, payload, first in calls:
            replay = restarted.post(route, json=payload)
            assert replay.status_code == 200, replay.text
            assert replay.json() == {**first.json(), "replayed": True}

    with sqlite3.connect(result["database"]) as connection:
        expected = {
            "capital_investment_intent_history": 1,
            "deployable_capital_snapshot_history": 2,
            "planned_acquisition_capital_requirement_history": 1,
            "capital_gate_history": 1,
            "founder_capital_approval_history": 1,
            "real_money_execution_intent_history": 1,
        }
        for table, count in expected.items():
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == count


def test_blocked_and_rejected_states_remain_successful_business_results(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    client, opportunity_id = result["client"], result["opportunity_id"]

    unresolved = deepcopy(result["requirement_payload"])
    unresolved.update(
        command_id="capital-requirement-unresolved",
        scope_status="unresolved",
    )
    blocked_requirement = client.post(
        f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
        json=unresolved,
    )
    assert blocked_requirement.status_code == 201
    assert blocked_requirement.json()["state"] == "blocked"

    insufficient_payload = deepcopy(result["snapshot_a_payload"])
    insufficient_payload.update(
        command_id="capital-snapshot-insufficient", amount="0"
    )
    insufficient = client.post(
        "/api/v1/deployable-capital-snapshots", json=insufficient_payload
    )
    assert insufficient.status_code == 201
    rejected_gate_payload = deepcopy(result["gate_payload"])
    rejected_gate_payload.update(
        command_id="capital-gate-insufficient",
        deployable_capital_snapshot_id=insufficient.json()["snapshot_id"],
    )
    rejected_gate = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        json=rejected_gate_payload,
    )
    assert rejected_gate.status_code == 201
    assert rejected_gate.json()["state"] == "rejected"
    assert "insufficient_deployable_capital" in rejected_gate.json()[
        "rejection_reasons"
    ]

    approval_payload = deepcopy(result["approval_payload"])
    approval_payload.update(
        command_id="approval-for-rejected-gate",
        capital_gate_id=rejected_gate.json()["gate_id"],
    )
    assert client.post(
        f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
        json=approval_payload,
    ).status_code == 409

    execution_payload = deepcopy(result["execution_payload"])
    execution_payload.update(
        command_id="execution-not-confirmed",
        current_execution_confirmed=False,
    )
    blocked_execution = client.post(
        f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
        json=execution_payload,
    )
    assert blocked_execution.status_code == 201
    assert blocked_execution.json()["state"] == "blocked"


def test_money_inputs_require_json_decimal_strings(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    numeric_snapshot = deepcopy(result["snapshot_a_payload"])
    numeric_snapshot.update(command_id="numeric-snapshot", amount=10.5)
    assert result["client"].post(
        "/api/v1/deployable-capital-snapshots", json=numeric_snapshot
    ).status_code == 422


def test_exact_source_and_o2_route_ownership(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    payload = deepcopy(result["intended_payload"])
    payload["command_id"] = "wrong-route-opportunity-command"
    assert result["client"].post(
        "/api/v1/opportunities/source-opportunity-1/intended-order-quantities",
        json=payload,
    ).status_code == 409
    payload.update(
        command_id="missing-admission-command",
        sourcing_admission_id="missing-admission",
    )
    assert result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/intended-order-quantities",
        json=payload,
    ).status_code == 404


def test_all_six_routes_reject_changed_same_command(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    opportunity_id = result["opportunity_id"]
    cases = (
        (
            f"/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
            result["intended_payload"],
            {"quantity": 11},
        ),
        (
            "/api/v1/deployable-capital-snapshots",
            result["snapshot_a_payload"],
            {"amount": "999999999"},
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
            result["requirement_payload"],
            {"scope_status": "unresolved"},
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
            result["gate_payload"],
            {
                "deployable_capital_snapshot_id": result["snapshot_b"].json()[
                    "snapshot_id"
                ]
            },
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
            result["approval_payload"],
            {"founder_id": "changed-founder"},
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
            result["execution_payload"],
            {"current_execution_confirmed": False},
        ),
    )
    for route, original, changes in cases:
        payload = deepcopy(original)
        payload.update(changes)
        assert result["client"].post(route, json=payload).status_code == 409


@pytest.mark.parametrize(
    "changes",
    (
        {"approved_capital": "1"},
        {"currency": "USD"},
    ),
)
def test_approval_rejects_amount_and_currency_mismatch(
    economics_chain_client, changes
):
    result = _execute_capital_journey(economics_chain_client)
    payload = deepcopy(result["approval_payload"])
    payload.update(command_id=f"mismatched-approval-{next(iter(changes))}", **changes)
    response = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/founder-capital-approvals",
        json=payload,
    )
    assert response.status_code == 409


def test_gate_api_rejects_below_moq_and_non_positive_economics_and_blocks_scope(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    client, opportunity_id = result["client"], result["opportunity_id"]

    small_intended_payload = deepcopy(result["intended_payload"])
    small_intended_payload.update(
        command_id="below-moq-intended-command", quantity=1
    )
    small_intended = client.post(
        f"/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
        json=small_intended_payload,
    )
    assert small_intended.status_code == 201
    small_requirement_payload = deepcopy(result["requirement_payload"])
    small_requirement_payload.update(
        command_id="below-moq-requirement-command",
        intended_order_quantity_id=small_intended.json()["intent_id"],
    )
    small_requirement = client.post(
        f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
        json=small_requirement_payload,
    )
    assert small_requirement.status_code == 201
    below_moq_gate_payload = deepcopy(result["gate_payload"])
    below_moq_gate_payload.update(
        command_id="below-moq-gate-command",
        capital_requirement_id=small_requirement.json()["requirement_id"],
    )
    below_moq_gate = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        json=below_moq_gate_payload,
    )
    assert below_moq_gate.status_code == 201
    assert below_moq_gate.json()["state"] == "rejected"
    assert "intended_quantity_below_moq" in below_moq_gate.json()[
        "rejection_reasons"
    ]

    unresolved_payload = deepcopy(result["requirement_payload"])
    unresolved_payload.update(
        command_id="blocked-scope-requirement-command", scope_status="unresolved"
    )
    unresolved = client.post(
        f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
        json=unresolved_payload,
    )
    blocked_gate_payload = deepcopy(result["gate_payload"])
    blocked_gate_payload.update(
        command_id="blocked-scope-gate-command",
        capital_requirement_id=unresolved.json()["requirement_id"],
    )
    blocked_gate = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        json=blocked_gate_payload,
    )
    assert blocked_gate.status_code == 201
    assert blocked_gate.json()["state"] == "blocked"
    assert "capital_requirement_blocked" in blocked_gate.json()["blocking_reasons"]

    readiness_manifest = result["readiness"].json()["source_manifest"]
    conservative_payload = {
        "command_id": "non-positive-conservative-command",
        "source_composition_id": result["chain"]["source"].json()["composition_id"],
        "scenario": {
            "scenario_name": "founder-explicit-unit-scenario",
            "scenario_version": "1.0.0",
            "sale_price_factor": "0.01",
            "assumption_owner": "founder",
        },
        "requested_at": _now(),
    }
    conservative = client.post(
        f"/api/v1/opportunities/{opportunity_id}/conservative-economics",
        json=conservative_payload,
    )
    assert conservative.status_code == 201, conservative.text
    assert conservative.json()["status"] == "calculable"
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json={
            "command_id": "non-positive-readiness-command",
            "conservative_economics_result_id": conservative.json()["result_id"],
            "domestic_market_validation_assessment_id": readiness_manifest[
                "domestic_market_validation_assessment_id"
            ],
            "critical_cost_assessment_id": readiness_manifest[
                "critical_cost_assessment_id"
            ],
            "requested_at": _now(),
        },
    )
    assert readiness.status_code == 201, readiness.text
    non_positive_gate_payload = deepcopy(result["gate_payload"])
    non_positive_gate_payload.update(
        command_id="non-positive-gate-command",
        capital_readiness_assessment_id=readiness.json()["assessment_id"],
    )
    non_positive_gate = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        json=non_positive_gate_payload,
    )
    assert non_positive_gate.status_code == 201, non_positive_gate.text
    assert non_positive_gate.json()["state"] == "rejected"
    assert any(
        reason.startswith("conservative_")
        for reason in non_positive_gate.json()["rejection_reasons"]
    )


def test_execution_api_blocks_each_current_safety_mismatch(
    economics_chain_client, monkeypatch
):
    result = _execute_capital_journey(economics_chain_client)
    client, opportunity_id = result["client"], result["opportunity_id"]
    route = f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents"

    insufficient_payload = deepcopy(result["snapshot_b_payload"])
    insufficient_payload.update(
        command_id="execution-insufficient-snapshot-command", amount="0"
    )
    insufficient = client.post(
        "/api/v1/deployable-capital-snapshots", json=insufficient_payload
    )
    assert insufficient.status_code == 201

    cases = (
        {"planned_execution_amount": "1"},
        {"execution_quantity": 11},
        {
            "current_deployable_capital_snapshot_id": insufficient.json()[
                "snapshot_id"
            ]
        },
        {
            "current_deployable_capital_snapshot_id": result["snapshot_a"].json()[
                "snapshot_id"
            ]
        },
        {"founder_id": "different-founder"},
        {"current_execution_confirmed": False},
        {"quote_id": "different-quote"},
    )
    for index, changes in enumerate(cases):
        payload = deepcopy(result["execution_payload"])
        payload.update(command_id=f"blocked-execution-command-{index}", **changes)
        response = client.post(route, json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["state"] == "blocked"
        assert response.json()["blocking_reasons"]

    expires = datetime.fromisoformat(
        result["sourcing"]["quote"]["valid_until"]
    ) + timedelta(days=1)
    monkeypatch.setattr(web_module, "ProductionUTCClock", lambda: lambda: expires)
    expired_payload = deepcopy(result["execution_payload"])
    expired_payload.update(
        command_id="expired-quote-execution-command",
        confirmed_at=expires.isoformat(),
    )
    expired = client.post(route, json=expired_payload)
    assert expired.status_code == 201, expired.text
    assert expired.json()["state"] == "blocked"
    assert "quote_expired" in expired.json()["blocking_reasons"]


def test_ready_alias_and_competing_ready_action_cardinality(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    client, opportunity_id = result["client"], result["opportunity_id"]
    route = f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents"

    alias_payload = deepcopy(result["execution_payload"])
    alias_payload.update(command_id="equivalent-ready-alias-command", requested_at=_now())
    alias = client.post(route, json=alias_payload)
    assert alias.status_code == 200, alias.text
    assert alias.json()["intent_id"] == result["execution"].json()["intent_id"]
    assert alias.json()["replayed"] is True

    second_snapshot_payload = deepcopy(result["snapshot_b_payload"])
    second_snapshot_payload["command_id"] = "competing-ready-snapshot-command"
    second_snapshot = client.post(
        "/api/v1/deployable-capital-snapshots", json=second_snapshot_payload
    )
    competing_payload = deepcopy(result["execution_payload"])
    competing_payload.update(
        command_id="competing-ready-action-command",
        current_deployable_capital_snapshot_id=second_snapshot.json()["snapshot_id"],
    )
    competing = client.post(route, json=competing_payload)
    assert competing.status_code == 409


def test_http_same_command_concurrency_converges_for_all_six_authorities(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    opportunity_id = result["opportunity_id"]

    def concurrent(route, payload):
        def execute(_):
            return TestClient(app).post(route, json=payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = tuple(pool.map(execute, range(2)))
        assert sorted(value.status_code for value in responses) == [200, 201]
        assert responses[0].json()[next(
            key
            for key in (
                "intent_id", "snapshot_id", "requirement_id", "gate_id", "approval_id"
            )
            if key in responses[0].json()
        )] == responses[1].json()[next(
            key
            for key in (
                "intent_id", "snapshot_id", "requirement_id", "gate_id", "approval_id"
            )
            if key in responses[1].json()
        )]
        return responses[0].json()

    intended_payload = deepcopy(result["intended_payload"])
    intended_payload["command_id"] = "concurrent-intended-command"
    intended = concurrent(
        f"/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
        intended_payload,
    )
    snapshot_payload = deepcopy(result["snapshot_a_payload"])
    snapshot_payload["command_id"] = "concurrent-gate-snapshot-command"
    snapshot = concurrent("/api/v1/deployable-capital-snapshots", snapshot_payload)
    requirement_payload = deepcopy(result["requirement_payload"])
    requirement_payload.update(
        command_id="concurrent-requirement-command",
        intended_order_quantity_id=intended["intent_id"],
    )
    requirement = concurrent(
        f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
        requirement_payload,
    )
    gate_payload = deepcopy(result["gate_payload"])
    gate_payload.update(
        command_id="concurrent-gate-command",
        capital_requirement_id=requirement["requirement_id"],
        deployable_capital_snapshot_id=snapshot["snapshot_id"],
    )
    gate = concurrent(
        f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
        gate_payload,
    )
    approval_payload = deepcopy(result["approval_payload"])
    approval_payload.update(
        command_id="concurrent-approval-command",
        capital_gate_id=gate["gate_id"],
        approved_capital=requirement["planned_acquisition_capital"],
    )
    approval = concurrent(
        f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
        approval_payload,
    )
    current_payload = deepcopy(result["snapshot_b_payload"])
    current_payload.update(
        command_id="concurrent-current-snapshot-command",
        amount=requirement["planned_acquisition_capital"],
        as_of=approval["approved_at"],
    )
    current = TestClient(app).post(
        "/api/v1/deployable-capital-snapshots", json=current_payload
    )
    assert current.status_code == 201
    execution_payload = deepcopy(result["execution_payload"])
    execution_payload.update(
        command_id="concurrent-execution-command",
        founder_capital_approval_id=approval["approval_id"],
        current_deployable_capital_snapshot_id=current.json()["snapshot_id"],
        planned_execution_amount=requirement["planned_acquisition_capital"],
    )
    concurrent(
        f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
        execution_payload,
    )


def test_all_capital_dependencies_own_one_connection_and_close(tmp_path, monkeypatch):
    database = tmp_path / "capital-execution-cleanup.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    factories = (
        web_module.get_intended_order_quantity_entry,
        web_module.get_deployable_capital_entry,
        web_module.get_planned_capital_requirement_entry,
        web_module.get_capital_gate_entry,
        web_module.get_founder_capital_approval_entry,
        web_module.get_real_money_execution_intent_entry,
    )
    for factory in factories:
        dependency = factory()
        entry = next(dependency)
        repository = entry._repository
        for child_name in (
            "_sourcing",
            "_investment",
            "_requirements",
            "_gates",
            "_approvals",
        ):
            child = getattr(repository, child_name, None)
            if child is not None:
                assert child._connection is repository._connection
        dependency.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


@pytest.mark.parametrize(
    ("factory_name", "repository_name", "identity_name"),
    (
        (
            "get_intended_order_quantity_entry",
            "SQLiteCapitalInvestmentFactsRepository",
            "ProductionIntendedOrderQuantityIdentityGenerator",
        ),
        (
            "get_deployable_capital_entry",
            "SQLiteCapitalInvestmentFactsRepository",
            "ProductionDeployableCapitalSnapshotIdentityGenerator",
        ),
        (
            "get_planned_capital_requirement_entry",
            "SQLitePlannedAcquisitionCapitalRequirementRepository",
            "ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator",
        ),
        (
            "get_capital_gate_entry",
            "SQLiteCapitalGateRepository",
            "ProductionCapitalGateIdentityGenerator",
        ),
        (
            "get_founder_capital_approval_entry",
            "SQLiteFounderCapitalApprovalRepository",
            "ProductionFounderCapitalApprovalIdentityGenerator",
        ),
        (
            "get_real_money_execution_intent_entry",
            "SQLiteRealMoneyExecutionIntentRepository",
            "ProductionRealMoneyExecutionIntentIdentityGenerator",
        ),
    ),
)
def test_partial_capital_composition_failure_closes_connection(
    tmp_path, monkeypatch, factory_name, repository_name, identity_name
):
    database = tmp_path / f"partial-{factory_name}.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    captured = []
    real_repository = getattr(web_module, repository_name)

    class CapturingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(web_module, repository_name, CapturingRepository)
    monkeypatch.setattr(
        web_module,
        identity_name,
        lambda: (_ for _ in ()).throw(RuntimeError("broken Capital composition")),
    )
    with pytest.raises(RuntimeError, match="broken Capital composition"):
        next(getattr(web_module, factory_name)())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_required_persistence_failures_are_503_atomic_closed_and_retryable(
    economics_chain_client, monkeypatch
):
    result = _execute_capital_journey(economics_chain_client)
    client, database, opportunity_id = (
        result["client"],
        result["database"],
        result["opportunity_id"],
    )
    tables = (
        "planned_acquisition_capital_requirement_history",
        "capital_gate_history",
        "founder_capital_approval_history",
        "real_money_execution_intent_history",
        "real_money_execution_intent_receipts",
    )

    def counts():
        with sqlite3.connect(database) as connection:
            return tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            )

    cases = (
        (
            "SQLitePlannedAcquisitionCapitalRequirementRepository",
            SQLitePlannedAcquisitionCapitalRequirementRepository,
            "save_requirement",
            PlannedAcquisitionCapitalRequirementPersistenceError,
            f"/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
            {**result["requirement_payload"], "command_id": "failed-requirement-command"},
            201,
        ),
        (
            "SQLiteCapitalGateRepository",
            SQLiteCapitalGateRepository,
            "save_gate",
            CapitalGatePersistenceError,
            f"/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
            {**result["gate_payload"], "command_id": "failed-gate-command"},
            201,
        ),
        (
            "SQLiteFounderCapitalApprovalRepository",
            SQLiteFounderCapitalApprovalRepository,
            "save_approval",
            FounderCapitalApprovalPersistenceError,
            f"/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
            {**result["approval_payload"], "command_id": "failed-approval-command"},
            201,
        ),
        (
            "SQLiteRealMoneyExecutionIntentRepository",
            SQLiteRealMoneyExecutionIntentRepository,
            "save_alias",
            RealMoneyExecutionIntentPersistenceError,
            f"/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
            {**result["execution_payload"], "command_id": "failed-execution-command"},
            200,
        ),
    )
    for (
        repository_name,
        real_repository,
        failing_method,
        error_type,
        route,
        payload,
        retry_status,
    ) in cases:
        captured = []

        class FailingRepository(real_repository):
            def __init__(self, value):
                super().__init__(value)
                captured.append(self)

        def fail(*_args, **_kwargs):
            raise error_type("private Capital sqlite detail")

        setattr(FailingRepository, failing_method, fail)
        before = counts()
        monkeypatch.setattr(web_module, repository_name, FailingRepository)
        failed = client.post(route, json=payload)
        assert failed.status_code == 503, failed.text
        assert "private Capital" not in failed.text
        assert counts() == before
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            captured[0]._connection.execute("SELECT 1")

        monkeypatch.setattr(web_module, repository_name, real_repository)
        retry = client.post(route, json=payload)
        assert retry.status_code == retry_status, retry.text
