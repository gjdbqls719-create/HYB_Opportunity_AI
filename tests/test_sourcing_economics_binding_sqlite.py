from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Barrier

import pytest

from app.application.sourcing import (
    BindSourcingEconomicsSource,
    BindSourcingEconomicsSourceCommand,
    MalformedSourcingEconomicsBindingError,
    SourcingEconomicsBindingReplayConflictError,
    UnsupportedSourcingEconomicsBindingVersionError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.sourcing import (
    SQLiteSourcingAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
    SourcingEconomicsBindingCommitError,
    SourcingEconomicsBindingHistoryError,
    SourcingEconomicsBindingReceiptError,
)
from test_sourcing_authority_contract import NOW, command
from test_sourcing_authority_sqlite_persistence import boundary


def seed(path):
    with SQLiteSourcingAuthorityRepository(path) as repository:
        return boundary(repository).execute(command()).admission


def use_case(repository, *, fail=False):
    def supplied(value):
        return lambda: pytest.fail(f"{value} called on replay") if fail else value
    return BindSourcingEconomicsSource(
        repository, binding_id_generator=supplied("binding-1"),
        bound_clock=supplied(NOW + timedelta(minutes=1)),
        committed_clock=supplied(NOW + timedelta(minutes=2)),
    )


def binding_command(admission, **changes):
    values = dict(
        command_id="binding-command-1",
        opportunity_identity=OpportunityIdentity("opp-1", "discovery-1"),
        source_reference=admission.to_economics_source_reference(),
        requested_at=NOW,
    )
    values.update(changes)
    return BindSourcingEconomicsSourceCommand(**values)


def test_schema_round_trip_receipt_and_read_paths_are_deterministic(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        result = use_case(repository).execute(binding_command(admission))
        before = repository._connection.total_changes
        assert repository.get_binding("binding-1") == result.binding
        assert repository.get_binding("binding-1") == result.binding
        assert repository.get_receipt("binding-command-1") == result.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False


def test_restart_and_response_loss_replay_are_exact(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        first = use_case(repository).execute(binding_command(admission))
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        replay = use_case(repository, fail=True).execute(binding_command(admission))
        assert replay.binding == first.binding
        assert replay.receipt == first.receipt
        assert replay.replayed


def test_restart_changed_payload_conflicts(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        use_case(repository).execute(binding_command(admission))
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        with pytest.raises(SourcingEconomicsBindingReplayConflictError):
            use_case(repository, fail=True).execute(binding_command(
                admission, requested_at=NOW + timedelta(seconds=1)
            ))


@pytest.mark.parametrize("table", [
    "sourcing_economics_binding_history", "sourcing_economics_binding_receipts"
])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_append_only_triggers(table, operation, tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        use_case(repository).execute(binding_command(admission))
        with pytest.raises(sqlite3.IntegrityError):
            if operation == "UPDATE":
                repository._connection.execute(f"UPDATE {table} SET inserted_at=inserted_at")
            else:
                repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()


@pytest.mark.parametrize("failure,error", [
    ("binding", SourcingEconomicsBindingHistoryError),
    ("receipt", SourcingEconomicsBindingReceiptError),
    ("commit", SourcingEconomicsBindingCommitError),
])
def test_atomic_failure_rolls_back_without_partial_rows(failure, error, tmp_path, monkeypatch):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        if failure == "binding":
            repository._connection.execute("DROP TRIGGER trg_sourcing_economics_binding_history_no_delete")
            repository._connection.execute("""CREATE TRIGGER fail_binding BEFORE INSERT ON
                sourcing_economics_binding_history BEGIN SELECT RAISE(ABORT,'forced'); END""")
            repository._connection.commit()
        elif failure == "receipt":
            repository._connection.execute("""CREATE TRIGGER fail_receipt BEFORE INSERT ON
                sourcing_economics_binding_receipts BEGIN SELECT RAISE(ABORT,'forced'); END""")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")))
        with pytest.raises(error):
            use_case(repository).execute(binding_command(admission))
        assert repository._connection.execute("SELECT COUNT(*) FROM sourcing_economics_binding_history").fetchone()[0] == 0
        assert repository._connection.execute("SELECT COUNT(*) FROM sourcing_economics_binding_receipts").fetchone()[0] == 0
        assert repository._connection.in_transaction is False


def test_malformed_and_unsupported_persistence_are_distinguished(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        use_case(repository).execute(binding_command(admission))
        repository._connection.execute("DROP TRIGGER trg_sourcing_economics_binding_history_no_update")
        repository._connection.execute("UPDATE sourcing_economics_binding_history SET schema_version='future'")
        repository._connection.commit()
        with pytest.raises(UnsupportedSourcingEconomicsBindingVersionError):
            repository.get_binding("binding-1")
        repository._connection.execute("UPDATE sourcing_economics_binding_history SET schema_version='sourcing-economics-binding-v1', requested_at='bad'")
        repository._connection.commit()
        with pytest.raises(MalformedSourcingEconomicsBindingError):
            repository.get_binding("binding-1")


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    admission = seed(path)
    barrier = Barrier(2)
    def run(changed):
        with SQLiteSourcingEconomicsBindingRepository(path) as repository:
            barrier.wait()
            cmd = binding_command(admission, requested_at=NOW + timedelta(seconds=changed))
            try:
                return use_case(repository).execute(cmd)
            except SourcingEconomicsBindingReplayConflictError as error:
                return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(run, [0, 0]))
    assert values[0].binding == values[1].binding
    # A different payload cannot replace the committed binding.
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        with pytest.raises(SourcingEconomicsBindingReplayConflictError):
            use_case(repository).execute(binding_command(admission, requested_at=NOW + timedelta(seconds=1)))
