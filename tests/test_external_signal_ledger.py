import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.external_signal_ledger import (
    DuplicateExternalSignalLedgerError,
    ExternalSignalLedgerService,
    GetLatestVerification,
    GetVerificationHistory,
    SaveHumanVerification,
    SaveOCRCandidate,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    HumanVerification,
    OCRCandidate,
    OCRField,
)
from app.infrastructure.external_signal_ledger import SQLiteExternalSignalLedgerRepository


NOW = datetime(2026, 8, 11, 9, tzinfo=timezone.utc)


def artifact() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="artifact-1",
        artifact_type=ArtifactType.SCREENSHOT,
        artifact_origin=ArtifactOrigin.ITEMSCOUT,
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        sha256="a" * 64,
        captured_at=NOW,
        width=1920,
        height=1080,
        mime_type="image/png",
        file_size=100,
        schema_version="artifact-v1",
    )


def candidate(*, candidate_id="candidate-1", at=NOW + timedelta(seconds=1), value=Decimal("1234")) -> OCRCandidate:
    return OCRCandidate(
        candidate_id=candidate_id,
        artifact=artifact(),
        field_name=OCRField.SEARCH_VOLUME,
        raw_text="1,234",
        normalized_value=value,
        confidence=Decimal("0.81"),
        captured_at=at,
        schema_version="ocr-candidate-v1",
    )


def verification(*, verification_id="verification-1", at=NOW + timedelta(minutes=1), value=Decimal("1234")) -> HumanVerification:
    return HumanVerification(
        verification_id=verification_id,
        candidate_id="candidate-1",
        verified_value=value,
        operator_id="founder-1",
        verified_at=at,
        comment="verified",
        schema_version="human-verification-v1",
    )


def count(repository, table: str) -> int:
    return repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def repository_with_candidate() -> SQLiteExternalSignalLedgerRepository:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    repository.save_candidate(candidate())
    return repository


def test_candidate_round_trip_and_application_save() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    item = candidate()
    assert ExternalSignalLedgerService(repository).save_candidate(SaveOCRCandidate(item)) == item
    assert repository.get_latest_candidate("artifact-1", OCRField.SEARCH_VOLUME) == item
    assert repository.get_candidate_history("artifact-1", OCRField.SEARCH_VOLUME) == (item,)


def test_verification_round_trip_and_application_queries() -> None:
    repository = repository_with_candidate()
    service = ExternalSignalLedgerService(repository)
    item = verification()
    assert service.save_verification(SaveHumanVerification(item)) == item
    assert service.get_latest_verification(GetLatestVerification("candidate-1")) == item
    assert service.get_verification_history(GetVerificationHistory("candidate-1")) == (item,)


def test_candidate_append_only_history_and_projection_do_not_regress() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    latest = candidate(candidate_id="candidate-latest", at=NOW + timedelta(minutes=3), value=Decimal("2000"))
    older = candidate(candidate_id="candidate-older", at=NOW + timedelta(minutes=2), value=Decimal("1000"))
    repository.save_candidate(latest)
    repository.save_candidate(older)
    assert repository.get_latest_candidate("artifact-1", OCRField.SEARCH_VOLUME) == latest
    assert repository.get_candidate_history("artifact-1", OCRField.SEARCH_VOLUME) == (latest, older)
    assert count(repository, "ocr_candidate_history") == 2


def test_verification_append_only_history_and_projection_do_not_regress() -> None:
    repository = repository_with_candidate()
    latest = verification(verification_id="verification-latest", at=NOW + timedelta(minutes=3), value=Decimal("2000"))
    older = verification(verification_id="verification-older", at=NOW + timedelta(minutes=2), value=Decimal("1000"))
    repository.save_verification(latest)
    repository.save_verification(older)
    assert repository.get_latest_verification("candidate-1") == latest
    assert repository.get_verification_history("candidate-1") == (latest, older)


def test_candidate_duplicate_fingerprint_rolls_back_history_and_projection() -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    original = candidate()
    repository.save_candidate(original)
    duplicate = replace(original, candidate_id="candidate-other", normalized_value=Decimal("999"))
    with pytest.raises(DuplicateExternalSignalLedgerError):
        repository.save_candidate(duplicate)
    assert count(repository, "ocr_candidate_history") == 1
    assert repository.get_latest_candidate("artifact-1", OCRField.SEARCH_VOLUME) == original


def test_verification_duplicate_fingerprint_rolls_back_history_and_projection() -> None:
    repository = repository_with_candidate()
    original = verification()
    repository.save_verification(original)
    duplicate = replace(original, verification_id="verification-other", comment="different")
    with pytest.raises(DuplicateExternalSignalLedgerError):
        repository.save_verification(duplicate)
    assert count(repository, "human_verification_history") == 1
    assert repository.get_latest_verification("candidate-1") == original


@pytest.mark.parametrize(
    ("projection_table", "save", "history_table"),
    (
        ("ocr_candidate_current", lambda repository: repository.save_candidate(candidate()), "ocr_candidate_history"),
        ("human_verification_current", lambda repository: repository.save_verification(verification()), "human_verification_history"),
    ),
)
def test_projection_failure_rolls_back_history(projection_table, save, history_table) -> None:
    repository = SQLiteExternalSignalLedgerRepository(":memory:")
    if projection_table == "human_verification_current":
        repository.save_candidate(candidate())
    repository._connection.execute(
        f"""CREATE TRIGGER fail_projection BEFORE INSERT ON {projection_table}
        BEGIN SELECT RAISE(ABORT, 'projection failure'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="projection failure"):
        save(repository)
    assert count(repository, history_table) == 0
    assert count(repository, projection_table) == 0


@pytest.mark.parametrize("table", ("ocr_candidate_history", "human_verification_history"))
def test_history_update_and_delete_are_blocked_by_triggers(table: str) -> None:
    repository = repository_with_candidate()
    if table == "human_verification_history":
        repository.save_verification(verification())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute(f"UPDATE {table} SET payload_json = 'changed'")
    repository._connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute(f"DELETE FROM {table}")
    repository._connection.rollback()
    assert count(repository, table) == 1


def test_history_is_latest_first_and_limit_is_applied() -> None:
    repository = repository_with_candidate()
    first = verification(verification_id="verification-1", at=NOW + timedelta(minutes=1))
    second = verification(verification_id="verification-2", at=NOW + timedelta(minutes=2))
    repository.save_verification(first)
    repository.save_verification(second)
    assert repository.get_verification_history("candidate-1") == (second, first)
    assert repository.get_verification_history("candidate-1", limit=1) == (second,)
    with pytest.raises(ValueError, match="positive integer"):
        repository.get_verification_history("candidate-1", limit=0)
