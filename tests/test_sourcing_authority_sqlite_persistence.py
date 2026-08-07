from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
import sqlite3
from threading import Barrier

import pytest

from app.application.sourcing import (
    AdmitFounderSourcing,
    ReviseFounderSourcingQuote,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionReplayConflictError,
    SourcingQuoteRevisionConflictError,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    SourcingMoneyFact,
    SourcingQuantityFact,
)
from app.infrastructure.sourcing import (
    MalformedSourcingAuthorityPersistenceError,
    SQLiteSourcingAuthorityRepository,
    SourcingAdmissionHistoryError,
    SourcingAuthorityCommitError,
    SourcingMatchHistoryError,
    SourcingQuoteHistoryError,
    SourcingReceiptHistoryError,
    SourcingSupplierHistoryError,
    SourcingProductHistoryError,
)
from test_sourcing_authority_contract import NOW, command, evidence


TABLES = (
    "sourcing_supplier_history",
    "sourcing_product_history",
    "sourcing_match_verification_history",
    "sourcing_quote_revision_history",
    "founder_sourcing_admission_history",
    "sourcing_admission_receipts",
)


def boundary(repository, *, fail=False):
    def value(name):
        if fail:
            return lambda: pytest.fail(f"{name} called during replay")
        return lambda: name

    return AdmitFounderSourcing(
        repository,
        supplier_id_generator=value("supplier-1"),
        sourcing_product_id_generator=value("sourcing-product-1"),
        quote_id_generator=value("quote-1"),
        match_verification_id_generator=value("match-1"),
        admission_id_generator=value("admission-1"),
        committed_clock=(
            (lambda: pytest.fail("clock called during replay"))
            if fail else (lambda: NOW)
        ),
    )


def revision_command(first, *, command_id="revision-command-1", price="11.90"):
    return ReviseFounderSourcingQuoteCommand(
        command_id=command_id,
        admission_id=first.admission_id,
        expected_revision=first.revision,
        quoted_unit_price=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal(price), "CNY"
        ),
        minimum_order_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 20
        ),
        quoted_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 200
        ),
        shipping_terms=first.quote_revision.shipping_terms,
        lead_time_availability=CommercialFactAvailability.UNKNOWN,
        lead_time_days=None,
        quote_observed_at=NOW,
        quote_valid_until=None,
        quote_evidence=evidence(),
        operator_id="founder-1",
        requested_at=NOW,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in TABLES
    )


def state(repository):
    return tuple(
        (
            table,
            tuple(tuple(row) for row in repository._connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            )),
        )
        for table in TABLES
    )


def test_schema_fresh_admission_and_exact_reconstruction(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "sourcing.db")
    result = boundary(repository).execute(command())
    assert counts(repository) == (1, 1, 1, 1, 1, 1)
    assert repository.get_admission(result.admission.admission_id) == result.admission
    assert repository.get_admission_revision(result.admission.admission_id, 1) == result.admission
    assert repository.get_receipt(result.receipt.command_id) == result.receipt
    assert result.admission.selling_product_lineage == command().selling_product_lineage
    assert result.admission.quote_revision.evidence == command().quote_evidence
    assert result.admission.match_verification.evidence == command().match_evidence
    repository.close()


def test_unknown_shipping_round_trip_never_becomes_zero(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "unknown.db")
    saved = boundary(repository).execute(command()).admission
    restored = repository.get_admission(saved.admission_id)
    unknown = restored.quote_revision.shipping_terms[1].cost
    assert unknown.availability is CommercialFactAvailability.UNKNOWN
    assert unknown.amount is None and unknown.currency is None
    repository.close()


def test_exact_replay_and_restart_replay_do_not_append_or_call_suppliers(tmp_path):
    path = tmp_path / "replay.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    first = boundary(repository).execute(command())
    before = state(repository)
    replay = boundary(repository, fail=True).execute(command())
    assert replay.admission == first.admission and replay.replayed
    assert state(repository) == before
    repository.close()
    restarted = SQLiteSourcingAuthorityRepository(path)
    replay = boundary(restarted, fail=True).execute(command())
    assert replay.admission == first.admission and replay.receipt == first.receipt
    assert state(restarted) == before
    restarted.close()


def test_changed_command_payload_conflicts_without_rows(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "conflict.db")
    boundary(repository).execute(command())
    before = state(repository)
    changed = command(quoted_quantity=SourcingQuantityFact(
        CommercialFactAvailability.KNOWN, 999
    ))
    with pytest.raises(SourcingAdmissionReplayConflictError):
        boundary(repository, fail=True).execute(changed)
    assert state(repository) == before
    repository.close()


def test_quote_revision_appends_and_prior_revision_is_exact(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "revision.db")
    first = boundary(repository).execute(command()).admission
    revised = ReviseFounderSourcingQuote(
        repository, committed_clock=lambda: NOW
    ).execute(revision_command(first)).admission
    assert counts(repository) == (1, 1, 1, 2, 2, 2)
    assert revised.revision == 2
    assert revised.quote_revision.quote_id == first.quote_revision.quote_id
    assert repository.get_admission_revision(first.admission_id, 1) == first
    assert repository.get_admission_revision(first.admission_id, 2) == revised
    assert repository.get_admission(first.admission_id) == revised
    repository.close()


def test_quote_revision_restart_replay_and_stale_revision_conflict(tmp_path):
    path = tmp_path / "revision-replay.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    first = boundary(repository).execute(command()).admission
    revision = revision_command(first)
    saved = ReviseFounderSourcingQuote(repository, committed_clock=lambda: NOW).execute(revision)
    repository.close()
    restarted = SQLiteSourcingAuthorityRepository(path)
    replay = ReviseFounderSourcingQuote(
        restarted, committed_clock=lambda: pytest.fail("clock called")
    ).execute(revision)
    assert replay == replace(saved, replayed=True)
    with pytest.raises(SourcingQuoteRevisionConflictError):
        ReviseFounderSourcingQuote(restarted, committed_clock=lambda: NOW).execute(
            replace(revision, command_id="other", expected_revision=1)
        )
    assert counts(restarted) == (1, 1, 1, 2, 2, 2)
    restarted.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (
        ("supplier", SourcingSupplierHistoryError),
        ("product", SourcingProductHistoryError),
        ("match", SourcingMatchHistoryError),
        ("quote", SourcingQuoteHistoryError),
        ("admission", SourcingAdmissionHistoryError),
        ("receipt", SourcingReceiptHistoryError),
        ("commit", SourcingAuthorityCommitError),
    ),
)
def test_fresh_admission_atomic_failure_matrix(tmp_path, stage, error_type):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / f"{stage}.db")
    hook = {
        "supplier": "_insert_supplier", "product": "_insert_product",
        "match": "_insert_match", "quote": "_insert_quote",
        "admission": "_insert_admission", "receipt": "_insert_receipt",
        "commit": "_commit",
    }[stage]
    setattr(repository, hook, lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError(stage)))
    with pytest.raises(error_type):
        boundary(repository).execute(command())
    assert counts(repository) == (0, 0, 0, 0, 0, 0)
    assert repository._connection.in_transaction is False
    repository.close()


@pytest.mark.parametrize(
    ("stage", "error_type"),
    (
        ("quote", SourcingQuoteHistoryError),
        ("admission", SourcingAdmissionHistoryError),
        ("receipt", SourcingReceiptHistoryError),
        ("commit", SourcingAuthorityCommitError),
    ),
)
def test_quote_revision_atomic_failure_preserves_previous_current(tmp_path, stage, error_type):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / f"revision-{stage}.db")
    first = boundary(repository).execute(command()).admission
    before = state(repository)
    hook = {
        "quote": "_insert_quote", "admission": "_insert_admission",
        "receipt": "_insert_receipt", "commit": "_commit",
    }[stage]
    setattr(repository, hook, lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError(stage)))
    with pytest.raises(error_type):
        ReviseFounderSourcingQuote(repository, committed_clock=lambda: NOW).execute(
            revision_command(first)
        )
    assert state(repository) == before
    assert repository.get_admission(first.admission_id) == first
    assert repository._connection.in_transaction is False
    repository.close()


def test_append_only_triggers_reject_update_and_delete(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "append.db")
    first = boundary(repository).execute(command()).admission
    ReviseFounderSourcingQuote(repository, committed_clock=lambda: NOW).execute(
        revision_command(first)
    )
    for table in TABLES:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(f"UPDATE {table} SET rowid=rowid")
        repository._connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()
    repository.close()


def test_malformed_quote_and_broken_reference_fail_explicitly(tmp_path):
    repository = SQLiteSourcingAuthorityRepository(tmp_path / "malformed.db")
    admission = boundary(repository).execute(command()).admission
    repository._connection.execute("DROP TRIGGER trg_sourcing_quote_revision_history_no_update")
    repository._connection.execute(
        "UPDATE sourcing_quote_revision_history SET payload_json='{}' WHERE quote_id=? AND revision=1",
        (admission.quote_revision.quote_id,),
    )
    repository._connection.commit()
    with pytest.raises(MalformedSourcingAuthorityPersistenceError):
        repository.get_admission(admission.admission_id)
    repository.close()


def test_read_paths_are_deterministic_read_only_and_close_is_clean(tmp_path):
    path = tmp_path / "read.db"
    repository = SQLiteSourcingAuthorityRepository(path)
    saved = boundary(repository).execute(command())
    before = state(repository)
    for _ in range(2):
        assert repository.get_admission(saved.admission.admission_id) == saved.admission
        assert repository.get_admission_revision(saved.admission.admission_id, 1) == saved.admission
        assert repository.get_receipt(saved.receipt.command_id) == saved.receipt
        assert repository.validate_replay(command().command_id, command().fingerprint).admission == saved.admission
    assert state(repository) == before
    assert repository._connection.in_transaction is False
    repository.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")


def test_concurrent_same_admission_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "admission-race.db"
    barrier = Barrier(2)

    def execute(value):
        repository = SQLiteSourcingAuthorityRepository(path)
        try:
            barrier.wait()
            return boundary(repository).execute(value)
        except SourcingAdmissionReplayConflictError:
            return "conflict"
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(execute, (command(), command())))
    assert sum(value.replayed for value in same) == 1
    with SQLiteSourcingAuthorityRepository(path) as repository:
        assert counts(repository) == (1, 1, 1, 1, 1, 1)

    changed_path = tmp_path / "admission-conflict-race.db"
    barrier = Barrier(2)
    original = command()
    changed = command(quoted_quantity=SourcingQuantityFact(
        CommercialFactAvailability.KNOWN, 999
    ))

    def changed_execute(value):
        repository = SQLiteSourcingAuthorityRepository(changed_path)
        try:
            barrier.wait()
            return boundary(repository).execute(value)
        except SourcingAdmissionReplayConflictError:
            return "conflict"
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(changed_execute, (original, changed)))
    assert sum(value == "conflict" for value in outcomes) == 1
    with SQLiteSourcingAuthorityRepository(changed_path) as repository:
        assert counts(repository) == (1, 1, 1, 1, 1, 1)


def test_concurrent_quote_revision_converges_or_conflicts(tmp_path):
    path = tmp_path / "revision-race.db"
    with SQLiteSourcingAuthorityRepository(path) as repository:
        first = boundary(repository).execute(command()).admission
    same = revision_command(first)
    barrier = Barrier(2)

    def execute(value):
        repository = SQLiteSourcingAuthorityRepository(path)
        try:
            barrier.wait()
            return ReviseFounderSourcingQuote(
                repository, committed_clock=lambda: NOW
            ).execute(value)
        except (SourcingAdmissionReplayConflictError, SourcingQuoteRevisionConflictError):
            return "conflict"
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(execute, (same, same)))
    assert sum(value.replayed for value in outcomes) == 1
    with SQLiteSourcingAuthorityRepository(path) as repository:
        assert counts(repository) == (1, 1, 1, 2, 2, 2)

    conflict_path = tmp_path / "revision-conflict-race.db"
    with SQLiteSourcingAuthorityRepository(conflict_path) as repository:
        first = boundary(repository).execute(command()).admission
    left = revision_command(first, price="11.90")
    right = revision_command(first, price="10.90")
    barrier = Barrier(2)

    def conflict_execute(value):
        repository = SQLiteSourcingAuthorityRepository(conflict_path)
        try:
            barrier.wait()
            return ReviseFounderSourcingQuote(repository, committed_clock=lambda: NOW).execute(value)
        except (SourcingAdmissionReplayConflictError, SourcingQuoteRevisionConflictError):
            return "conflict"
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(conflict_execute, (left, right)))
    assert sum(value == "conflict" for value in outcomes) == 1
    with SQLiteSourcingAuthorityRepository(conflict_path) as repository:
        assert counts(repository) == (1, 1, 1, 2, 2, 2)
