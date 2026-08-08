from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app.application.domestic_market_validation import (
    DomesticMarketValidationReplayConflictError,
    ValidateDomesticMarketForCapital,
)
from app.infrastructure.domestic_market_validation import (
    DomesticMarketValidationCommitError,
    DomesticMarketValidationHistoryError,
    DomesticMarketValidationReceiptError,
    MalformedDomesticMarketValidationPersistenceError,
    SQLiteDomesticMarketValidationRepository,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from test_domestic_market_validation import (
    Counter,
    NOW,
    command,
    competition,
    competition_snapshot,
    demand,
    demand_snapshot,
    identity,
    verification,
)
from test_opportunity_market_identity_binding import command as admission_command
from test_opportunity_market_identity_binding import service as admission_service


def seed(database: Path) -> None:
    opportunities = SQLiteValidationQueueRepository(database)
    market = SQLiteMarketObservationRepository(database)
    identity_value = identity()
    base = admission_command(identity_value)
    base = replace(
        base,
        opportunity_id="opportunity-1",
        discovery_reference="discovery:1",
    )
    admission_service(opportunities).add(base)
    comp = competition(identity_value)
    dem = demand(identity_value)
    market.save_assessment_snapshot(comp, competition_snapshot(comp))
    market.save_assessment_snapshot(dem, demand_snapshot(dem))
    market.close()
    opportunities.close()


def evaluator(repository, *, result_id="validation-assessment-1"):
    return ValidateDomesticMarketForCapital(
        repository,
        assessment_id_generator=Counter(result_id),
        evaluated_clock=Counter(NOW.replace(minute=11)),
        committed_clock=Counter(NOW.replace(minute=12)),
    )


def counts(repository):
    connection = repository._connection
    return (
        connection.execute("SELECT COUNT(*) FROM domestic_market_validation_history").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM domestic_market_validation_receipts").fetchone()[0],
    )


def test_round_trip_restart_replay_and_read_path_no_mutation(tmp_path: Path) -> None:
    database = tmp_path / "validation.db"
    seed(database)
    repository = SQLiteDomesticMarketValidationRepository(database)
    first = evaluator(repository).execute(command())
    before_changes = repository._connection.total_changes
    assert repository.get_assessment(first.assessment.assessment_id) == first.assessment
    assert repository.get_receipt(command().command_id) == first.receipt
    assert repository._connection.total_changes == before_changes
    repository.close()

    restarted = SQLiteDomesticMarketValidationRepository(database)
    replay = evaluator(restarted, result_id="must-not-win").execute(command())
    assert replay.replayed is True
    assert replay.assessment == first.assessment
    assert replay.receipt == first.receipt
    assert counts(restarted) == (1, 1)
    restarted.close()


@pytest.mark.parametrize("table", ("domestic_market_validation_history", "domestic_market_validation_receipts"))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_history_and_receipt_are_append_only(tmp_path: Path, table: str, operation: str) -> None:
    database = tmp_path / f"{table}-{operation}.db"
    seed(database)
    repository = SQLiteDomesticMarketValidationRepository(database)
    evaluator(repository).execute(command())
    statement = f"{operation} {table} SET payload_json='x'" if operation == "UPDATE" and table.endswith("history") else (
        f"{operation} {table} SET command_fingerprint='x'" if operation == "UPDATE" else f"{operation} FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute(statement)
    repository._connection.rollback()
    assert counts(repository) == (1, 1)
    repository.close()


@pytest.mark.parametrize(
    ("table", "expected"),
    (
        ("domestic_market_validation_history", DomesticMarketValidationHistoryError),
        ("domestic_market_validation_receipts", DomesticMarketValidationReceiptError),
    ),
)
def test_insert_failure_rolls_back_both_rows(tmp_path: Path, table: str, expected) -> None:
    database = tmp_path / f"rollback-{table}.db"
    seed(database)
    repository = SQLiteDomesticMarketValidationRepository(database)
    repository._connection.execute(
        f"CREATE TRIGGER fail_insert BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'forced'); END"
    )
    with pytest.raises(expected):
        evaluator(repository).execute(command())
    assert counts(repository) == (0, 0)
    assert repository._connection.in_transaction is False
    repository.close()


def test_commit_failure_rolls_back_and_retry_is_possible(tmp_path: Path) -> None:
    database = tmp_path / "commit.db"
    seed(database)

    class FailingCommitRepository(SQLiteDomesticMarketValidationRepository):
        def _commit(self):
            raise sqlite3.OperationalError("forced commit failure")

    failing = FailingCommitRepository(database)
    with pytest.raises(DomesticMarketValidationCommitError):
        evaluator(failing).execute(command())
    assert counts(failing) == (0, 0)
    assert failing._connection.in_transaction is False
    failing.close()

    retry = SQLiteDomesticMarketValidationRepository(database)
    assert evaluator(retry).execute(command()).replayed is False
    retry.close()


def test_concurrent_same_command_converges(tmp_path: Path) -> None:
    database = tmp_path / "converge.db"
    seed(database)

    def run(suffix):
        repository = SQLiteDomesticMarketValidationRepository(database)
        try:
            return evaluator(repository, result_id=f"assessment-{suffix}").execute(command())
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, ("one", "two")))
    assert len({value.assessment.assessment_id for value in results}) == 1
    repository = SQLiteDomesticMarketValidationRepository(database)
    assert counts(repository) == (1, 1)
    repository.close()


def test_concurrent_changed_payload_has_one_commit_and_one_conflict(tmp_path: Path) -> None:
    database = tmp_path / "conflict.db"
    seed(database)

    def run(operator):
        repository = SQLiteDomesticMarketValidationRepository(database)
        try:
            changed = command(verification_value=replace(verification(), operator_id=operator))
            return evaluator(repository, result_id=f"assessment-{operator}").execute(changed)
        finally:
            repository.close()

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, value) for value in ("one", "two")]
        for future in futures:
            try:
                outcomes.append(future.result())
            except DomesticMarketValidationReplayConflictError:
                outcomes.append("conflict")
    assert sum(value == "conflict" for value in outcomes) == 1
    repository = SQLiteDomesticMarketValidationRepository(database)
    assert counts(repository) == (1, 1)
    repository.close()


def test_malformed_payload_fingerprint_and_orphan_receipt_are_rejected(tmp_path: Path) -> None:
    database = tmp_path / "malformed.db"
    seed(database)
    repository = SQLiteDomesticMarketValidationRepository(database)
    result = evaluator(repository).execute(command())
    repository.close()

    raw = sqlite3.connect(database)
    raw.execute("DROP TRIGGER trg_domestic_market_validation_history_no_update")
    raw.execute(
        "UPDATE domestic_market_validation_history SET integrity_fingerprint=? WHERE assessment_id=?",
        ("0" * 64, result.assessment.assessment_id),
    )
    raw.commit()
    raw.close()
    repository = SQLiteDomesticMarketValidationRepository(database)
    with pytest.raises(MalformedDomesticMarketValidationPersistenceError):
        repository.get_assessment(result.assessment.assessment_id)
    repository.close()

    orphan = tmp_path / "orphan.db"
    repository = SQLiteDomesticMarketValidationRepository(orphan)
    repository.close()
    raw = sqlite3.connect(orphan)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "INSERT INTO domestic_market_validation_receipts(command_id,assessment_id,command_fingerprint,committed_at,schema_version,inserted_at) VALUES(?,?,?,?,?,?)",
        ("orphan", "missing", "0" * 64, NOW.isoformat(), "domestic-market-validation-receipt-v1", NOW.isoformat()),
    )
    raw.commit()
    raw.close()
    repository = SQLiteDomesticMarketValidationRepository(orphan)
    with pytest.raises(MalformedDomesticMarketValidationPersistenceError):
        repository.get_receipt("orphan")
    repository.close()


@pytest.mark.parametrize(
    "case",
    (
        "corrupted_json",
        "invalid_state",
        "invalid_reason",
        "duplicate_reason",
        "wrong_reason_order",
        "unsupported_policy",
        "unsupported_schema",
        "corrupted_manifest",
        "missing_source_identity",
        "wrong_market_lineage",
        "malformed_verification",
        "unconfirmed_validated",
        "wrong_reviewed_sources",
        "invalid_timestamp",
        "validated_with_blocker",
    ),
)
def test_semantically_malformed_persistence_is_rejected(tmp_path: Path, case: str) -> None:
    database = tmp_path / f"malformed-{case}.db"
    seed(database)
    repository = SQLiteDomesticMarketValidationRepository(database)
    result = evaluator(repository).execute(command())
    repository.close()

    raw = sqlite3.connect(database)
    raw.execute("DROP TRIGGER trg_domestic_market_validation_history_no_update")
    encoded = raw.execute(
        "SELECT payload_json FROM domestic_market_validation_history WHERE assessment_id=?",
        (result.assessment.assessment_id,),
    ).fetchone()[0]
    payload = json.loads(encoded)
    if case == "corrupted_json":
        encoded = "{"
    elif case == "invalid_state":
        payload["state"] = "trusted"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "invalid_reason":
        payload["state"] = "blocked"
        payload["blocking_reasons"] = ["invented"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "duplicate_reason":
        payload["state"] = "blocked"
        payload["blocking_reasons"] = ["non_domestic_market", "non_domestic_market"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "wrong_reason_order":
        payload["state"] = "blocked"
        payload["blocking_reasons"] = [
            "current_use_verification_missing",
            "non_domestic_market",
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "unsupported_policy":
        payload["policy_version"] = "2.0.0"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "unsupported_schema":
        payload["schema_version"] = "future"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "corrupted_manifest":
        del payload["source_manifest"]["competition"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "missing_source_identity":
        payload["source_manifest"]["demand"]["observation_id"] = ""
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "wrong_market_lineage":
        payload["source_manifest"]["market_identity"]["market"] = "US"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "malformed_verification":
        payload["verification"]["current_use_confirmed"] = "yes"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "unconfirmed_validated":
        payload["verification"]["current_use_confirmed"] = False
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "wrong_reviewed_sources":
        payload["verification"]["reviewed_source_ids"] = ["other"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "invalid_timestamp":
        payload["evaluated_at"] = "2026-08-09T11:00:00"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif case == "validated_with_blocker":
        payload["blocking_reasons"] = ["non_domestic_market"]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    raw.execute(
        "UPDATE domestic_market_validation_history SET payload_json=?, integrity_fingerprint=? WHERE assessment_id=?",
        (encoded, fingerprint, result.assessment.assessment_id),
    )
    raw.commit()
    raw.close()

    repository = SQLiteDomesticMarketValidationRepository(database)
    with pytest.raises(MalformedDomesticMarketValidationPersistenceError):
        repository.get_assessment(result.assessment.assessment_id)
    repository.close()
