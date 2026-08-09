from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.sourcing import (
    CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2,
    CriticalCostCompletenessReplayConflictError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
    EvaluateCriticalCostCompleteness,
    PersistCriticalCostCompleteness,
    PersistCriticalCostCompletenessCommand,
)
from app.domain.sourcing import CriticalCostCompletenessState, CriticalCostReasonCode
from app.infrastructure.sourcing import (
    MalformedCriticalCostCompletenessPersistenceError,
    SQLiteCriticalCostCompletenessRepository,
    SQLiteFXObservationRepository,
)
from app.web import app
from test_domestic_selling_opportunity_api import (
    domestic_payload,
    domestic_sourcing_payload,
)
from test_domestic_selling_opportunity_sqlite import seed
from test_verified_economics_operational_admission import payload as economics_payload


@pytest.fixture
def economics_chain_client(tmp_path, monkeypatch):
    database = tmp_path / "o2-economics-production-chain.db"
    seed(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        domestic = client.post(
            "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
            json=domestic_payload(),
        )
        assert domestic.status_code == 201
        domestic_body = domestic.json()
        opportunity_id = domestic_body["domestic_opportunity_identity"]["opportunity_id"]

        sourcing_request = domestic_sourcing_payload(domestic_body["admission_id"])
        sourcing_request["quote_valid_until"] = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).replace(microsecond=0).isoformat()
        sourcing_request["shipping_terms"] = [
            {
                "scope": "supplier_side",
                "cost": {
                    "availability": "known",
                    "amount": "20.50",
                    "currency": "CNY",
                },
            },
            {
                "scope": "international_freight",
                "cost": {
                    "availability": "known",
                    "amount": "100.00",
                    "currency": "CNY",
                },
            },
            {
                "scope": "domestic_inbound",
                "cost": {
                    "availability": "not_applicable",
                    "amount": None,
                    "currency": None,
                },
            },
        ]
        sourcing = client.post(
            "/api/v1/sourcing/admissions",
            json=sourcing_request,
        )
        assert sourcing.status_code == 201

        economics = economics_payload()
        for name in (
            "purchase_cost",
            "shipping_cost",
            "fixed_fee",
            "duty_cost",
            "other_cost",
            "expected_sale_price",
        ):
            economics[name]["currency"] = "KRW"
            economics[name]["evidence"]["status"] = "verified"
            economics[name]["evidence"]["source"] = "founder-verified"
            economics[name]["evidence"]["reference"] = f"verified:{name}"
        for name in ("marketplace_fee_rate", "payment_fee_rate", "tax_rate"):
            economics[name]["evidence"]["status"] = "verified"
            economics[name]["evidence"]["source"] = "founder-verified"
            economics[name]["evidence"]["reference"] = f"verified:{name}"
        economics["expected_sale_price"]["amount"] = "50000.00"
        economics["fixed_fee"]["amount"] = "1000.00"
        economics["tax_rate"]["rate"] = "0"
        economics["duty_cost"]["amount"] = "0"
        economics["other_cost"]["amount"] = "0"
        verified = client.post(
            f"/api/v1/opportunities/{opportunity_id}/verified-economics",
            json=economics,
        )
        assert verified.status_code == 201, verified.text
        yield client, database, opportunity_id, sourcing.json(), verified.json()
    app.dependency_overrides.clear()


def test_o2_sourcing_economics_binding_route_is_production_callable(
    economics_chain_client,
):
    client, _, opportunity_id, sourcing, _ = economics_chain_client
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings",
        json={
            "command_id": "binding-command-1",
            "admission_id": sourcing["admission_id"],
            "admission_revision": sourcing["revision"],
            "quote_id": sourcing["quote"]["quote_id"],
            "quote_revision": sourcing["quote"]["revision"],
            "requested_at": now,
        },
    )

    assert response.status_code == 201


def _chain_payloads(opportunity_id, sourcing, verified):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    evidence = {
        "kind": "manual_entry",
        "source_reference": "founder:shipping-allocation",
        "observed_at": (now - timedelta(minutes=1)).isoformat(),
        "artifact_reference": None,
    }
    return {
        "binding": {
            "command_id": "binding-command-1",
            "admission_id": sourcing["admission_id"],
            "admission_revision": sourcing["revision"],
            "quote_id": sourcing["quote"]["quote_id"],
            "quote_revision": sourcing["quote"]["revision"],
            "requested_at": now.isoformat(),
        },
        "landed": {
            "command_id": "landed-command-1",
            "binding_id": None,
            "requested_at": now.isoformat(),
        },
        "supplier_allocation": {
            "command_id": "supplier-allocation-command-1",
            "composition_id": None,
            "component_kind": "supplier_side_shipping",
            "effective_allocation_basis": "per_quoted_quantity",
            "operator_id": "founder-1",
            "verified_at": now.isoformat(),
            "evidence_reference": evidence,
            "requested_at": now.isoformat(),
        },
        "freight_allocation": {
            "command_id": "freight-allocation-command-1",
            "composition_id": None,
            "component_kind": "international_freight",
            "effective_allocation_basis": "per_quoted_quantity",
            "operator_id": "founder-1",
            "verified_at": now.isoformat(),
            "evidence_reference": evidence,
            "requested_at": now.isoformat(),
        },
        "fx": {
            "command_id": "fx-command-1",
            "base_currency": "CNY",
            "quote_currency": "KRW",
            "rate": "190.123400",
            "observed_at": (now - timedelta(minutes=1)).isoformat(),
            "provider": "founder-observed-provider",
            "source_reference": "fx:manual:1",
            "collection_method": "operator_capture",
        },
        "normalization": {
            "command_id": "normalization-command-1",
            "composition_id": None,
            "allocation_authority_ids": [],
            "fx_observation_ids": [],
            "target_currency": "KRW",
            "requested_at": now.isoformat(),
        },
        "source_composition": {
            "command_id": "source-composition-command-1",
            "acquisition_normalization_id": None,
            "verified_economics_snapshot_at": verified["snapshot_at"],
            "verified_economics_schema_version": verified["schema_version"],
            "requested_at": now.isoformat(),
        },
        "conservative": {
            "command_id": "conservative-command-1",
            "source_composition_id": None,
            "scenario": {
                "scenario_name": "founder-explicit-unit-scenario",
                "scenario_version": "1.0.0",
                "sale_price_factor": "0.90",
                "assumption_owner": "founder",
            },
            "requested_at": now.isoformat(),
        },
    }


def _execute_chain(client, opportunity_id, payloads):
    routes = {
        "binding": f"/api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings",
        "landed": f"/api/v1/opportunities/{opportunity_id}/landed-cost-compositions",
        "allocation": f"/api/v1/opportunities/{opportunity_id}/shipping-allocation-authorities",
        "fx": "/api/v1/fx-observations",
        "normalization": f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
        "source": f"/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
        "conservative": f"/api/v1/opportunities/{opportunity_id}/conservative-economics",
    }
    binding = client.post(routes["binding"], json=payloads["binding"])
    assert binding.status_code in {200, 201}
    payloads["landed"]["binding_id"] = binding.json()["binding_id"]
    landed = client.post(routes["landed"], json=payloads["landed"])
    assert landed.status_code in {200, 201}
    for key in ("supplier_allocation", "freight_allocation"):
        payloads[key]["composition_id"] = landed.json()["composition_id"]
    supplier = client.post(routes["allocation"], json=payloads["supplier_allocation"])
    freight = client.post(routes["allocation"], json=payloads["freight_allocation"])
    assert supplier.status_code in {200, 201}
    assert freight.status_code in {200, 201}
    fx = client.post(routes["fx"], json=payloads["fx"])
    assert fx.status_code in {200, 201}
    payloads["normalization"].update(
        composition_id=landed.json()["composition_id"],
        allocation_authority_ids=[
            supplier.json()["authority_id"],
            freight.json()["authority_id"],
        ],
        fx_observation_ids=[fx.json()["observation_id"]],
    )
    normalization = client.post(
        routes["normalization"], json=payloads["normalization"]
    )
    assert normalization.status_code in {200, 201}
    payloads["source_composition"]["acquisition_normalization_id"] = (
        normalization.json()["normalization_id"]
    )
    source = client.post(routes["source"], json=payloads["source_composition"])
    assert source.status_code in {200, 201}
    payloads["conservative"]["source_composition_id"] = source.json()[
        "composition_id"
    ]
    conservative = client.post(routes["conservative"], json=payloads["conservative"])
    assert conservative.status_code in {200, 201}
    return {
        "binding": binding,
        "landed": landed,
        "supplier": supplier,
        "freight": freight,
        "fx": fx,
        "normalization": normalization,
        "source": source,
        "conservative": conservative,
    }


def test_api_only_o2_sourcing_to_conservative_economics_happy_path(
    economics_chain_client,
):
    client, database, opportunity_id, sourcing, verified = economics_chain_client
    payloads = _chain_payloads(opportunity_id, sourcing, verified)

    results = _execute_chain(client, opportunity_id, payloads)

    assert all(
        response.json().get("opportunity_id", opportunity_id) == opportunity_id
        for response in results.values()
    )
    assert results["supplier"].json()["status"] == "resolved"
    assert results["freight"].json()["denominator"]["quantity"] == 100
    assert results["fx"].json()["rate"] == "190.123400"
    assert results["normalization"].json()["target_currency"] == "KRW"
    assert isinstance(
        results["normalization"].json()["total_per_unit_acquisition_cost"], str
    )
    assert results["source"].json()["state"] == "ready"
    assert results["conservative"].json()["status"] == "calculable"

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM validation_queue_admission_snapshots "
            "WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()[0] == 0


def test_supported_o2_normalized_path_exposes_legacy_critical_cost_gap(
    economics_chain_client,
):
    client, database, opportunity_id, sourcing, verified = economics_chain_client
    results = _execute_chain(
        client,
        opportunity_id,
        _chain_payloads(opportunity_id, sourcing, verified),
    )
    repository = SQLiteCriticalCostCompletenessRepository(database)
    try:
        assessment = EvaluateCriticalCostCompleteness(
            repository,
            repository,
            policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
            evaluated_clock=lambda: datetime.now(timezone.utc),
        ).execute(results["landed"].json()["composition_id"])
    finally:
        repository.close()

    assert tuple(reason.code for reason in assessment.blocking_reasons) == (
        CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN,
        CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN,
        CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING,
    )
    assert results["normalization"].json()["target_currency"] == "KRW"
    assert results["conservative"].json()["status"] == "calculable"


def test_supported_o2_normalized_path_persists_complete_v2_and_replays_after_restart(
    economics_chain_client,
):
    client, database, opportunity_id, sourcing, verified = economics_chain_client
    results = _execute_chain(
        client,
        opportunity_id,
        _chain_payloads(opportunity_id, sourcing, verified),
    )
    requested_at = datetime.now(timezone.utc).replace(microsecond=0)
    command = PersistCriticalCostCompletenessCommand(
        command_id="critical-cost-v2-command-1",
        composition_id=results["landed"].json()["composition_id"],
        verified_economics_opportunity_id=opportunity_id,
        verified_economics_snapshot_at=datetime.fromisoformat(verified["snapshot_at"]),
        verified_economics_schema_version=verified["schema_version"],
        policy_name=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.name,
        policy_version=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.version,
        requested_at=requested_at,
        acquisition_normalization_id=results["normalization"].json()["normalization_id"],
        schema_version=CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2,
    )

    repository = SQLiteCriticalCostCompletenessRepository(database)
    try:
        first = PersistCriticalCostCompleteness(
            repository,
            assessment_id_generator=lambda: "critical-cost-v2-assessment-1",
            evaluated_clock=lambda: requested_at,
            committed_clock=lambda: requested_at + timedelta(seconds=1),
            policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        ).execute(command)
    finally:
        repository.close()

    assert first.assessment.state is CriticalCostCompletenessState.COMPLETE
    assert first.assessment.opportunity_identity.opportunity_id == opportunity_id
    assert (
        first.assessment.acquisition_normalization_id
        == results["normalization"].json()["normalization_id"]
    )
    assert first.assessment.allocation_authority_ids == (
        results["supplier"].json()["authority_id"],
        results["freight"].json()["authority_id"],
    )
    assert first.assessment.fx_observation_ids == (
        results["fx"].json()["observation_id"],
    )

    restarted = SQLiteCriticalCostCompletenessRepository(database)
    try:
        replay = PersistCriticalCostCompleteness(
            restarted,
            assessment_id_generator=lambda: (_ for _ in ()).throw(
                AssertionError("identity called during replay")
            ),
            evaluated_clock=lambda: (_ for _ in ()).throw(
                AssertionError("evaluation clock called during replay")
            ),
            committed_clock=lambda: (_ for _ in ()).throw(
                AssertionError("commit clock called during replay")
            ),
            policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        ).execute(command)
        counts = tuple(
            restarted._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "critical_cost_completeness_history",
                "critical_cost_completeness_receipts",
            )
        )
        with pytest.raises(CriticalCostCompletenessReplayConflictError):
            PersistCriticalCostCompleteness(
                restarted,
                assessment_id_generator=lambda: "never",
                evaluated_clock=lambda: requested_at,
                committed_clock=lambda: requested_at,
                policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
            ).execute(
                replace(
                    command,
                    acquisition_normalization_id="changed-normalization",
                )
            )
    finally:
        restarted.close()

    assert replay.replayed is True
    assert replay.assessment == first.assessment
    assert replay.receipt == first.receipt
    assert counts == (1, 1)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DROP TRIGGER trg_critical_cost_completeness_history_no_update"
        )
        encoded = connection.execute(
            "SELECT payload_json FROM critical_cost_completeness_history "
            "WHERE assessment_id=?",
            (first.receipt.assessment_id,),
        ).fetchone()[0]
        payload = json.loads(encoded)
        payload["normalization_source"]["normalization_id"] = "corrupted"
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        connection.execute(
            "UPDATE critical_cost_completeness_history "
            "SET payload_json=?,integrity_fingerprint=? WHERE assessment_id=?",
            (
                encoded,
                hashlib.sha256(encoded.encode()).hexdigest(),
                first.receipt.assessment_id,
            ),
        )
    corrupted = SQLiteCriticalCostCompletenessRepository(database)
    try:
        with pytest.raises(MalformedCriticalCostCompletenessPersistenceError):
            corrupted.get_assessment(first.receipt.assessment_id)
    finally:
        corrupted.close()


def test_complete_chain_exact_replay_restart_and_changed_payload_conflicts(
    economics_chain_client,
):
    client, database, opportunity_id, sourcing, verified = economics_chain_client
    payloads = _chain_payloads(opportunity_id, sourcing, verified)
    first = _execute_chain(client, opportunity_id, payloads)
    replay = _execute_chain(client, opportunity_id, payloads)

    assert all(value.status_code == 201 for value in first.values())
    assert all(value.status_code == 200 for value in replay.values())
    for key in first:
        assert replay[key].json() == {**first[key].json(), "replayed": True}

    changed_cases = (
        (
            f"/api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings",
            "binding",
            "requested_at",
            "2027-01-01T00:00:00+00:00",
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/landed-cost-compositions",
            "landed",
            "requested_at",
            "2027-01-01T00:00:00+00:00",
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/shipping-allocation-authorities",
            "supplier_allocation",
            "operator_id",
            "changed-founder",
        ),
        ("/api/v1/fx-observations", "fx", "rate", "191.00"),
        (
            f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
            "normalization",
            "target_currency",
            "CNY",
        ),
        (
            f"/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
            "source_composition",
            "requested_at",
            "2027-01-01T00:00:00+00:00",
        ),
    )
    for route, key, field, changed_value in changed_cases:
        changed = deepcopy(payloads[key])
        changed[field] = changed_value
        assert client.post(route, json=changed).status_code == 409

    with TestClient(app) as restarted:
        restart = _execute_chain(restarted, opportunity_id, payloads)
    assert all(value.status_code == 200 for value in restart.values())
    for key in first:
        assert restart[key].json() == replay[key].json()

    expected = {
        "sourcing_economics_binding_history": 1,
        "landed_cost_composition_history": 1,
        "shipping_allocation_authority_history": 2,
        "fx_observation_history": 1,
        "acquisition_cost_normalization_history": 1,
        "economics_source_composition_history": 1,
        "conservative_economics_history": 1,
    }
    with sqlite3.connect(database) as connection:
        for table, count in expected.items():
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count


def test_unresolved_allocation_and_missing_fx_never_fall_back(
    economics_chain_client,
):
    client, _, opportunity_id, sourcing, verified = economics_chain_client
    payloads = _chain_payloads(opportunity_id, sourcing, verified)
    results = _execute_chain(client, opportunity_id, payloads)
    route = f"/api/v1/opportunities/{opportunity_id}/shipping-allocation-authorities"
    unresolved_request = deepcopy(payloads["supplier_allocation"])
    unresolved_request["command_id"] = "unresolved-allocation-command"
    unresolved_request["effective_allocation_basis"] = None
    unresolved_request["operator_id"] = None
    unresolved_request["verified_at"] = None
    unresolved_request["evidence_reference"] = None

    unresolved = client.post(route, json=unresolved_request)

    assert unresolved.status_code == 201
    assert unresolved.json()["status"] == "unresolved"
    assert unresolved.json()["unresolved_code"] == "unspecified_unresolved"

    normalization_route = (
        f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations"
    )
    unresolved_normalization = deepcopy(payloads["normalization"])
    unresolved_normalization.update(
        command_id="unresolved-normalization-command",
        allocation_authority_ids=[
            unresolved.json()["authority_id"],
            results["freight"].json()["authority_id"],
        ],
    )
    assert client.post(
        normalization_route, json=unresolved_normalization
    ).status_code == 409

    missing_fx = deepcopy(payloads["normalization"])
    missing_fx.update(command_id="missing-fx-normalization-command", fx_observation_ids=[])
    assert client.post(normalization_route, json=missing_fx).status_code == 409


def test_same_currency_normalization_uses_no_fake_fx_and_blocked_state_is_2xx(
    economics_chain_client,
):
    client, _, opportunity_id, sourcing, verified = economics_chain_client
    payloads = _chain_payloads(opportunity_id, sourcing, verified)
    results = _execute_chain(client, opportunity_id, payloads)
    normalization = deepcopy(payloads["normalization"])
    normalization.update(
        command_id="same-currency-normalization-command",
        target_currency="CNY",
        fx_observation_ids=[],
    )
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
        json=normalization,
    )
    assert response.status_code == 201
    assert response.json()["fx_observation_ids"] == []
    assert all(
        item["fx_direction"] == "none" for item in response.json()["components"]
    )

    source = deepcopy(payloads["source_composition"])
    source.update(
        command_id="blocked-source-composition-command",
        acquisition_normalization_id=response.json()["normalization_id"],
    )
    source_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
        json=source,
    )
    assert source_response.status_code == 201
    assert source_response.json()["state"] == "blocked"
    assert "currency_mismatch" in {
        value["code"] for value in source_response.json()["blocking_reasons"]
    }

    conservative = deepcopy(payloads["conservative"])
    conservative.update(
        command_id="blocked-conservative-command",
        source_composition_id=source_response.json()["composition_id"],
    )
    conservative_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/conservative-economics",
        json=conservative,
    )
    assert conservative_response.status_code == 201
    assert conservative_response.json()["status"] == "blocked"
    assert results["source"].json()["state"] == "ready"


def test_exact_o2_ownership_missing_sources_and_caller_owned_fields(
    economics_chain_client,
):
    client, _, opportunity_id, sourcing, verified = economics_chain_client
    payloads = _chain_payloads(opportunity_id, sourcing, verified)
    results = _execute_chain(client, opportunity_id, payloads)

    mixed = deepcopy(payloads["normalization"])
    mixed["command_id"] = "mixed-opportunity-command"
    assert client.post(
        "/api/v1/opportunities/source-opportunity-1/acquisition-cost-normalizations",
        json=mixed,
    ).status_code == 409

    missing = deepcopy(payloads["source_composition"])
    missing.update(
        command_id="missing-normalization-command",
        acquisition_normalization_id="missing-normalization",
    )
    assert client.post(
        f"/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
        json=missing,
    ).status_code == 404

    forbidden = deepcopy(payloads["binding"])
    forbidden["binding_id"] = "caller-owned"
    assert client.post(
        f"/api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings",
        json=forbidden,
    ).status_code == 422
    assert results["binding"].json()["opportunity_id"] == opportunity_id


def test_all_new_production_dependencies_own_one_connection_and_close(tmp_path, monkeypatch):
    database = tmp_path / "economics-production-cleanup.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    factories = (
        web_module.get_sourcing_economics_binding_entry,
        web_module.get_landed_cost_entry,
        web_module.get_shipping_allocation_entry,
        web_module.get_fx_observation_owner,
        web_module.get_acquisition_normalization_entry,
        web_module.get_economics_source_composition_entry,
    )
    for factory in factories:
        dependency = factory()
        entry = next(dependency)
        repository = entry._repository
        if hasattr(repository, "_landed_cost"):
            assert repository._landed_cost._connection is repository._connection
        if hasattr(repository, "_allocation"):
            assert repository._allocation._connection is repository._connection
        if hasattr(repository, "_fx"):
            assert repository._fx._connection is repository._connection
        dependency.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_partial_production_composition_failure_closes_repository(tmp_path, monkeypatch):
    database = tmp_path / "economics-partial-composition.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    captured = []
    real_repository = web_module.SQLiteSourcingEconomicsBindingRepository

    class CapturingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(
        web_module,
        "SQLiteSourcingEconomicsBindingRepository",
        CapturingRepository,
    )
    monkeypatch.setattr(
        web_module,
        "ProductionSourcingEconomicsBindingIdentityGenerator",
        lambda: (_ for _ in ()).throw(RuntimeError("broken production composition")),
    )

    with pytest.raises(RuntimeError, match="broken production composition"):
        next(web_module.get_sourcing_economics_binding_entry())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_fx_persistence_failure_is_503_atomic_bounded_and_closes(
    economics_chain_client,
    monkeypatch,
):
    client, database, _, _, _ = economics_chain_client
    captured = []

    class FailingRepository(SQLiteFXObservationRepository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)
            self._connection.execute(
                """CREATE TRIGGER fail_fx_receipt BEFORE INSERT ON fx_observation_receipts
                BEGIN SELECT RAISE(ABORT, 'private sqlite detail'); END"""
            )

    monkeypatch.setattr(web_module, "SQLiteFXObservationRepository", FailingRepository)
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "command_id": "failing-fx-command",
        "base_currency": "CNY",
        "quote_currency": "KRW",
        "rate": "190.123400",
        "observed_at": observed_at,
        "provider": "founder-observed-provider",
        "source_reference": "fx:manual:failure",
        "collection_method": "operator_capture",
    }
    response = client.post("/api/v1/fx-observations", json=payload)

    assert response.status_code == 503
    assert "private sqlite detail" not in response.text
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fx_observation_history").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fx_observation_receipts").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM founder_sourcing_admission_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM verified_economics_snapshots"
        ).fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")
