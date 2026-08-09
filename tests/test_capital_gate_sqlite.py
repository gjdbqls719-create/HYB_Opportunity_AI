from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.capital_gate import EvaluateCapitalGate, CapitalGateReplayConflictError
from app.application.capital_investment import AdmitDeployableCapitalSnapshot, AdmitIntendedOrderQuantity
from app.application.capital_readiness import EvaluateCapitalReadiness
from app.application.capital_requirement import CalculatePlannedAcquisitionCapitalRequirement
from app.infrastructure.capital_gate import (
    CapitalGateCommitError,
    CapitalGateHistoryError,
    CapitalGateReceiptError,
    MalformedCapitalGatePersistenceError,
    SQLiteCapitalGateRepository,
)
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.capital_readiness import SQLiteCapitalReadinessRepository
from app.infrastructure.capital_requirement import SQLitePlannedAcquisitionCapitalRequirementRepository
from test_capital_gate import command
from test_capital_investment_facts import capital_command, intent_command
from test_capital_investment_facts_sqlite import capital_owner, intent_owner
from test_capital_readiness import command as readiness_command
from test_capital_readiness_sqlite import owner as readiness_owner, seed as seed_readiness
from test_planned_acquisition_capital_requirement import command as requirement_command
from test_planned_acquisition_capital_requirement_sqlite import requirement_owner
from test_sourcing_authority_contract import NOW


HISTORY = "capital_gate_history"
RECEIPTS = "capital_gate_receipts"


def seed(path):
    opportunity, conservative, critical, market = seed_readiness(path)
    sources = type("Sources", (), {
        "conservative": conservative, "critical": critical, "market": market,
    })()
    readiness_request = readiness_command(
        sources,
        opportunity,
        critical_cost_assessment_id="critical-cost-assessment-1",
    )
    with SQLiteCapitalReadinessRepository(path) as repository:
        readiness = readiness_owner(repository)[0].execute(readiness_request).assessment
        admission = repository.get_sourcing_admission(critical.source_reference)
        normalization = repository.get_acquisition_normalization(
            readiness.source_manifest.acquisition_normalization_id
        )
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent = intent_owner(repository)[0].execute(intent_command(admission)).intent
        deployable = capital_owner(repository)[0].execute(
            capital_command(amount=normalization.total_per_unit_acquisition_cost * intent.quantity + 1, currency=normalization.target_currency)
        ).snapshot
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        requirement = requirement_owner(repository)[0].execute(
            requirement_command(intent, normalization)
        ).requirement
    return opportunity, readiness, requirement, deployable


def gate_owner(repository, identity="gate-1", *, fail=False):
    class Calls:
        def __init__(self, value):
            self.value = value
            self.calls = 0
        def __call__(self):
            self.calls += 1
            if fail:
                raise AssertionError("fresh dependency called on replay")
            return self.value
    identity_call = Calls(identity)
    evaluated = Calls(NOW + timedelta(days=2))
    committed = Calls(NOW + timedelta(days=2, minutes=1))
    return (
        EvaluateCapitalGate(
            repository,
            gate_id_generator=identity_call,
            evaluated_clock=evaluated,
            committed_clock=committed,
        ),
        identity_call,
        evaluated,
        committed,
    )


def counts(repository):
    return tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (HISTORY, RECEIPTS))


def test_round_trip_restart_replay_and_read_path_are_exact(tmp_path):
    path = tmp_path / "gate.sqlite3"
    opportunity, readiness, requirement, deployable = seed(path)
    repository_values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    request = command(repository_values, opportunity)
    with SQLiteCapitalGateRepository(path) as repository:
        first = gate_owner(repository)[0].execute(request)
        before = repository._connection.total_changes
        assert repository.get_gate(first.assessment.gate_id) == first.assessment
        assert repository.get_receipt(request.command_id) == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
    with SQLiteCapitalGateRepository(path) as repository:
        replay = gate_owner(repository, fail=True)[0].execute(request)
        assert replay.replayed is True
        assert replay.assessment == first.assessment
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_gate_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    opportunity, readiness, requirement, deployable = seed(path)
    values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    with SQLiteCapitalGateRepository(path) as repository:
        gate_owner(repository)[0].execute(command(values, opportunity))
        statement = f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET inserted_at=inserted_at"
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error"),
    [("history", CapitalGateHistoryError), ("receipt", CapitalGateReceiptError), ("commit", CapitalGateCommitError)],
)
def test_transaction_failures_rollback_and_retry(tmp_path, monkeypatch, failure, error):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    opportunity, readiness, requirement, deployable = seed(path)
    values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    request = command(values, opportunity)
    with SQLiteCapitalGateRepository(path) as repository:
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(f"CREATE TRIGGER forced BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END")
        else:
            original = repository._commit
            monkeypatch.setattr(repository, "_commit", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")))
        with pytest.raises(error):
            gate_owner(repository)[0].execute(request)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        if failure == "commit":
            monkeypatch.setattr(repository, "_commit", original)
            gate_owner(repository)[0].execute(request)


def test_concurrent_same_and_changed_commands_converge(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    opportunity, readiness, requirement, deployable = seed(path)
    values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    request = command(values, opportunity)
    barrier = Barrier(2)
    def run(identity, current_request=request):
        with SQLiteCapitalGateRepository(path) as repository:
            barrier.wait()
            return gate_owner(repository, identity)[0].execute(current_request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("gate-a", "gate-b")))
    assert len({value.assessment.gate_id for value in results}) == 1

    changed_path = tmp_path / "changed.sqlite3"
    opportunity, readiness, requirement, deployable = seed(changed_path)
    values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    requests = (command(values, opportunity), command(values, opportunity, requested_at=NOW + timedelta(seconds=1)))
    path = changed_path
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, f"gate-{index}", requests[index]) for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except CapitalGateReplayConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1


@pytest.mark.parametrize("corruption", ["state", "reasons", "fingerprint", "orphan"])
def test_malformed_persistence_is_rejected(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    opportunity, readiness, requirement, deployable = seed(path)
    values = type("Values", (), {"readiness": readiness, "requirement": requirement, "deployable": deployable})()
    with SQLiteCapitalGateRepository(path) as repository:
        result = gate_owner(repository)[0].execute(command(values, opportunity))
        if corruption == "orphan":
            repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
            repository._connection.execute("PRAGMA foreign_keys=OFF")
            repository._connection.execute(f"UPDATE {RECEIPTS} SET gate_id='missing'")
            repository._connection.commit()
            repository._connection.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(MalformedCapitalGatePersistenceError):
                repository.get_receipt(result.receipt.command_id)
            return
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(f"SELECT payload_json FROM {HISTORY} WHERE gate_id=?", (result.assessment.gate_id,)).fetchone()
        payload = json.loads(row[0])
        if corruption == "state":
            payload["state"] = "invalid"
        elif corruption == "reasons":
            payload["blocking_reasons"] = ["currency_mismatch"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        integrity = "0" * 64 if corruption == "fingerprint" else hashlib.sha256(encoded.encode()).hexdigest()
        repository._connection.execute(f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=? WHERE gate_id=?", (encoded, integrity, result.assessment.gate_id))
        repository._connection.commit()
        with pytest.raises(MalformedCapitalGatePersistenceError):
            repository.get_gate(result.assessment.gate_id)
