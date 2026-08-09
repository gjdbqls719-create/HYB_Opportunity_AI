from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.capital_investment import AdmitIntendedOrderQuantity
from app.application.capital_requirement import (
    CalculatePlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementReplayConflictError,
)
from app.application.sourcing import NormalizeAcquisitionCosts
from app.domain.capital import UpfrontCostScopeStatus
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.capital_requirement import (
    MalformedPlannedAcquisitionCapitalRequirementPersistenceError,
    PlannedAcquisitionCapitalRequirementCommitError,
    PlannedAcquisitionCapitalRequirementHistoryError,
    PlannedAcquisitionCapitalRequirementReceiptError,
    SQLitePlannedAcquisitionCapitalRequirementRepository,
)
from app.infrastructure.sourcing import (
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteLandedCostCompositionRepository,
)
from test_acquisition_cost_normalization import Calls, command as normalization_command
from test_acquisition_cost_normalization_sqlite import owner as normalization_owner, seed_sources
from test_capital_investment_facts import intent_command
from test_capital_investment_facts_sqlite import intent_owner
from test_planned_acquisition_capital_requirement import command
from test_sourcing_authority_contract import NOW


HISTORY = "planned_acquisition_capital_requirement_history"
RECEIPTS = "planned_acquisition_capital_requirement_receipts"


def seed(path):
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        normalization = normalization_owner(repository)[0].execute(
            normalization_command(composition, authorities, observations)
        ).normalization
    with SQLiteLandedCostCompositionRepository(path) as repository:
        binding = repository.get_binding(composition.binding_reference)
        admission = repository.get_source_admission(binding.source_reference)
    with SQLiteCapitalInvestmentFactsRepository(path) as repository:
        intent = intent_owner(repository)[0].execute(intent_command(admission)).intent
    return intent, normalization


def requirement_owner(repository, identity="requirement-1", *, fail=False):
    identity_call = Calls(AssertionError("identity called on replay") if fail else identity)
    calculated = Calls(AssertionError("calculated called on replay") if fail else NOW + timedelta(minutes=13))
    committed = Calls(AssertionError("committed called on replay") if fail else NOW + timedelta(minutes=14))
    return (
        CalculatePlannedAcquisitionCapitalRequirement(
            repository,
            requirement_id_generator=identity_call,
            calculated_clock=calculated,
            committed_clock=committed,
        ),
        identity_call,
        calculated,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_restart_and_exact_replay_preserve_all_authoritative_facts(tmp_path):
    path = tmp_path / "requirement.sqlite3"
    intent, normalization = seed(path)
    request = command(intent, normalization)
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        first = requirement_owner(repository)[0].execute(request)
        before = repository._connection.total_changes
        assert repository.get_requirement(first.requirement.requirement_id) == first.requirement
        assert repository.get_receipt(request.command_id) == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False

    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        replay = requirement_owner(repository, fail=True)[0].execute(request)
        assert replay.replayed is True
        assert replay.requirement == first.requirement
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_blocked_scope_round_trip_preserves_no_amount_and_reason(tmp_path):
    path = tmp_path / "blocked.sqlite3"
    intent, normalization = seed(path)
    request = command(intent, normalization, scope_status=UpfrontCostScopeStatus.UNRESOLVED)
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        result = requirement_owner(repository)[0].execute(request)
        restored = repository.get_requirement(result.requirement.requirement_id)
        assert restored == result.requirement
        assert restored.planned_acquisition_capital is None
        assert tuple(value.value for value in restored.blocking_reasons) == (
            "upfront_cost_scope_unverified",
        )


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    intent, normalization = seed(path)
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        requirement_owner(repository)[0].execute(command(intent, normalization))
        statement = f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET inserted_at=inserted_at"
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        ("history", PlannedAcquisitionCapitalRequirementHistoryError),
        ("receipt", PlannedAcquisitionCapitalRequirementReceiptError),
        ("commit", PlannedAcquisitionCapitalRequirementCommitError),
    ],
)
def test_transaction_failure_rolls_back_and_retry_is_possible(tmp_path, monkeypatch, failure, error_type):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    intent, normalization = seed(path)
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced_failure BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
        else:
            original = repository._commit
            monkeypatch.setattr(repository, "_commit", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")))
        with pytest.raises(error_type):
            requirement_owner(repository)[0].execute(command(intent, normalization))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        if failure == "commit":
            monkeypatch.setattr(repository, "_commit", original)
            requirement_owner(repository)[0].execute(command(intent, normalization))


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    intent, normalization = seed(path)
    barrier = Barrier(2)

    def run(identity, changed=False):
        with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
            barrier.wait()
            request = command(
                intent,
                normalization,
                scope_status=(UpfrontCostScopeStatus.UNRESOLVED if changed else UpfrontCostScopeStatus.COMPLETE),
            )
            return requirement_owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("requirement-a", "requirement-b")))
    assert len({value.requirement.requirement_id for value in results}) == 1

    conflict_path = tmp_path / "concurrent-conflict.sqlite3"
    intent, normalization = seed(conflict_path)
    path = conflict_path
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, "requirement-c", False), pool.submit(run, "requirement-d", True)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except PlannedAcquisitionCapitalRequirementReplayConflictError:
                outcomes.append("conflict")
    assert outcomes.count("conflict") == 1


@pytest.mark.parametrize("corruption", ["arithmetic", "fingerprint", "orphan"])
def test_malformed_persistence_is_rejected_without_silent_repair(tmp_path, corruption):
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    intent, normalization = seed(path)
    with SQLitePlannedAcquisitionCapitalRequirementRepository(path) as repository:
        result = requirement_owner(repository)[0].execute(command(intent, normalization))
        if corruption == "orphan":
            repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
            repository._connection.execute("PRAGMA foreign_keys=OFF")
            repository._connection.execute(
                f"UPDATE {RECEIPTS} SET requirement_id='missing' WHERE command_id=?",
                (result.receipt.command_id,),
            )
            repository._connection.commit()
            repository._connection.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(MalformedPlannedAcquisitionCapitalRequirementPersistenceError):
                repository.get_receipt(result.receipt.command_id)
            return
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE requirement_id=?",
            (result.requirement.requirement_id,),
        ).fetchone()
        payload = json.loads(row[0])
        if corruption == "arithmetic":
            payload["planned_acquisition_capital"] = "1"
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            integrity = hashlib.sha256(encoded.encode()).hexdigest()
        else:
            encoded = row[0]
            integrity = "0" * 64
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?, integrity_fingerprint=? WHERE requirement_id=?",
            (encoded, integrity, result.requirement.requirement_id),
        )
        repository._connection.commit()
        with pytest.raises(MalformedPlannedAcquisitionCapitalRequirementPersistenceError):
            repository.get_requirement(result.requirement.requirement_id)


def test_injected_connection_ownership_is_preserved_and_owned_connection_closes(tmp_path):
    path = tmp_path / "resources.sqlite3"
    seed(path)
    connection = sqlite3.connect(path)
    repository = SQLitePlannedAcquisitionCapitalRequirementRepository(connection=connection)
    repository.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()

    owned = SQLitePlannedAcquisitionCapitalRequirementRepository(path)
    owned_connection = owned._connection
    owned.close()
    with pytest.raises(sqlite3.ProgrammingError):
        owned_connection.execute("SELECT 1")
