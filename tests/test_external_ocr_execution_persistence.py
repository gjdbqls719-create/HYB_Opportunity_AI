import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Lock

import pytest

from app.application.ocr import (
    AdmitExternalOCRExecution,
    ArtifactAdmissionConflictError,
    ExternalOCRCandidateAdmission,
    OCRAdmissionDependencyError,
    OCRAdmissionValidationError,
    OCRExecutionConflictError,
    OCRExecutionPersistenceError,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    OCRField,
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)
from app.infrastructure.external_signal_ledger import (
    SQLiteExternalSignalLedgerRepository,
)


CAPTURED_AT = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
EXECUTED_AT = CAPTURED_AT + timedelta(minutes=1)
ARTIFACT_ADMITTED_AT = EXECUTED_AT + timedelta(minutes=1)
COMMITTED_AT = ARTIFACT_ADMITTED_AT + timedelta(seconds=1)


class Sequence:
    def __init__(self, *values):
        self._values = iter(values)
        self.calls = 0
        self._lock = Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
            return next(self._values)


class Fail:
    def __init__(self, message: str):
        self.message = message
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise RuntimeError(self.message)


def artifact(**overrides) -> ArtifactReference:
    values = dict(
        artifact_id="artifact-1",
        artifact_type=ArtifactType.SCREENSHOT,
        artifact_origin=ArtifactOrigin.ITEMSCOUT,
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        sha256="a" * 64,
        captured_at=CAPTURED_AT,
        width=1920,
        height=1080,
        mime_type="image/png",
        file_size=1234,
        schema_version="artifact-v1",
    )
    values.update(overrides)
    return ArtifactReference(**values)


def fields() -> tuple[OCRFieldResult, ...]:
    return (
        OCRFieldResult(
            field_name=OCRField.PRICE,
            raw_text="19,900",
            normalized_value=Decimal("19900"),
            confidence=Decimal("0.91"),
            bounding_box=(10, 20, 30, 40),
        ),
        OCRFieldResult(
            field_name=OCRField.SEARCH_VOLUME,
            raw_text="1,234",
            normalized_value=1234,
            confidence=Decimal("0.82"),
            bounding_box=None,
        ),
    )


def result(**overrides) -> OCRResult:
    values = dict(
        request_id="external-request-1",
        artifact_id="artifact-1",
        provider=OCRProvider.GOOGLE_VISION,
        provider_version="2026-08",
        executed_at=EXECUTED_AT,
        fields=fields(),
        confidence=Decimal("0.87"),
        schema_version="ocr-result-v1",
    )
    values.update(overrides)
    return OCRResult(**values)


def entry(
    repository,
    *,
    identities=None,
    artifact_clock=None,
    receipt_clock=None,
) -> ExternalOCRCandidateAdmission:
    return ExternalOCRCandidateAdmission(
        persistence=repository,
        candidate_identity_supplier=identities or Sequence("candidate-1", "candidate-2"),
        artifact_admission_clock=artifact_clock or Sequence(ARTIFACT_ADMITTED_AT),
        receipt_clock=receipt_clock or Sequence(COMMITTED_AT),
    )


def command(*, artifact_value=None, result_value=None) -> AdmitExternalOCRExecution:
    return AdmitExternalOCRExecution(
        artifact=artifact_value or artifact(),
        result=result_value or result(),
    )


def count(repository, table: str) -> int:
    return repository._connection.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]


def test_fresh_external_execution_persists_complete_provenance_and_order() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    identities = Sequence("candidate-price", "candidate-volume")
    artifact_clock = Sequence(ARTIFACT_ADMITTED_AT)
    receipt_clock = Sequence(COMMITTED_AT)

    admitted = entry(
        repository,
        identities=identities,
        artifact_clock=artifact_clock,
        receipt_clock=receipt_clock,
    ).execute(command())

    assert admitted.replayed is False
    assert admitted.execution.result == result()
    assert admitted.execution.artifact == artifact()
    assert admitted.execution.result.fields[0].bounding_box == (10, 20, 30, 40)
    assert admitted.receipt.ordered_candidate_ids == (
        "candidate-price",
        "candidate-volume",
    )
    assert tuple(candidate.candidate_id for candidate in admitted.candidates) == (
        "candidate-price",
        "candidate-volume",
    )
    assert tuple(candidate.field_name for candidate in admitted.candidates) == (
        OCRField.PRICE,
        OCRField.SEARCH_VOLUME,
    )
    assert all(candidate.artifact == artifact() for candidate in admitted.candidates)
    assert all(candidate.captured_at == EXECUTED_AT for candidate in admitted.candidates)
    assert all(not hasattr(candidate, "verified_at") for candidate in admitted.candidates)
    assert identities.calls == 2
    assert artifact_clock.calls == 1
    assert receipt_clock.calls == 1
    assert repository.get_artifact_admission("artifact-1") == admitted.artifact_admission
    assert repository.get_execution(
        OCRProvider.GOOGLE_VISION, "external-request-1", "artifact-1"
    ) == admitted.execution
    assert repository.get_execution_receipt(
        OCRProvider.GOOGLE_VISION, "external-request-1", "artifact-1"
    ) == admitted.receipt
    assert tuple(
        repository.get_candidate(candidate_id)
        for candidate_id in admitted.receipt.ordered_candidate_ids
    ) == admitted.candidates


def test_exact_replay_reconstructs_without_suppliers_clocks_or_writes() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    first = entry(repository).execute(command())
    before = {
        table: count(repository, table)
        for table in (
            "ocr_artifact_admission_history",
            "ocr_execution_history",
            "ocr_candidate_history",
            "ocr_execution_receipts",
        )
    }
    identities = Fail("identity must not run")
    artifact_clock = Fail("artifact clock must not run")
    receipt_clock = Fail("receipt clock must not run")

    replay = entry(
        repository,
        identities=identities,
        artifact_clock=artifact_clock,
        receipt_clock=receipt_clock,
    ).execute(command())

    assert replay == replace(first, replayed=True)
    assert identities.calls == artifact_clock.calls == receipt_clock.calls == 0
    assert {
        table: count(repository, table) for table in before
    } == before


def test_same_execution_key_with_changed_payload_conflicts_without_writes() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    original = entry(repository).execute(command())
    changed = result(provider_version="changed-version")
    identities = Fail("identity must not run")
    receipt_clock = Fail("clock must not run")

    with pytest.raises(OCRExecutionConflictError):
        entry(
            repository,
            identities=identities,
            artifact_clock=Fail("artifact clock must not run"),
            receipt_clock=receipt_clock,
        ).execute(command(result_value=changed))

    assert identities.calls == receipt_clock.calls == 0
    assert repository.get_execution_receipt(
        OCRProvider.GOOGLE_VISION, "external-request-1", "artifact-1"
    ) == original.receipt
    assert count(repository, "ocr_candidate_history") == 2


def test_artifact_conflict_precedes_execution_and_creates_nothing() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    entry(repository).execute(command())
    conflict = artifact(sha256="b" * 64)
    identities = Fail("identity must not run")

    with pytest.raises(ArtifactAdmissionConflictError):
        entry(
            repository,
            identities=identities,
            artifact_clock=Fail("artifact clock must not run"),
            receipt_clock=Fail("receipt clock must not run"),
        ).execute(command(artifact_value=conflict))

    assert identities.calls == 0
    assert count(repository, "ocr_artifact_admission_history") == 1
    assert count(repository, "ocr_execution_history") == 1
    assert count(repository, "ocr_candidate_history") == 2
    assert count(repository, "ocr_execution_receipts") == 1


def test_same_artifact_key_with_changed_metadata_conflicts() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    entry(repository).execute(command())
    changed_metadata = artifact(width=1280)

    with pytest.raises(ArtifactAdmissionConflictError):
        entry(
            repository,
            identities=Fail("identity must not run"),
            artifact_clock=Fail("artifact clock must not run"),
            receipt_clock=Fail("receipt clock must not run"),
        ).execute(command(artifact_value=changed_metadata))

    assert count(repository, "ocr_artifact_admission_history") == 1
    assert count(repository, "ocr_execution_receipts") == 1


def test_zero_field_execution_commits_and_replays_empty_membership() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    identities = Fail("zero fields need no identities")
    empty_command = command(result_value=result(fields=()))

    fresh = entry(repository, identities=identities).execute(empty_command)
    replay = entry(
        repository,
        identities=identities,
        artifact_clock=Fail("replay clock must not run"),
        receipt_clock=Fail("replay clock must not run"),
    ).execute(empty_command)

    assert fresh.candidates == ()
    assert fresh.receipt.ordered_candidate_ids == ()
    assert replay == replace(fresh, replayed=True)
    assert identities.calls == 0
    assert count(repository, "ocr_candidate_history") == 0


def test_restart_reconstructs_original_candidates_and_provenance(tmp_path) -> None:
    database = tmp_path / "ocr.sqlite3"
    first_repository = SQLiteExternalSignalLedgerRepository(database)
    original = entry(first_repository).execute(command())
    first_repository.close()

    restarted = SQLiteExternalSignalLedgerRepository(database)
    replay = entry(
        restarted,
        identities=Fail("identity must not run"),
        artifact_clock=Fail("artifact clock must not run"),
        receipt_clock=Fail("receipt clock must not run"),
    ).execute(command())

    assert replay == replace(original, replayed=True)
    assert replay.execution.result.provider_version == "2026-08"
    assert replay.execution.result.fields[0].bounding_box == (10, 20, 30, 40)


def test_concurrent_same_execution_converges_before_identity_generation(tmp_path) -> None:
    database = tmp_path / "concurrent.sqlite3"
    SQLiteExternalSignalLedgerRepository(database).close()
    barrier = Barrier(2)
    identities = Sequence("candidate-1", "candidate-2", "unused-3", "unused-4")
    artifact_clock = Sequence(ARTIFACT_ADMITTED_AT, ARTIFACT_ADMITTED_AT)
    receipt_clock = Sequence(COMMITTED_AT, COMMITTED_AT)

    def admit():
        repository = SQLiteExternalSignalLedgerRepository(database)
        try:
            barrier.wait()
            return entry(
                repository,
                identities=identities,
                artifact_clock=artifact_clock,
                receipt_clock=receipt_clock,
            ).execute(command())
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: admit(), range(2)))

    assert {result.replayed for result in results} == {False, True}
    assert results[0].receipt == results[1].receipt
    assert results[0].candidates == results[1].candidates
    assert identities.calls == 2
    assert artifact_clock.calls == receipt_clock.calls == 1
    check = SQLiteExternalSignalLedgerRepository(database)
    assert count(check, "ocr_artifact_admission_history") == 1
    assert count(check, "ocr_execution_history") == 1
    assert count(check, "ocr_candidate_history") == 2
    assert count(check, "ocr_execution_receipts") == 1


def test_concurrent_changed_payload_commits_one_and_conflicts_one(tmp_path) -> None:
    database = tmp_path / "concurrent-conflict.sqlite3"
    SQLiteExternalSignalLedgerRepository(database).close()
    barrier = Barrier(2)
    identities = Sequence("candidate-1", "candidate-2", "candidate-3", "candidate-4")
    artifact_clock = Sequence(ARTIFACT_ADMITTED_AT, ARTIFACT_ADMITTED_AT)
    receipt_clock = Sequence(COMMITTED_AT, COMMITTED_AT)
    versions = ("provider-version-a", "provider-version-b")

    def admit(version):
        repository = SQLiteExternalSignalLedgerRepository(database)
        try:
            barrier.wait()
            return entry(
                repository,
                identities=identities,
                artifact_clock=artifact_clock,
                receipt_clock=receipt_clock,
            ).execute(command(result_value=result(provider_version=version)))
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(pool.submit(admit, version) for version in versions)
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except OCRExecutionConflictError as error:
                outcomes.append(error)

    assert sum(isinstance(value, OCRExecutionConflictError) for value in outcomes) == 1
    assert sum(not isinstance(value, Exception) for value in outcomes) == 1
    assert identities.calls == 2
    assert artifact_clock.calls == receipt_clock.calls == 1
    check = SQLiteExternalSignalLedgerRepository(database)
    assert count(check, "ocr_candidate_history") == 2
    assert count(check, "ocr_execution_receipts") == 1


@pytest.mark.parametrize(
    ("trigger_table", "expected_message"),
    (
        ("ocr_candidate_history", "candidate persistence"),
        ("ocr_execution_receipts", "receipt persistence"),
    ),
)
def test_execution_write_failure_rolls_back_every_fresh_fact(
    trigger_table: str, expected_message: str
) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    repository._connection.execute(
        f"""CREATE TRIGGER fail_ocr_admission BEFORE INSERT ON {trigger_table}
        BEGIN SELECT RAISE(ABORT, '{expected_message} failed'); END"""
    )

    with pytest.raises(OCRExecutionPersistenceError, match=expected_message):
        entry(repository).execute(command())

    for table in (
        "ocr_artifact_admission_history",
        "ocr_execution_history",
        "ocr_candidate_history",
        "ocr_candidate_current",
        "ocr_execution_receipts",
    ):
        assert count(repository, table) == 0


@pytest.mark.parametrize(
    ("identities", "artifact_clock", "receipt_clock"),
    (
        (Fail("identity failed"), Sequence(ARTIFACT_ADMITTED_AT), Sequence(COMMITTED_AT)),
        (Sequence("candidate-1", "candidate-2"), Fail("artifact clock failed"), Sequence(COMMITTED_AT)),
        (Sequence("candidate-1", "candidate-2"), Sequence(ARTIFACT_ADMITTED_AT), Fail("receipt clock failed")),
    ),
)
def test_dependency_failure_persists_nothing(
    identities, artifact_clock, receipt_clock
) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")

    with pytest.raises(OCRAdmissionDependencyError):
        entry(
            repository,
            identities=identities,
            artifact_clock=artifact_clock,
            receipt_clock=receipt_clock,
        ).execute(command())

    assert count(repository, "ocr_artifact_admission_history") == 0
    assert count(repository, "ocr_execution_history") == 0
    assert count(repository, "ocr_candidate_history") == 0
    assert count(repository, "ocr_execution_receipts") == 0


@pytest.mark.parametrize(
    "invalid_result",
    (
        result(executed_at=CAPTURED_AT - timedelta(seconds=1)),
        result(fields=(replace(fields()[0], raw_text=""),)),
    ),
)
def test_external_execution_candidate_invariants_fail_before_dependencies(
    invalid_result,
) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    identities = Fail("identity must not run")

    with pytest.raises(OCRAdmissionValidationError):
        command(result_value=invalid_result)

    assert identities.calls == 0
    assert count(repository, "ocr_artifact_admission_history") == 0


def test_distinct_execution_for_same_artifact_preserves_both_batches() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    first = entry(repository).execute(command())
    second_result = result(request_id="external-request-2")
    second = entry(
        repository,
        identities=Sequence("candidate-3", "candidate-4"),
        artifact_clock=Fail("existing artifact needs no clock"),
        receipt_clock=Sequence(COMMITTED_AT + timedelta(minutes=1)),
    ).execute(command(result_value=second_result))

    assert first.receipt.ordered_candidate_ids == ("candidate-1", "candidate-2")
    assert second.receipt.ordered_candidate_ids == ("candidate-3", "candidate-4")
    assert count(repository, "ocr_artifact_admission_history") == 1
    assert count(repository, "ocr_execution_history") == 2
    assert count(repository, "ocr_candidate_history") == 4
    assert count(repository, "ocr_execution_receipts") == 2


def test_repository_tables_are_append_only() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    entry(repository).execute(command())

    for table in (
        "ocr_artifact_admission_history",
        "ocr_execution_history",
        "ocr_execution_receipts",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()
