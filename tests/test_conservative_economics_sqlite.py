from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.conservative_economics import (
    ConservativeEconomicsReplayConflictError,
    EvaluateConservativeEconomics,
)
from app.application.economics_source_composition import ComposeEconomicsSources
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.infrastructure.conservative_economics import (
    ConservativeEconomicsCommitError,
    ConservativeEconomicsHistoryError,
    ConservativeEconomicsReceiptError,
    MalformedConservativeEconomicsPersistenceError,
    SQLiteConservativeEconomicsRepository,
)
from app.infrastructure.economics_source_composition import (
    SQLiteEconomicsSourceCompositionRepository,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.sourcing import SQLiteAcquisitionCostNormalizationRepository
from test_acquisition_cost_normalization import command as normalization_command
from test_acquisition_cost_normalization_sqlite import (
    owner as normalization_owner,
    seed_sources,
)
from test_conservative_economics import command, rate, verified_input
from test_economics_source_composition import Calls, command as source_command
from test_sourcing_authority_contract import NOW


HISTORY = "conservative_economics_history"
RECEIPTS = "conservative_economics_receipts"


def seed_source(path, verified=None):
    landed, authorities, observations = seed_sources(path)
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
            verified or verified_input(),
            NOW + timedelta(minutes=4),
        )
        repository._insert_verified_economics_snapshot(verified)
        repository._connection.commit()
    finally:
        repository.close()

    with SQLiteEconomicsSourceCompositionRepository(path) as source_repository:
        source = ComposeEconomicsSources(
            source_repository,
            composition_id_generator=lambda: "economics-source-composition-1",
            composed_clock=lambda: NOW + timedelta(minutes=5),
            committed_clock=lambda: NOW + timedelta(minutes=6),
        ).execute(source_command(normalization, verified)).composition
    return source


def owner(repository, identity="conservative-result-1"):
    identity_calls = Calls(identity)
    calculated = Calls(NOW + timedelta(minutes=30))
    committed = Calls(NOW + timedelta(minutes=31))
    return (
        EvaluateConservativeEconomics(
            repository,
            result_id_generator=identity_calls,
            calculated_clock=calculated,
            committed_clock=committed,
        ),
        identity_calls,
        calculated,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_round_trip_and_read_path_are_exact_and_pure(tmp_path):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        publication = owner(repository)[0].execute(command(source, factor="0.9"))
        before = repository._connection.total_changes
        assert repository.get_result(publication.result.result_id) == publication.result
        assert repository.get_receipt(publication.receipt.command_id) == publication.receipt
        assert repository._connection.total_changes == before
        assert counts(repository) == (1, 1)
        assert repository._connection.in_transaction is False


def test_restart_exact_replay_skips_identity_and_clocks(tmp_path):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    request = command(source, factor="0.9")
    with SQLiteConservativeEconomicsRepository(path) as repository:
        first = owner(repository)[0].execute(request)

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during restart replay")

    with SQLiteConservativeEconomicsRepository(path) as repository:
        replay = EvaluateConservativeEconomics(
            repository,
            result_id_generator=Never(),
            calculated_clock=Never(),
            committed_clock=Never(),
        ).execute(request)
        assert replay.replayed is True
        assert replay.result == first.result
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_blocked_result_round_trip_preserves_reasons_and_absent_profitability(tmp_path):
    path = tmp_path / "blocked.sqlite3"
    source = seed_source(
        path,
        verified_input(tax_rate=rate("0.01", "tax")),
    )
    with SQLiteConservativeEconomicsRepository(path) as repository:
        publication = owner(repository)[0].execute(command(source))
        restored = repository.get_result(publication.result.result_id)
        assert restored == publication.result
        assert restored.status.value == "blocked"
        assert restored.conservative_profit_per_unit is None
        assert restored.conservative_margin is None
        assert restored.conservative_acquisition_roi is None


def test_changed_scenario_or_source_conflicts_before_recalculation(tmp_path):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        boundary = owner(repository)[0]
        boundary.execute(command(source))
        with pytest.raises(ConservativeEconomicsReplayConflictError):
            boundary.execute(command(source, factor="0.9"))
        with pytest.raises(ConservativeEconomicsReplayConflictError):
            boundary.execute(
                command(source, source_composition_id="different-source")
            )


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(tmp_path, table, operation):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        owner(repository)[0].execute(command(source))
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
        ("history", ConservativeEconomicsHistoryError),
        ("receipt", ConservativeEconomicsReceiptError),
        ("commit", ConservativeEconomicsCommitError),
    ],
)
def test_transaction_failures_roll_back_without_partial_state(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
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
            owner(repository)[0].execute(command(source))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_concurrent_same_command_converges(tmp_path):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    request = command(source)
    barrier = Barrier(2)

    def run(identity):
        with SQLiteConservativeEconomicsRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("result-a", "result-b")))
    assert len({value.result.result_id for value in results}) == 1


def test_concurrent_changed_payload_commits_one_and_conflicts_other(tmp_path):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    requests = (command(source), command(source, factor="0.9"))
    barrier = Barrier(2)

    def run(arguments):
        identity, request = arguments
        try:
            with SQLiteConservativeEconomicsRepository(path) as repository:
                barrier.wait()
                return owner(repository, identity)[0].execute(request)
        except ConservativeEconomicsReplayConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, zip(("result-a", "result-b"), requests)))
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert sum(isinstance(value, ConservativeEconomicsReplayConflictError) for value in results) == 1
    with SQLiteConservativeEconomicsRepository(path) as repository:
        assert counts(repository) == (1, 1)


def _tamper_status(payload):
    payload["status"] = "invalid"


def _tamper_profit(payload):
    payload["conservative_profit_per_unit"] = "999"


def _tamper_blocked_with_profit(payload):
    payload["status"] = "blocked"
    payload["blocking_reasons"] = [
        {"code": "source_composition_blocked", "category": "source", "source_reference": None}
    ]


def _tamper_source(payload):
    payload["source_composition_id"] = "missing-source"


def _tamper_opportunity(payload):
    payload["opportunity_identity"]["opportunity_id"] = "other"


def _tamper_assumption(payload):
    payload["assumptions"][0]["value"] = "1.1"


def _tamper_policy(payload):
    payload["policy_version"] = "2.0.0"


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_status,
        _tamper_profit,
        _tamper_blocked_with_profit,
        _tamper_source,
        _tamper_opportunity,
        _tamper_assumption,
        _tamper_policy,
    ],
)
def test_malformed_persistence_is_rejected(tmp_path, tamper):
    path = tmp_path / "conservative.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        publication = owner(repository)[0].execute(command(source))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        encoded = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE result_id=?",
            (publication.result.result_id,),
        ).fetchone()[0]
        payload = json.loads(encoded)
        tamper(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest()),
        )
        repository._connection.commit()
        with pytest.raises(MalformedConservativeEconomicsPersistenceError):
            repository.get_result(publication.result.result_id)


def test_fingerprint_mismatch_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "fingerprint.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        publication = owner(repository)[0].execute(command(source))
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint=?", ("0" * 64,)
        )
        repository._connection.commit()
        with pytest.raises(MalformedConservativeEconomicsPersistenceError):
            repository.get_result(publication.result.result_id)

    path = tmp_path / "orphan.sqlite3"
    source = seed_source(path)
    with SQLiteConservativeEconomicsRepository(path) as repository:
        publication = owner(repository)[0].execute(command(source))
        repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"UPDATE {RECEIPTS} SET result_id='missing-result'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedConservativeEconomicsPersistenceError):
            repository.get_receipt(publication.receipt.command_id)
