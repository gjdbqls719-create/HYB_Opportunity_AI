from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.economics_source_composition import (
    ComposeEconomicsSources,
    EconomicsSourceCompositionReplayConflictError,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.infrastructure.economics_source_composition import (
    EconomicsSourceCompositionCommitError,
    EconomicsSourceCompositionHistoryError,
    EconomicsSourceCompositionReceiptError,
    MalformedEconomicsSourceCompositionPersistenceError,
    SQLiteEconomicsSourceCompositionRepository,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.sourcing import SQLiteAcquisitionCostNormalizationRepository
from test_acquisition_cost_normalization_sqlite import (
    owner as normalization_owner,
    seed_sources,
)
from test_economics_source_composition import Calls, command, economics
from test_sourcing_authority_contract import NOW


HISTORY = "economics_source_composition_history"
RECEIPTS = "economics_source_composition_receipts"


def seed_exact_sources(path):
    landed, authorities, observations = seed_sources(path)
    from test_acquisition_cost_normalization import command as normalization_command

    request = normalization_command(landed, authorities, observations)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        normalization = normalization_owner(repository)[0].execute(request).normalization

    repository = SQLiteValidationQueueRepository(path)
    try:
        repository._connection.execute(
            """INSERT INTO opportunity_lifecycles(
                opportunity_id,discovery_reference,status,version,
                created_at,updated_at,archived_at,archived_by,archive_reason
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                normalization.opportunity_identity.opportunity_id,
                normalization.opportunity_identity.discovery_reference,
                "discovered",
                1,
                NOW.isoformat(),
                NOW.isoformat(),
                None,
                None,
                None,
            ),
        )
        verified = VerifiedEconomicsSnapshot(
            normalization.opportunity_identity.opportunity_id,
            economics(),
            NOW + timedelta(minutes=4),
        )
        repository._insert_verified_economics_snapshot(verified)
        repository._connection.commit()
    finally:
        repository.close()
    return normalization, verified


def owner(repository, identity="economics-source-composition-1"):
    identity_calls = Calls(identity)
    composed = Calls(NOW + timedelta(minutes=20))
    committed = Calls(NOW + timedelta(minutes=21))
    return (
        ComposeEconomicsSources(
            repository,
            composition_id_generator=identity_calls,
            composed_clock=composed,
            committed_clock=committed,
        ),
        identity_calls,
        composed,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_round_trip_exact_sources_and_read_path_are_pure(tmp_path):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        result = owner(repository)[0].execute(command(normalization, verified))
        before = repository._connection.total_changes
        assert repository.get_composition(result.composition.composition_id) == result.composition
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert repository._connection.total_changes == before
        assert counts(repository) == (1, 1)
        assert repository._connection.in_transaction is False


def test_restart_exact_replay_skips_identity_and_clocks(tmp_path):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    request = command(normalization, verified)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        first = owner(repository)[0].execute(request)

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during restart replay")

    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        replay = ComposeEconomicsSources(
            repository,
            composition_id_generator=Never(),
            composed_clock=Never(),
            committed_clock=Never(),
        ).execute(request)
        assert replay.replayed is True
        assert replay.composition == first.composition
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_same_command_changed_exact_source_conflicts(tmp_path):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        boundary = owner(repository)[0]
        boundary.execute(command(normalization, verified))
        with pytest.raises(EconomicsSourceCompositionReplayConflictError):
            boundary.execute(
                command(
                    normalization,
                    verified,
                    verified_economics_snapshot_at=verified.snapshot_at
                    + timedelta(seconds=1),
                )
            )


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(tmp_path, table, operation):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        owner(repository)[0].execute(command(normalization, verified))
        statement = (
            f"DELETE FROM {table}"
            if operation == "DELETE"
            else f"UPDATE {table} SET inserted_at=inserted_at"
        )
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(statement)
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        ("history", EconomicsSourceCompositionHistoryError),
        ("receipt", EconomicsSourceCompositionReceiptError),
        ("commit", EconomicsSourceCompositionCommitError),
    ],
)
def test_transaction_failures_roll_back_without_partial_state(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
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
            owner(repository)[0].execute(command(normalization, verified))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_concurrent_same_command_converges(tmp_path):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    request = command(normalization, verified)
    barrier = Barrier(2)

    def run(identity):
        with SQLiteEconomicsSourceCompositionRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("composition-a", "composition-b")))
    assert len({result.composition.composition_id for result in results}) == 1


def test_concurrent_changed_payload_commits_one_and_conflicts_other(tmp_path):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    requests = (
        command(normalization, verified),
        command(
            normalization,
            verified,
            requested_at=NOW + timedelta(seconds=1),
        ),
    )
    barrier = Barrier(2)

    def run(arguments):
        identity, request = arguments
        try:
            with SQLiteEconomicsSourceCompositionRepository(path) as repository:
                barrier.wait()
                return owner(repository, identity)[0].execute(request)
        except EconomicsSourceCompositionReplayConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, zip(("composition-a", "composition-b"), requests)))
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert sum(
        isinstance(value, EconomicsSourceCompositionReplayConflictError)
        for value in results
    ) == 1
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        assert counts(repository) == (1, 1)


def _tamper_state(payload):
    payload["state"] = "invalid"


def _tamper_currency(payload):
    payload["economics_currency"] = "INVALID"


def _tamper_normalization(payload):
    payload["acquisition_normalization_id"] = "missing-normalization"


def _tamper_opportunity(payload):
    payload["opportunity_identity"]["opportunity_id"] = "other"


def _tamper_evidence(payload):
    payload["expected_sale_price"]["evidence"]["status"] = "invalid"


def _tamper_duplicate_source(payload):
    payload["purchase_cost"] = payload["expected_sale_price"]


def _tamper_policy(payload):
    payload["policy_version"] = "2.0.0"


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_state,
        _tamper_currency,
        _tamper_normalization,
        _tamper_opportunity,
        _tamper_evidence,
        _tamper_duplicate_source,
        _tamper_policy,
    ],
)
def test_malformed_persistence_is_rejected(tmp_path, tamper):
    path = tmp_path / "economics-source.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        result = owner(repository)[0].execute(command(normalization, verified))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE composition_id=?",
            (result.composition.composition_id,),
        ).fetchone()
        payload = json.loads(row[0])
        tamper(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest()),
        )
        repository._connection.commit()
        with pytest.raises(MalformedEconomicsSourceCompositionPersistenceError):
            repository.get_composition(result.composition.composition_id)


def test_fingerprint_mismatch_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "fingerprint.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        result = owner(repository)[0].execute(command(normalization, verified))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint=?", ("0" * 64,)
        )
        repository._connection.commit()
        with pytest.raises(MalformedEconomicsSourceCompositionPersistenceError):
            repository.get_composition(result.composition.composition_id)

    path = tmp_path / "orphan.sqlite3"
    normalization, verified = seed_exact_sources(path)
    with SQLiteEconomicsSourceCompositionRepository(path) as repository:
        result = owner(repository)[0].execute(command(normalization, verified))
        repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"UPDATE {RECEIPTS} SET composition_id='missing-composition'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedEconomicsSourceCompositionPersistenceError):
            repository.get_receipt(result.receipt.command_id)
