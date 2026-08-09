from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Barrier

import pytest

from app.application.goods_receipt import (
    AdmitGoodsReceipt,
    GoodsReceiptCumulativeQuantityConflictError,
    GoodsReceiptPublication,
    GoodsReceiptReplayConflictError,
)
from app.infrastructure.goods_receipt import (
    GoodsReceiptCommitError,
    GoodsReceiptHistoryError,
    GoodsReceiptReceiptError,
    MalformedGoodsReceiptPersistenceError,
    SQLiteGoodsReceiptRepository,
    UnsupportedGoodsReceiptVersionError,
)
from app.infrastructure.purchase_execution import SQLitePurchaseExecutionRepository
from test_goods_receipt import command
from test_purchase_execution_sqlite import command as purchase_command
from test_purchase_execution_sqlite import owner as purchase_owner
from test_purchase_execution_sqlite import seed as seed_purchase_sources


HISTORY = "goods_receipt_record_history"
RECEIPTS = "goods_receipt_record_receipts"


def seed(path):
    intent = seed_purchase_sources(path)
    with SQLitePurchaseExecutionRepository(path) as repository:
        return purchase_owner(repository).execute(purchase_command(intent)).record


def owner(repository, record, identity="goods-receipt-1", *, fail=False, offset=4):
    def forbidden():
        raise AssertionError("dependency called during replay")

    return AdmitGoodsReceipt(
        repository,
        record_id_generator=forbidden if fail else lambda: identity,
        admitted_clock=(
            forbidden if fail else lambda: record.executed_at + timedelta(minutes=offset)
        ),
        committed_clock=(
            forbidden
            if fail
            else lambda: record.executed_at + timedelta(minutes=offset + 1)
        ),
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_restart_replay_read_purity_index_and_connection_ownership(tmp_path):
    path = tmp_path / "goods-receipt.sqlite3"
    purchase = seed(path)
    request = command(purchase)
    with SQLiteGoodsReceiptRepository(path) as repository:
        first = owner(repository, purchase).execute(request)
        before = repository._connection.total_changes
        assert repository.get_record(first.record.record_id) == first.record
        assert repository.get_records_for_purchase(purchase.record_id) == (first.record,)
        assert repository.get_cumulative_received_quantity(purchase.record_id) == purchase.actual_quantity
        assert repository.validate_replay(request.command_id, request.fingerprint).receipt == first.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
        indexes = {
            row[1] for row in repository._connection.execute(f"PRAGMA index_list({HISTORY})")
        }
        assert "ix_goods_receipt_record_purchase_execution" in indexes
        assert repository._purchase._connection is repository._connection
    with SQLiteGoodsReceiptRepository(path) as repository:
        replay = owner(repository, purchase, fail=True).execute(request)
        assert replay.replayed is True
        assert replay.record == first.record
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)

    connection = sqlite3.connect(path)
    injected = SQLiteGoodsReceiptRepository(connection=connection)
    injected.close()
    connection.execute("SELECT 1")
    connection.close()


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_command_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    purchase = seed(path)
    with SQLiteGoodsReceiptRepository(path) as repository:
        owner(repository, purchase).execute(command(purchase))
        statement = (
            f"DELETE FROM {table}"
            if operation == "DELETE"
            else f"UPDATE {table} SET inserted_at=inserted_at"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    (
        ("history", GoodsReceiptHistoryError),
        ("receipt", GoodsReceiptReceiptError),
        ("commit", GoodsReceiptCommitError),
    ),
)
def test_transaction_failures_rollback_without_cumulative_drift_and_retry(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    purchase = seed(path)
    with SQLiteGoodsReceiptRepository(path) as repository:
        request = command(purchase)
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
        else:
            original = repository._commit
            monkeypatch.setattr(
                repository,
                "_commit",
                lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
            )
        with pytest.raises(error_type):
            owner(repository, purchase).execute(request)
        assert counts(repository) == (0, 0)
        assert repository.get_cumulative_received_quantity(purchase.record_id) == 0
        assert repository.get_purchase_execution_record(purchase.record_id) == purchase
        assert repository._connection.in_transaction is False
        if failure in {"history", "receipt"}:
            repository._connection.execute("DROP TRIGGER forced")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", original)
        retry = owner(repository, purchase, "goods-receipt-retry").execute(request)
        assert retry.replayed is False
        assert counts(repository) == (1, 1)


def test_multiple_partial_receipts_exact_fill_and_post_full_rejection(tmp_path):
    path = tmp_path / "partial.sqlite3"
    purchase = seed(path)
    first_quantity = purchase.actual_quantity - 1
    with SQLiteGoodsReceiptRepository(path) as repository:
        first = owner(repository, purchase).execute(
            command(
                purchase,
                received_quantity=first_quantity,
                sellable_quantity=first_quantity - 1,
                damaged_quantity=1,
            )
        )
        second = owner(repository, purchase, "goods-receipt-2", offset=6).execute(
            command(
                purchase,
                command_id="goods-receipt-command-2",
                received_quantity=1,
                sellable_quantity=1,
                damaged_quantity=0,
                delivery_reference=None,
            )
        )
        assert first.record.record_id != second.record.record_id
        assert repository.get_cumulative_received_quantity(purchase.record_id) == purchase.actual_quantity
        with pytest.raises(GoodsReceiptCumulativeQuantityConflictError):
            owner(repository, purchase, "goods-receipt-3", offset=8).execute(
                command(
                    purchase,
                    command_id="goods-receipt-command-3",
                    received_quantity=1,
                    sellable_quantity=1,
                    damaged_quantity=0,
                )
            )
        assert counts(repository) == (2, 2)


def test_multi_connection_concurrent_valid_partial_receipts_never_lose_quantity(tmp_path):
    path = tmp_path / "concurrent-valid.sqlite3"
    purchase = seed(path)
    first_quantity = purchase.actual_quantity // 2
    quantities = (first_quantity, purchase.actual_quantity - first_quantity)
    requests = tuple(
        command(
            purchase,
            command_id=f"valid-{index}",
            received_quantity=quantity,
            sellable_quantity=quantity,
            damaged_quantity=0,
        )
        for index, quantity in enumerate(quantities)
    )
    barrier = Barrier(2)

    def execute(index):
        with SQLiteGoodsReceiptRepository(path) as repository:
            barrier.wait()
            return owner(repository, purchase, f"valid-record-{index}").execute(
                requests[index]
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, range(2)))
    assert all(isinstance(value, GoodsReceiptPublication) for value in results)
    with SQLiteGoodsReceiptRepository(path) as repository:
        assert counts(repository) == (2, 2)
        assert repository.get_cumulative_received_quantity(purchase.record_id) == purchase.actual_quantity


def test_multi_connection_concurrent_over_receipt_commits_only_safe_event(tmp_path):
    path = tmp_path / "concurrent-over.sqlite3"
    purchase = seed(path)
    quantity = purchase.actual_quantity - 1
    requests = tuple(
        command(
            purchase,
            command_id=f"over-{index}",
            received_quantity=quantity,
            sellable_quantity=quantity,
            damaged_quantity=0,
        )
        for index in range(2)
    )
    barrier = Barrier(2)

    def execute(index):
        with SQLiteGoodsReceiptRepository(path) as repository:
            barrier.wait()
            return owner(repository, purchase, f"over-record-{index}").execute(
                requests[index]
            )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except GoodsReceiptCumulativeQuantityConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, GoodsReceiptPublication) for value in outcomes) == 1
    assert sum(
        isinstance(value, GoodsReceiptCumulativeQuantityConflictError)
        for value in outcomes
    ) == 1
    with SQLiteGoodsReceiptRepository(path) as repository:
        assert counts(repository) == (1, 1)
        assert repository.get_cumulative_received_quantity(purchase.record_id) == quantity


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "concurrent-replay.sqlite3"
    purchase = seed(path)
    request = command(purchase)
    barrier = Barrier(2)

    def same(index):
        with SQLiteGoodsReceiptRepository(path) as repository:
            barrier.wait()
            return owner(repository, purchase, f"same-{index}").execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(same, range(2)))
    assert {value.record.record_id for value in results} == {results[0].record.record_id}
    assert sorted(value.replayed for value in results) == [False, True]

    changed_path = tmp_path / "concurrent-changed.sqlite3"
    changed_purchase = seed(changed_path)
    requests = (
        command(changed_purchase),
        replace(command(changed_purchase), delivery_reference="different-delivery"),
    )
    barrier = Barrier(2)

    def changed(index):
        with SQLiteGoodsReceiptRepository(changed_path) as repository:
            barrier.wait()
            return owner(repository, changed_purchase, f"changed-{index}").execute(
                requests[index]
            )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(changed, index) for index in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except GoodsReceiptReplayConflictError as error:
                outcomes.append(error)
    assert sum(isinstance(value, GoodsReceiptPublication) for value in outcomes) == 1
    assert sum(isinstance(value, GoodsReceiptReplayConflictError) for value in outcomes) == 1


def test_integrity_schema_and_orphan_corruption_are_rejected(tmp_path):
    corrupt_path = tmp_path / "corrupt.sqlite3"
    purchase = seed(corrupt_path)
    with SQLiteGoodsReceiptRepository(corrupt_path) as repository:
        result = owner(repository, purchase).execute(command(purchase))
        repository._connection.execute(
            "DROP TRIGGER trg_goods_receipt_record_history_no_update"
        )
        repository._connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint='corrupt' WHERE record_id=?",
            (result.record.record_id,),
        )
        repository._connection.commit()
        with pytest.raises(MalformedGoodsReceiptPersistenceError):
            repository.get_record(result.record.record_id)

    schema_path = tmp_path / "schema.sqlite3"
    schema_purchase = seed(schema_path)
    with SQLiteGoodsReceiptRepository(schema_path) as repository:
        result = owner(repository, schema_purchase).execute(command(schema_purchase))
        repository._connection.execute(
            "DROP TRIGGER trg_goods_receipt_record_history_no_update"
        )
        repository._connection.execute(
            f"UPDATE {HISTORY} SET schema_version='unsupported' WHERE record_id=?",
            (result.record.record_id,),
        )
        repository._connection.commit()
        with pytest.raises(UnsupportedGoodsReceiptVersionError):
            repository.get_record(result.record.record_id)

    orphan_path = tmp_path / "orphan.sqlite3"
    orphan_purchase = seed(orphan_path)
    request = command(orphan_purchase)
    with SQLiteGoodsReceiptRepository(orphan_path) as repository:
        owner(repository, orphan_purchase).execute(request)
    with sqlite3.connect(orphan_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TRIGGER trg_goods_receipt_record_history_no_delete")
        connection.execute(f"DELETE FROM {HISTORY}")
        connection.commit()
    with SQLiteGoodsReceiptRepository(orphan_path) as repository:
        with pytest.raises(MalformedGoodsReceiptPersistenceError):
            repository.validate_replay(request.command_id, request.fingerprint)
