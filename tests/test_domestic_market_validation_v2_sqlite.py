from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app.application.domestic_market_validation_v2 import (
    DomesticMarketValidationV2ReplayConflictError,
    PersistDomesticMarketValidationV2ForCapital,
    ValidateDomesticMarketV2Command,
    ValidateDomesticMarketV2ForCapital,
)
from app.domain.market_intelligence.domestic_market_validation import (
    DomesticMarketValidationAssessment,
    DomesticMarketValidationState,
)
from app.domain.market_intelligence.domestic_market_validation_v2 import (
    DomesticMarketValidationV2Assessment,
    DomesticMarketVerificationV2,
)
from app.infrastructure.domestic_market_validation_v2 import (
    DomesticMarketValidationV2CommitError,
    DomesticMarketValidationV2CorruptionError,
    DomesticMarketValidationV2HistoryError,
    DomesticMarketValidationV2ReceiptError,
    SQLiteDomesticMarketValidationV2Repository,
)
from test_domestic_market_validation_v2 import (
    DEMAND_FINGERPRINT,
    EVALUATED_AT,
    SOURCE_TIME,
    TARGET,
    VERIFIED_AT,
    Repository,
    _competition_publication,
    _competition_reference,
    _demand_publication,
)


COMMITTED_AT = EVALUATED_AT + timedelta(minutes=1)


class Values:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if not self.values:
            raise AssertionError("unexpected supplier invocation")
        return self.values.pop(0)


class CountingSourceRepository(Repository):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def _called(self):
        self.calls += 1

    def get_target_binding(self, opportunity_id):
        self._called()
        return super().get_target_binding(opportunity_id)

    def get_competition_publication(self, observation_id):
        self._called()
        return super().get_competition_publication(observation_id)

    def get_competition_authority_fingerprint(self, cohort_id):
        self._called()
        return super().get_competition_authority_fingerprint(cohort_id)

    def get_demand_publication(self, observation_id):
        self._called()
        return super().get_demand_publication(observation_id)

    def get_demand_authority_fingerprint(self, observation_id):
        self._called()
        return super().get_demand_authority_fingerprint(observation_id)


def setup_core(
    *,
    current_use_confirmed=True,
    competition_reference=False,
    assessment_ids=None,
    evaluated_clock=None,
):
    competition, fingerprint = _competition_publication()
    reference = (
        _competition_reference(competition, fingerprint)
        if competition_reference
        else None
    )
    demand = _demand_publication(competition_reference=reference)
    source = CountingSourceRepository(
        competition,
        demand,
        competition_fingerprint=fingerprint,
    )
    assessment_ids = assessment_ids or Values("dmv-v2-assessment-1")
    evaluated_clock = evaluated_clock or Values(EVALUATED_AT)
    owner = ValidateDomesticMarketV2ForCapital(
        source,
        assessment_id_generator=assessment_ids,
        evaluated_clock=evaluated_clock,
    )
    manifest = owner.resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    command = ValidateDomesticMarketV2Command(
        command_id="dmv-v2-command-1",
        opportunity_id="opportunity-1",
        competition_observation_id="competition-observation-1",
        demand_observation_id="obs-1",
        verification=DomesticMarketVerificationV2(
            operator_id="founder",
            verified_at=VERIFIED_AT,
            current_use_confirmed=current_use_confirmed,
            reviewed_source_manifest_fingerprint=manifest.fingerprint,
        ),
        requested_at=VERIFIED_AT,
    )
    source.calls = 0
    return source, owner, command, assessment_ids, evaluated_clock


def persisted_service(database, *, current=True, reference=False, ids=None, evaluated=None, committed=None):
    source, owner, command, ids, evaluated = setup_core(
        current_use_confirmed=current,
        competition_reference=reference,
        assessment_ids=ids,
        evaluated_clock=evaluated,
    )
    repository = SQLiteDomesticMarketValidationV2Repository(database)
    committed = committed or Values(COMMITTED_AT)
    service = PersistDomesticMarketValidationV2ForCapital(
        repository,
        owner,
        committed_clock=committed,
    )
    return repository, service, command, source, ids, evaluated, committed


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "domestic_market_validation_v2_history",
            "domestic_market_validation_v2_receipts",
        )
    )


@pytest.mark.parametrize("current", (True, False))
@pytest.mark.parametrize("reference", (True, False))
def test_exact_assessment_round_trip_preserves_manifest_verification_and_sources(
    tmp_path: Path, current: bool, reference: bool,
):
    database = tmp_path / f"round-trip-{current}-{reference}.db"
    repository, service, command, *_ = persisted_service(
        database, current=current, reference=reference,
    )

    publication = service.execute(command)
    loaded = repository.get_assessment(publication.assessment.assessment_id)

    assert publication.replayed is False
    assert loaded == publication.assessment
    assert loaded.source_manifest_fingerprint == publication.receipt.source_manifest_fingerprint
    assert loaded.verification == command.verification
    assert loaded.source_manifest.competition == publication.assessment.source_manifest.competition
    assert loaded.source_manifest.demand == publication.assessment.source_manifest.demand
    assert (
        loaded.source_manifest.demand.source_competition_cohort is not None
    ) is reference
    expected_state = (
        DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
        if current
        else DomesticMarketValidationState.BLOCKED
    )
    assert loaded.state is expected_state
    assert counts(repository) == (1, 1)
    repository.close()


def test_assessment_and_receipt_commit_atomically_on_each_insert_failure(tmp_path: Path):
    for table, expected in (
        ("domestic_market_validation_v2_history", DomesticMarketValidationV2HistoryError),
        ("domestic_market_validation_v2_receipts", DomesticMarketValidationV2ReceiptError),
    ):
        database = tmp_path / f"atomic-{table}.db"
        repository, service, command, *_ = persisted_service(database)
        repository._connection.execute(
            f"CREATE TRIGGER forced_failure BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT,'forced'); END"
        )
        with pytest.raises(expected):
            service.execute(command)
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        repository.close()


def test_commit_failure_rolls_back_and_retry_succeeds(tmp_path: Path):
    database = tmp_path / "commit-failure.db"
    source, owner, command, *_ = setup_core()

    class FailingCommitRepository(SQLiteDomesticMarketValidationV2Repository):
        def _commit(self):
            raise sqlite3.OperationalError("forced")

    failing = FailingCommitRepository(database)
    service = PersistDomesticMarketValidationV2ForCapital(
        failing, owner, committed_clock=Values(COMMITTED_AT),
    )
    with pytest.raises(DomesticMarketValidationV2CommitError):
        service.execute(command)
    assert counts(failing) == (0, 0)
    failing.close()

    retry_ids = Values("retry-assessment")
    _, retry_owner, _, _, _ = setup_core(assessment_ids=retry_ids)
    retry = SQLiteDomesticMarketValidationV2Repository(database)
    result = PersistDomesticMarketValidationV2ForCapital(
        retry, retry_owner, committed_clock=Values(COMMITTED_AT),
    ).execute(command)
    assert result.replayed is False
    assert counts(retry) == (1, 1)
    retry.close()


def test_exact_restart_replay_uses_only_persisted_historical_assessment(tmp_path: Path):
    database = tmp_path / "restart-replay.db"
    repository, service, command, source, ids, evaluated, committed = persisted_service(database)
    first = service.execute(command)
    assert (source.calls, ids.calls, evaluated.calls, committed.calls) == (5, 1, 1, 1)
    repository.close()

    class ExplodingOwner:
        def execute(self, _command):
            raise AssertionError("historical replay must not resolve live upstream sources")

    restarted = SQLiteDomesticMarketValidationV2Repository(database)
    replay_clock = Values()
    replay = PersistDomesticMarketValidationV2ForCapital(
        restarted,
        ExplodingOwner(),
        committed_clock=replay_clock,
    ).execute(command)

    assert replay.replayed is True
    assert replay.assessment == first.assessment
    assert replay.receipt == first.receipt
    assert replay_clock.calls == 0
    assert counts(restarted) == (1, 1)
    restarted.close()


def test_same_command_changed_fingerprint_conflicts_before_source_or_clocks(tmp_path: Path):
    database = tmp_path / "replay-conflict.db"
    repository, service, command, *_ = persisted_service(database)
    service.execute(command)
    changed = replace(
        command,
        verification=replace(command.verification, operator_id="other-founder"),
    )

    class ExplodingOwner:
        def execute(self, _command):
            raise AssertionError("conflict must precede source resolution")

    clock = Values()
    with pytest.raises(DomesticMarketValidationV2ReplayConflictError):
        PersistDomesticMarketValidationV2ForCapital(
            repository, ExplodingOwner(), committed_clock=clock,
        ).execute(changed)
    assert clock.calls == 0
    assert counts(repository) == (1, 1)
    repository.close()


def test_new_command_with_same_sources_is_new_event_not_alias(tmp_path: Path):
    database = tmp_path / "new-command.db"
    ids = Values("assessment-one", "assessment-two")
    evaluated = Values(EVALUATED_AT, EVALUATED_AT)
    committed = Values(COMMITTED_AT, COMMITTED_AT + timedelta(seconds=1))
    repository, service, command, *_ = persisted_service(
        database, ids=ids, evaluated=evaluated, committed=committed,
    )
    first = service.execute(command)
    second = service.execute(replace(command, command_id="dmv-v2-command-2"))

    assert second.replayed is False
    assert first.assessment.assessment_id != second.assessment.assessment_id
    assert first.assessment.source_manifest == second.assessment.source_manifest
    assert counts(repository) == (2, 2)
    repository.close()


@pytest.mark.parametrize(
    ("table", "operation"),
    tuple(
        (table, operation)
        for table in (
            "domestic_market_validation_v2_history",
            "domestic_market_validation_v2_receipts",
        )
        for operation in ("UPDATE", "DELETE")
    ),
)
def test_history_and_receipts_are_append_only(
    tmp_path: Path, table: str, operation: str,
):
    database = tmp_path / f"append-only-{table}-{operation}.db"
    repository, service, command, *_ = persisted_service(database)
    service.execute(command)
    if operation == "DELETE":
        statement = f"DELETE FROM {table}"
    elif table.endswith("history"):
        statement = f"UPDATE {table} SET state='blocked'"
    else:
        statement = f"UPDATE {table} SET command_fingerprint='{'0' * 64}'"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute(statement)
    repository._connection.rollback()
    assert counts(repository) == (1, 1)
    repository.close()


def _drop_update_trigger(repository, table):
    repository._connection.execute(f"DROP TRIGGER trg_{table}_no_update")


def _rewrite_history_payload(repository, assessment_id, mutate, *, update_hash=True):
    row = repository._connection.execute(
        "SELECT payload_json FROM domestic_market_validation_v2_history WHERE assessment_id=?",
        (assessment_id,),
    ).fetchone()
    payload = json.loads(row["payload_json"])
    mutate(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = (
        hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if update_hash
        else "0" * 64
    )
    repository._connection.execute(
        "UPDATE domestic_market_validation_v2_history "
        "SET payload_json=?,integrity_fingerprint=? WHERE assessment_id=?",
        (encoded, fingerprint, assessment_id),
    )
    repository._connection.commit()


@pytest.mark.parametrize(
    "case",
    (
        "payload_hash",
        "payload_assessment_id",
        "malformed_target",
        "malformed_competition",
        "malformed_demand",
        "malformed_competition_reference",
        "unsupported_payload_schema",
        "unsupported_policy",
        "impossible_state",
    ),
)
def test_corrupted_history_payload_fails_closed(tmp_path: Path, case: str):
    database = tmp_path / f"history-corruption-{case}.db"
    repository, service, command, *_ = persisted_service(database, reference=True)
    result = service.execute(command)
    assessment_id = result.assessment.assessment_id
    _drop_update_trigger(repository, "domestic_market_validation_v2_history")

    def mutate(payload):
        if case == "payload_assessment_id":
            payload["assessment_id"] = "other-assessment"
        elif case == "malformed_target":
            del payload["source_manifest"]["target_binding"]["target_identity"]["market"]
        elif case == "malformed_competition":
            del payload["source_manifest"]["competition"]["cohort_id"]
        elif case == "malformed_demand":
            del payload["source_manifest"]["demand"]["assessment_id"]
        elif case == "malformed_competition_reference":
            del payload["source_manifest"]["demand"]["source_competition_cohort"]["cohort_id"]
        elif case == "unsupported_payload_schema":
            payload["schema_version"] = "future"
        elif case == "unsupported_policy":
            payload["policy_version"] = "3.0.0"
        elif case == "impossible_state":
            payload["state"] = "blocked"

    _rewrite_history_payload(
        repository,
        assessment_id,
        mutate,
        update_hash=case != "payload_hash",
    )
    with pytest.raises(DomesticMarketValidationV2CorruptionError):
        repository.get_assessment(assessment_id)
    repository.close()


@pytest.mark.parametrize(
    "column",
    (
        "source_manifest_fingerprint",
        "opportunity_id",
        "domestic_selling_target_id",
        "state",
        "schema_version",
    ),
)
def test_corrupted_history_columns_fail_closed(tmp_path: Path, column: str):
    database = tmp_path / f"history-column-{column}.db"
    repository, service, command, *_ = persisted_service(database)
    result = service.execute(command)
    _drop_update_trigger(repository, "domestic_market_validation_v2_history")
    value = "f" * 64 if column == "source_manifest_fingerprint" else "corrupted"
    repository._connection.execute(
        f"UPDATE domestic_market_validation_v2_history SET {column}=? WHERE assessment_id=?",
        (value, result.assessment.assessment_id),
    )
    repository._connection.commit()
    with pytest.raises(DomesticMarketValidationV2CorruptionError):
        repository.get_assessment(result.assessment.assessment_id)
    repository.close()


@pytest.mark.parametrize(
    "case",
    ("command_fingerprint", "source_fingerprint", "assessment_link", "receipt_schema"),
)
def test_corrupted_receipt_fails_closed(tmp_path: Path, case: str):
    database = tmp_path / f"receipt-corruption-{case}.db"
    repository, service, command, *_ = persisted_service(database)
    result = service.execute(command)
    _drop_update_trigger(repository, "domestic_market_validation_v2_receipts")
    if case == "assessment_link":
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        column, value = "assessment_id", "missing-assessment"
    elif case == "receipt_schema":
        column, value = "schema_version", "future"
    elif case == "source_fingerprint":
        column, value = "source_manifest_fingerprint", "e" * 64
    else:
        column, value = "command_fingerprint", "e" * 64
    repository._connection.execute(
        f"UPDATE domestic_market_validation_v2_receipts SET {column}=? WHERE command_id=?",
        (value, command.command_id),
    )
    repository._connection.commit()
    with pytest.raises(DomesticMarketValidationV2CorruptionError):
        repository.get_receipt(command.command_id)
    assert result.assessment.assessment_id
    repository.close()


def test_read_is_pure_and_v2_namespace_emits_no_v1_rows(tmp_path: Path):
    database = tmp_path / "read-purity.db"
    repository, service, command, *_ = persisted_service(database)
    result = service.execute(command)
    before = repository._connection.total_changes
    assert repository.get_assessment(result.assessment.assessment_id) == result.assessment
    assert repository.get_receipt(command.command_id) == result.receipt
    assert repository._connection.total_changes == before
    names = {
        row[0]
        for row in repository._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "domestic_market_validation_history" not in names
    assert "domestic_market_validation_receipts" not in names
    assert not isinstance(result.assessment, DomesticMarketValidationAssessment)
    assert isinstance(result.assessment, DomesticMarketValidationV2Assessment)
    repository.close()


def test_concurrent_same_command_converges_on_one_historical_publication(tmp_path: Path):
    database = tmp_path / "concurrent.db"
    _, _, command, *_ = setup_core()
    initialized = SQLiteDomesticMarketValidationV2Repository(database)
    initialized.close()

    def run(suffix):
        ids = Values(f"assessment-{suffix}")
        _, owner, _, _, _ = setup_core(assessment_ids=ids)
        repository = SQLiteDomesticMarketValidationV2Repository(database)
        try:
            return PersistDomesticMarketValidationV2ForCapital(
                repository,
                owner,
                committed_clock=Values(COMMITTED_AT),
            ).execute(command)
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, ("one", "two")))
    assert len({result.assessment.assessment_id for result in results}) == 1
    repository = SQLiteDomesticMarketValidationV2Repository(database)
    assert counts(repository) == (1, 1)
    repository.close()


def test_concurrent_changed_command_has_one_commit_and_one_replay_conflict(
    tmp_path: Path,
):
    database = tmp_path / "concurrent-conflict.db"
    _, _, command, *_ = setup_core()
    initialized = SQLiteDomesticMarketValidationV2Repository(database)
    initialized.close()

    def run(operator):
        _, owner, _, _, _ = setup_core(
            assessment_ids=Values(f"assessment-{operator}"),
        )
        repository = SQLiteDomesticMarketValidationV2Repository(database)
        changed = replace(
            command,
            verification=replace(command.verification, operator_id=operator),
        )
        try:
            return PersistDomesticMarketValidationV2ForCapital(
                repository,
                owner,
                committed_clock=Values(COMMITTED_AT),
            ).execute(changed)
        finally:
            repository.close()

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(pool.submit(run, value) for value in ("one", "two"))
        for future in futures:
            try:
                outcomes.append(future.result())
            except DomesticMarketValidationV2ReplayConflictError:
                outcomes.append("conflict")

    assert sum(value == "conflict" for value in outcomes) == 1
    repository = SQLiteDomesticMarketValidationV2Repository(database)
    assert counts(repository) == (1, 1)
    repository.close()
