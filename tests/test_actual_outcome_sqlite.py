from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from app.application.actual_outcome import ActualOutcomeReplayConflictError
from app.infrastructure.actual_acquisition_settlement import SQLiteActualAcquisitionSettlementRepository
from app.infrastructure.actual_outcome import (
    ActualOutcomeCommitError,
    ActualOutcomeHistoryError,
    ActualOutcomeReceiptError,
    MalformedActualOutcomePersistenceError,
    SQLiteActualOutcomeRepository,
)
from app.infrastructure.actual_sale_settlement import SQLiteActualSaleSettlementRepository
from app.infrastructure.goods_receipt import SQLiteGoodsReceiptRepository
from test_actual_acquisition_settlement import request as acquisition_command
from test_actual_acquisition_settlement_sqlite import owner as acquisition_owner
from test_actual_acquisition_settlement_sqlite import seed as seed_purchase
from test_actual_outcome import command as outcome_command
from test_actual_outcome import owner as outcome_owner
from test_actual_sale_settlement import command as sale_command
from test_actual_sale_settlement import owner as sale_owner
from test_goods_receipt import command as goods_command
from test_goods_receipt_sqlite import owner as goods_owner


HISTORY = "actual_outcome_history"
RECEIPTS = "actual_outcome_receipts"


def seed(path):
    purchase = seed_purchase(path)
    with SQLiteActualAcquisitionSettlementRepository(path) as repository:
        acquisition = acquisition_owner(repository, purchase).execute(acquisition_command(purchase)).settlement
    with SQLiteGoodsReceiptRepository(path) as repository:
        receipt = goods_owner(repository, purchase).execute(goods_command(purchase)).record
    request = sale_command(receipt)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        sale = sale_owner(repository, request).execute(request).settlement
    return acquisition, receipt, sale


def counts(repository):
    return tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (HISTORY, RECEIPTS))


def test_round_trip_restart_replay_alias_read_purity_and_connection_ownership(tmp_path):
    path = tmp_path / "actual-outcome.sqlite3"
    acquisition, _, sale = seed(path)
    request = outcome_command(acquisition, (sale,))
    with SQLiteActualOutcomeRepository(path) as repository:
        first = outcome_owner(repository, request).execute(request)
        before = repository._connection.total_changes
        assert repository.get_outcome(first.outcome.outcome_id) == first.outcome
        assert repository.validate_replay(request.command_id, request.fingerprint).outcome == first.outcome
        assert repository._connection.total_changes == before
        assert repository._acquisition._connection is repository._connection
        assert repository._sale._connection is repository._connection
        assert repository._goods._connection is repository._connection
    with SQLiteActualOutcomeRepository(path) as repository:
        replay = outcome_owner(repository, request, fail=True).execute(request)
        assert replay.replayed is True
        alias_request = replace(request, command_id="actual-outcome-command-alias")
        alias = outcome_owner(repository, alias_request, identity="unused").execute(alias_request)
        assert alias.aliased is True
        assert alias.outcome.outcome_id == first.outcome.outcome_id
        assert counts(repository) == (1, 2)

    connection = sqlite3.connect(path)
    injected = SQLiteActualOutcomeRepository(connection=connection)
    injected.close()
    connection.execute("SELECT 1")
    connection.close()


@pytest.mark.parametrize("table", (HISTORY, RECEIPTS))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / "append-only.sqlite3"
    acquisition, _, sale = seed(path)
    request = outcome_command(acquisition, (sale,))
    with SQLiteActualOutcomeRepository(path) as repository:
        outcome_owner(repository, request).execute(request)
        statement = f"UPDATE {table} SET inserted_at=inserted_at" if operation == "UPDATE" else f"DELETE FROM {table}"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)


@pytest.mark.parametrize(
    ("failure", "error_type"),
    (("history", ActualOutcomeHistoryError), ("receipt", ActualOutcomeReceiptError), ("commit", ActualOutcomeCommitError)),
)
def test_transaction_failure_rolls_back_and_retry_succeeds(tmp_path, monkeypatch, failure, error_type):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    acquisition, _, sale = seed(path)
    request = outcome_command(acquisition, (sale,))
    with SQLiteActualOutcomeRepository(path) as repository:
        if failure == "history":
            monkeypatch.setattr(repository, "_insert_history", lambda *_: (_ for _ in ()).throw(ActualOutcomeHistoryError("fail")))
        elif failure == "receipt":
            monkeypatch.setattr(repository, "_insert_receipt", lambda *_: (_ for _ in ()).throw(ActualOutcomeReceiptError("fail")))
        else:
            monkeypatch.setattr(repository, "_commit", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("fail")))
        with pytest.raises(error_type):
            outcome_owner(repository, request).execute(request)
        assert counts(repository) == (0, 0)
    with SQLiteActualOutcomeRepository(path) as repository:
        result = outcome_owner(repository, request).execute(request)
        assert result.outcome.outcome_id == "actual-outcome-1"


def test_changed_replay_fingerprint_payload_corruption_and_orphan_receipt_fail_closed(tmp_path):
    path = tmp_path / "malformed.sqlite3"
    acquisition, _, sale = seed(path)
    request = outcome_command(acquisition, (sale,))
    with SQLiteActualOutcomeRepository(path) as repository:
        result = outcome_owner(repository, request).execute(request)
        with pytest.raises(ActualOutcomeReplayConflictError):
            repository.validate_replay(request.command_id, "0" * 64)
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(f"UPDATE {HISTORY} SET integrity_fingerprint='bad' WHERE outcome_id=?", (result.outcome.outcome_id,))
        repository._connection.commit()
        with pytest.raises(MalformedActualOutcomePersistenceError):
            repository.get_outcome(result.outcome.outcome_id)

    orphan = tmp_path / "orphan.sqlite3"
    with SQLiteActualOutcomeRepository(orphan) as repository:
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute(
            f"INSERT INTO {RECEIPTS} VALUES(?,?,?,?,?,?)",
            ("orphan-command", "missing", "0" * 64, request.requested_at.isoformat(), "actual-outcome-receipt-v1", request.requested_at.isoformat()),
        )
        repository._connection.commit()
        with pytest.raises(MalformedActualOutcomePersistenceError):
            repository.validate_replay("orphan-command", "0" * 64)


def test_concurrent_same_command_converges_and_distinct_commands_alias_one_scope(tmp_path):
    path = tmp_path / "concurrency.sqlite3"
    acquisition, _, sale = seed(path)
    request = outcome_command(acquisition, (sale,))

    def execute_same(index):
        with SQLiteActualOutcomeRepository(path) as repository:
            return outcome_owner(repository, request, identity=f"outcome-{index}").execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(execute_same, range(2)))
    assert {value.outcome.outcome_id for value in same} == {same[0].outcome.outcome_id}
    assert sorted(value.replayed for value in same) == [False, True]

    alias_requests = tuple(replace(request, command_id=f"alias-{index}") for index in range(2))

    def execute_alias(index):
        with SQLiteActualOutcomeRepository(path) as repository:
            return outcome_owner(repository, alias_requests[index], identity=f"unused-{index}").execute(alias_requests[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        aliases = tuple(pool.map(execute_alias, range(2)))
    assert all(value.aliased for value in aliases)
    assert {value.outcome.outcome_id for value in aliases} == {same[0].outcome.outcome_id}
    with SQLiteActualOutcomeRepository(path) as repository:
        assert counts(repository) == (1, 3)
