from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.sourcing import (
    AdmitShippingAllocationAuthority,
    ShippingAllocationAuthorityReplayConflictError,
)
from app.domain.sourcing import CostAllocationBasis
from app.infrastructure.sourcing import (
    MalformedShippingAllocationAuthorityPersistenceError,
    SQLiteLandedCostCompositionRepository,
    SQLiteShippingAllocationAuthorityRepository,
    ShippingAllocationAuthorityCommitError,
    ShippingAllocationAuthorityHistoryError,
    ShippingAllocationAuthorityReceiptError,
)
from test_landed_cost_composition_sqlite import (
    composition_command,
    seed,
    use_case as landed_cost_use_case,
)
from test_shipping_allocation_authority_reconciliation import Calls, command
from test_sourcing_authority_contract import NOW


HISTORY = "shipping_allocation_authority_history"
RECEIPTS = "shipping_allocation_authority_receipts"


def seed_composition(path):
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        return landed_cost_use_case(repository)[0].execute(
            composition_command(binding)
        ).composition


def owner(repository, *, fail=False, identity="allocation-authority-1"):
    identity_call = Calls(identity)
    admitted = Calls(NOW + timedelta(minutes=5))
    committed = Calls(NOW + timedelta(minutes=6))
    if fail:
        identity_call = Calls(AssertionError("identity called on replay"))
    return (
        AdmitShippingAllocationAuthority(
            repository,
            authority_id_generator=identity_call,
            admitted_clock=admitted,
            committed_clock=committed,
        ),
        identity_call,
        admitted,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_round_trip_and_read_path_are_exact_and_pure(tmp_path):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        result = owner(repository)[0].execute(command(composition))
        before = repository._connection.total_changes

        assert repository.get_authority(result.authority.authority_id) == result.authority
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
        assert counts(repository) == (1, 1)


def test_restart_exact_replay_preserves_every_fact_without_new_calls(tmp_path):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        first = owner(repository)[0].execute(command(composition))

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during replay")

    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        replay = AdmitShippingAllocationAuthority(
            repository,
            authority_id_generator=Never(),
            admitted_clock=Never(),
            committed_clock=Never(),
        ).execute(command(composition))
        assert replay.replayed is True
        assert replay.authority == first.authority
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_changed_payload_conflicts_after_restart(tmp_path):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        owner(repository)[0].execute(command(composition))
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        with pytest.raises(ShippingAllocationAuthorityReplayConflictError):
            owner(repository)[0].execute(
                command(composition, per_order_denominator=101)
            )
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(tmp_path, table, operation):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        owner(repository)[0].execute(command(composition))
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(
                f"{operation} FROM {table}"
                if operation == "DELETE"
                else f"UPDATE {table} SET inserted_at=inserted_at"
            )
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        ("authority", ShippingAllocationAuthorityHistoryError),
        ("receipt", ShippingAllocationAuthorityReceiptError),
        ("commit", ShippingAllocationAuthorityCommitError),
    ],
)
def test_atomic_failure_rolls_back_and_closes_transaction(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        if failure in {"authority", "receipt"}:
            table = HISTORY if failure == "authority" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced_failure BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
        else:
            monkeypatch.setattr(
                repository,
                "_commit",
                lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
            )
        with pytest.raises(error_type):
            owner(repository)[0].execute(command(composition))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    barrier = Barrier(2)

    def run(denominator, identity):
        with SQLiteShippingAllocationAuthorityRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity=identity)[0].execute(
                command(composition, per_order_denominator=denominator)
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: run(100, item), ("authority-a", "authority-b")))
    assert {value.authority.authority_id for value in results} <= {"authority-a", "authority-b"}
    assert len({value.authority.authority_id for value in results}) == 1

    other_path = tmp_path / "allocation-conflict.sqlite3"
    other = seed_composition(other_path)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                lambda denominator, identity: run_other(other_path, other, barrier, denominator, identity),
                denominator,
                identity,
            )
            for denominator, identity in ((100, "authority-c"), (101, "authority-d"))
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except ShippingAllocationAuthorityReplayConflictError:
                outcomes.append("conflict")
    assert len([value for value in outcomes if value != "conflict"]) == 1
    assert outcomes.count("conflict") == 1


def run_other(path, composition, barrier, denominator, identity):
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        barrier.wait()
        return owner(repository, identity=identity)[0].execute(
            command(composition, per_order_denominator=denominator)
        )


def test_malformed_payload_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "allocation.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        result = owner(repository)[0].execute(command(composition))
        repository._connection.execute(
            f"DROP TRIGGER trg_{HISTORY}_no_update"
        )
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE authority_id=?",
            (result.authority.authority_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["status"] = "not-a-status"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = __import__("hashlib").sha256(encoded.encode()).hexdigest()
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?, integrity_fingerprint=?",
            (encoded, fingerprint),
        )
        repository._connection.commit()
        with pytest.raises(MalformedShippingAllocationAuthorityPersistenceError):
            repository.get_authority(result.authority.authority_id)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.__setitem__("allocation_basis", "not-a-basis"),
        lambda payload: payload.__setitem__("original_allocation_basis", "per_unit"),
        lambda payload: payload["denominator"].__setitem__("quantity", 0),
        lambda payload: payload.__setitem__("schema_version", "future-version"),
    ],
)
def test_malformed_authoritative_facts_are_never_silently_repaired(
    tmp_path, mutation
):
    path = tmp_path / "malformed.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        result = owner(repository)[0].execute(command(composition))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE authority_id=?",
            (result.authority.authority_id,),
        ).fetchone()
        payload = json.loads(row[0])
        mutation(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = __import__("hashlib").sha256(encoded.encode()).hexdigest()
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=?",
            (encoded, fingerprint),
        )
        repository._connection.commit()
        with pytest.raises(MalformedShippingAllocationAuthorityPersistenceError):
            repository.get_authority(result.authority.authority_id)


def test_integrity_fingerprint_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "integrity.sqlite3"
    composition = seed_composition(path)
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        result = owner(repository)[0].execute(command(composition))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint=?",
            ("0" * 64,),
        )
        repository._connection.commit()
        with pytest.raises(MalformedShippingAllocationAuthorityPersistenceError):
            repository.get_authority(result.authority.authority_id)

    orphan_path = tmp_path / "orphan.sqlite3"
    composition = seed_composition(orphan_path)
    with SQLiteShippingAllocationAuthorityRepository(orphan_path) as repository:
        result = owner(repository)[0].execute(command(composition))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_delete")
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"DELETE FROM {HISTORY} WHERE authority_id=?",
            (result.authority.authority_id,),
        )
        repository._connection.commit()
        with pytest.raises(MalformedShippingAllocationAuthorityPersistenceError):
            repository.get_receipt(result.receipt.command_id)


def test_injected_connection_remains_caller_owned(tmp_path):
    path = tmp_path / "injected.sqlite3"
    composition = seed_composition(path)
    connection = sqlite3.connect(path)
    with SQLiteShippingAllocationAuthorityRepository(connection=connection) as repository:
        owner(repository)[0].execute(command(composition))
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()
