from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Barrier

import pytest

from app.application.actual_sale_settlement import (
    ActualSaleSettlementOversellConflictError,
    ActualSaleSettlementReplayConflictError,
    ActualSaleSettlementReportConflictError,
    ActualSaleSettlementRevisionConflictError,
    ActualSaleSettlementTerminalConflictError,
    ActualSaleSettlementWindowConflictError,
)
from app.domain.capital import ActualSaleSettlementState
from app.infrastructure.actual_sale_settlement import (
    ActualSaleSettlementCommitError,
    ActualSaleSettlementHistoryError,
    ActualSaleSettlementReceiptError,
    MalformedActualSaleSettlementPersistenceError,
    SQLiteActualSaleSettlementRepository,
)
from app.infrastructure.goods_receipt import SQLiteGoodsReceiptRepository
from test_actual_sale_settlement import command as sale_command
from test_actual_sale_settlement import owner as sale_owner
from test_goods_receipt import command as goods_command
from test_goods_receipt_sqlite import owner as goods_owner
from test_goods_receipt_sqlite import seed as seed_purchase


HISTORY = "actual_sale_settlement_history"
RECEIPTS = "actual_sale_settlement_receipts"


def seed(path):
    purchase = seed_purchase(path)
    with SQLiteGoodsReceiptRepository(path) as repository:
        receipt = goods_owner(repository, purchase).execute(goods_command(purchase)).record
    return purchase, receipt


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_round_trip_restart_replay_read_purity_and_connection_ownership(tmp_path):
    path = tmp_path / "actual-sale.sqlite3"
    _, receipt = seed(path)
    request = sale_command(receipt)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        first = sale_owner(repository, request).execute(request)
        before = repository._connection.total_changes
        assert repository.get_settlement(first.settlement.settlement_id) == first.settlement
        assert repository.validate_replay(request.command_id, request.fingerprint).receipt == first.receipt
        assert repository._connection.total_changes == before
        assert repository._goods._connection is repository._connection
    with SQLiteActualSaleSettlementRepository(path) as repository:
        replay = sale_owner(repository, request, identity="unused", fail=True).execute(request)
        assert replay.replayed is True
        assert replay.settlement == first.settlement
        assert counts(repository) == (1, 1)

    connection = sqlite3.connect(path)
    injected = SQLiteActualSaleSettlementRepository(connection=connection)
    injected.close()
    connection.execute("SELECT 1")
    connection.close()


@pytest.mark.parametrize("table", (HISTORY, RECEIPTS))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_history_and_receipts_are_append_only(tmp_path, table, operation):
    path = tmp_path / f"append-{table}-{operation}.sqlite3"
    _, receipt = seed(path)
    request = sale_command(receipt)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        sale_owner(repository, request).execute(request)
        statement = f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET inserted_at=inserted_at"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    (("history", ActualSaleSettlementHistoryError), ("receipt", ActualSaleSettlementReceiptError), ("commit", ActualSaleSettlementCommitError)),
)
def test_transaction_failure_rolls_back_and_retry_succeeds(tmp_path, monkeypatch, failure, error_type):
    path = tmp_path / f"rollback-{failure}.sqlite3"
    _, receipt = seed(path)
    request = sale_command(receipt)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        attribute = {"history": "_insert_history", "receipt": "_insert_receipt", "commit": "_commit"}[failure]
        original = getattr(repository, attribute)
        if failure == "commit":
            monkeypatch.setattr(repository, attribute, lambda: (_ for _ in ()).throw(sqlite3.OperationalError("commit failure")))
        else:
            monkeypatch.setattr(repository, attribute, lambda *args: (_ for _ in ()).throw(error_type("injected")))
        with pytest.raises(error_type):
            sale_owner(repository, request).execute(request)
        assert counts(repository) == (0, 0)
        monkeypatch.setattr(repository, attribute, original)
        assert sale_owner(repository, request).execute(request).replayed is False
        assert counts(repository) == (1, 1)


def test_blocked_complete_linearity_terminal_and_changed_replay(tmp_path):
    from test_actual_sale_settlement import complete_facts, unknown
    from app.domain.capital import ActualSaleMonetaryCategory

    path = tmp_path / "revisions.sqlite3"
    _, receipt = seed(path)
    facts = list(complete_facts())
    facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    first_request = sale_command(receipt, fixed_monetary_facts=tuple(facts))
    with SQLiteActualSaleSettlementRepository(path) as repository:
        first = sale_owner(repository, first_request).execute(first_request)
        assert first.settlement.state is ActualSaleSettlementState.BLOCKED
        with pytest.raises(ActualSaleSettlementReplayConflictError):
            sale_owner(repository, replace(first_request, fulfilled_outbound_quantity=0)).execute(replace(first_request, fulfilled_outbound_quantity=0))
        child_request = sale_command(receipt, command_id="sale-command-2", predecessor_settlement_id=first.settlement.settlement_id)
        child = sale_owner(repository, child_request, identity="sale-settlement-2").execute(child_request)
        assert child.settlement.state is ActualSaleSettlementState.COMPLETE
        with pytest.raises(ActualSaleSettlementTerminalConflictError):
            terminal = replace(child_request, command_id="sale-command-3", predecessor_settlement_id=child.settlement.settlement_id)
            sale_owner(repository, terminal, identity="sale-settlement-3").execute(terminal)
        with pytest.raises(ActualSaleSettlementRevisionConflictError):
            fork = replace(child_request, command_id="sale-command-4", predecessor_settlement_id=first.settlement.settlement_id)
            sale_owner(repository, fork, identity="sale-settlement-4").execute(fork)


def test_non_overlapping_windows_succeed_overlap_and_oversell_fail(tmp_path):
    path = tmp_path / "windows.sqlite3"
    _, receipt = seed(path)
    first_request = sale_command(receipt, fulfilled_outbound_quantity=max(0, receipt.sellable_quantity - 2))
    with SQLiteActualSaleSettlementRepository(path) as repository:
        sale_owner(repository, first_request).execute(first_request)
        overlap = sale_command(receipt, command_id="overlap", external_report_reference="report-overlap", transaction_references=("order-overlap",))
        with pytest.raises(ActualSaleSettlementWindowConflictError):
            sale_owner(repository, overlap, identity="overlap-id").execute(overlap)
        second = sale_command(
            receipt, command_id="second", external_report_reference="report-2",
            transaction_references=("order-2",), period_start=first_request.period_end,
            period_end=first_request.period_end + timedelta(days=1),
            requested_at=first_request.period_end + timedelta(days=1, minutes=1),
            finality=replace(first_request.finality, observed_at=first_request.period_end + timedelta(days=1)),
            fulfilled_outbound_quantity=2,
        )
        assert sale_owner(repository, second, identity="second-id").execute(second).settlement.state is ActualSaleSettlementState.COMPLETE
        third = replace(
            second, command_id="third", external_report_reference="report-3",
            transaction_references=("order-3",), period_start=second.period_end,
            period_end=second.period_end + timedelta(days=1),
            requested_at=second.period_end + timedelta(days=1, minutes=1),
            finality=replace(second.finality, observed_at=second.period_end + timedelta(days=1)),
            fulfilled_outbound_quantity=1,
        )
        with pytest.raises(ActualSaleSettlementOversellConflictError):
            sale_owner(repository, third, identity="third-id").execute(third)


def test_concurrent_windows_cannot_jointly_oversell(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    _, receipt = seed(path)
    existing_quantity = max(0, receipt.sellable_quantity - 2)
    base = sale_command(receipt, fulfilled_outbound_quantity=existing_quantity)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        sale_owner(repository, base).execute(base)
    barrier = Barrier(2)

    def execute(index):
        start = base.period_end + timedelta(days=index)
        request = sale_command(
            receipt, command_id=f"concurrent-{index}", external_report_reference=f"report-{index}",
            transaction_references=(f"concurrent-order-{index}",), period_start=start,
            period_end=start + timedelta(days=1), requested_at=start + timedelta(days=1, minutes=1),
            finality=replace(base.finality, observed_at=start + timedelta(days=1)),
            fulfilled_outbound_quantity=2,
        )
        with SQLiteActualSaleSettlementRepository(path) as repository:
            barrier.wait()
            try:
                return sale_owner(repository, request, identity=f"settlement-{index}").execute(request).settlement.state
            except ActualSaleSettlementOversellConflictError:
                return "oversell"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(execute, (0, 1)))
    assert outcomes.count(ActualSaleSettlementState.COMPLETE) == 1
    assert outcomes.count("oversell") == 1


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "concurrent-replay.sqlite3"
    _, receipt = seed(path)
    request = sale_command(receipt)
    barrier = Barrier(2)

    def execute(identity):
        with SQLiteActualSaleSettlementRepository(path) as repository:
            barrier.wait()
            return sale_owner(repository, request, identity=identity).execute(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(execute, ("settlement-a", "settlement-b")))
    assert {value.settlement.settlement_id for value in outcomes} in (
        {"settlement-a"}, {"settlement-b"}
    )
    assert sorted(value.replayed for value in outcomes) == [False, True]
    with SQLiteActualSaleSettlementRepository(path) as repository:
        changed = replace(request, fulfilled_outbound_quantity=0)
        with pytest.raises(ActualSaleSettlementReplayConflictError):
            sale_owner(repository, changed, identity="unused").execute(changed)


def test_concurrent_competing_first_revisions_and_duplicate_references_are_rejected(tmp_path):
    path = tmp_path / "concurrent-cardinality.sqlite3"
    _, receipt = seed(path)
    base = sale_command(receipt)
    requests = (
        replace(base, command_id="first-a", transaction_references=("order-a",)),
        replace(base, command_id="first-b", transaction_references=("order-b",)),
    )
    barrier = Barrier(2)

    def execute(pair):
        index, request = pair
        with SQLiteActualSaleSettlementRepository(path) as repository:
            barrier.wait()
            try:
                return sale_owner(repository, request, identity=f"first-{index}").execute(request).settlement
            except (ActualSaleSettlementRevisionConflictError, ActualSaleSettlementTerminalConflictError):
                return "revision"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(execute, enumerate(requests)))
    assert sum(value != "revision" for value in outcomes) == 1
    assert outcomes.count("revision") == 1

    winner = next(value for value in outcomes if value != "revision")
    with SQLiteActualSaleSettlementRepository(path) as repository:
        duplicate_report = replace(
            base,
            command_id="duplicate-report",
            predecessor_settlement_id=winner.settlement_id,
        )
        with pytest.raises(ActualSaleSettlementTerminalConflictError):
            sale_owner(repository, duplicate_report, identity="duplicate-report-id").execute(duplicate_report)


def test_concurrent_children_do_not_fork_and_overlapping_complete_windows_do_not_both_commit(tmp_path):
    from app.domain.capital import ActualSaleMonetaryCategory
    from test_actual_sale_settlement import complete_facts, unknown

    path = tmp_path / "concurrent-children.sqlite3"
    _, receipt = seed(path)
    blocked_facts = list(complete_facts())
    blocked_facts[5] = unknown(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
    blocked_request = sale_command(receipt, fixed_monetary_facts=tuple(blocked_facts))
    with SQLiteActualSaleSettlementRepository(path) as repository:
        blocked = sale_owner(repository, blocked_request).execute(blocked_request).settlement
    children = tuple(
        sale_command(
            receipt,
            command_id=f"child-{index}",
            predecessor_settlement_id=blocked.settlement_id,
            transaction_references=(f"child-order-{index}",),
        )
        for index in range(2)
    )
    barrier = Barrier(2)

    def execute_child(pair):
        index, request = pair
        with SQLiteActualSaleSettlementRepository(path) as repository:
            barrier.wait()
            try:
                return sale_owner(repository, request, identity=f"child-id-{index}").execute(request).settlement.state
            except (ActualSaleSettlementRevisionConflictError, ActualSaleSettlementTerminalConflictError):
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        child_outcomes = tuple(executor.map(execute_child, enumerate(children)))
    assert child_outcomes.count(ActualSaleSettlementState.COMPLETE) == 1
    assert child_outcomes.count("conflict") == 1

    overlap_path = tmp_path / "concurrent-overlap.sqlite3"
    _, overlap_receipt = seed(overlap_path)
    base = sale_command(overlap_receipt, fulfilled_outbound_quantity=1)
    overlaps = (
        replace(base, command_id="overlap-a", external_report_reference="overlap-report-a", transaction_references=("overlap-order-a",)),
        replace(base, command_id="overlap-b", external_report_reference="overlap-report-b", transaction_references=("overlap-order-b",)),
    )
    overlap_barrier = Barrier(2)

    def execute_overlap(pair):
        index, request = pair
        with SQLiteActualSaleSettlementRepository(overlap_path) as repository:
            overlap_barrier.wait()
            try:
                return sale_owner(repository, request, identity=f"overlap-id-{index}").execute(request).settlement.state
            except ActualSaleSettlementWindowConflictError:
                return "overlap"

    with ThreadPoolExecutor(max_workers=2) as executor:
        overlap_outcomes = tuple(executor.map(execute_overlap, enumerate(overlaps)))
    assert overlap_outcomes.count(ActualSaleSettlementState.COMPLETE) == 1
    assert overlap_outcomes.count("overlap") == 1


def test_concurrent_valid_windows_both_commit_and_duplicate_transaction_is_rejected(tmp_path):
    path = tmp_path / "concurrent-valid.sqlite3"
    _, receipt = seed(path)
    base = sale_command(receipt, fulfilled_outbound_quantity=1)
    requests = []
    for index in range(2):
        start = base.period_start + timedelta(days=index)
        requests.append(replace(
            base,
            command_id=f"valid-{index}",
            external_report_reference=f"valid-report-{index}",
            transaction_references=(f"valid-order-{index}",),
            period_start=start,
            period_end=start + timedelta(days=1),
            requested_at=start + timedelta(days=1, minutes=1),
            finality=replace(base.finality, observed_at=start + timedelta(days=1)),
        ))
    barrier = Barrier(2)

    def execute(pair):
        index, request = pair
        with SQLiteActualSaleSettlementRepository(path) as repository:
            barrier.wait()
            return sale_owner(repository, request, identity=f"valid-id-{index}").execute(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(execute, enumerate(requests)))
    assert all(value.settlement.state is ActualSaleSettlementState.COMPLETE for value in outcomes)

    third_start = requests[-1].period_end
    duplicate_transaction = replace(
        base,
        command_id="duplicate-transaction",
        external_report_reference="valid-report-2",
        transaction_references=("valid-order-0",),
        period_start=third_start,
        period_end=third_start + timedelta(days=1),
        requested_at=third_start + timedelta(days=1, minutes=1),
        finality=replace(base.finality, observed_at=third_start + timedelta(days=1)),
    )
    with SQLiteActualSaleSettlementRepository(path) as repository:
        with pytest.raises(ActualSaleSettlementReportConflictError):
            sale_owner(repository, duplicate_transaction, identity="duplicate-transaction-id").execute(duplicate_transaction)


def test_malformed_fingerprint_and_orphan_receipt_fail_closed(tmp_path):
    path = tmp_path / "malformed.sqlite3"
    _, receipt = seed(path)
    request = sale_command(receipt)
    with SQLiteActualSaleSettlementRepository(path) as repository:
        result = sale_owner(repository, request).execute(request)
        repository._connection.execute("DROP TRIGGER trg_actual_sale_settlement_history_no_update")
        repository._connection.execute(f"UPDATE {HISTORY} SET integrity_fingerprint='bad' WHERE settlement_id=?", (result.settlement.settlement_id,))
        repository._connection.commit()
        with pytest.raises(MalformedActualSaleSettlementPersistenceError):
            repository.get_settlement(result.settlement.settlement_id)

    path2 = tmp_path / "orphan.sqlite3"
    _, receipt2 = seed(path2)
    request2 = sale_command(receipt2)
    with SQLiteActualSaleSettlementRepository(path2) as repository:
        result2 = sale_owner(repository, request2).execute(request2)
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute("DROP TRIGGER trg_actual_sale_settlement_history_no_delete")
        repository._connection.execute(f"DELETE FROM {HISTORY} WHERE settlement_id=?", (result2.settlement.settlement_id,))
        repository._connection.commit()
        with pytest.raises(MalformedActualSaleSettlementPersistenceError):
            repository.validate_replay(request2.command_id, request2.fingerprint)
