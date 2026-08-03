from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.review import (
    ApproveCandidate,
    CreateReviewSession,
    GetReviewSession,
    GetReviewSessionHistory,
    ListReviewSessions,
    ReviewCommandConflictError,
    ReviewPersistenceError,
    ReviewSessionQueryService,
    ReviewSessionVersionConflictError,
    ReviewTransitionMetadata,
    ReviewWorkflowService,
    SkipCandidate,
    StartReview,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketObservationIdentity,
    MarketObservationScope,
    OCRCandidate,
    OCRField,
    ReviewSession,
    ReviewSessionStatus,
)
from app.infrastructure.review import (
    SQLiteReviewSessionRepository,
    SQLiteVerifiedSignalPersistence,
)


NOW = datetime(2026, 8, 15, 9, tzinfo=timezone.utc)


def session() -> ReviewSession:
    return ReviewSession(
        session_id="review-1",
        artifact_id="artifact-1",
        candidate_ids=("candidate-1",),
        status=ReviewSessionStatus.OPEN,
        created_at=NOW,
        completed_at=None,
        operator_id="founder-1",
        schema_version="review-session-v1",
    )


def metadata(command_id="command-create", fingerprint="fingerprint-create", kind="create"):
    return ReviewTransitionMetadata(
        event_id=f"event-{command_id}",
        command_id=command_id,
        transition_type=kind,
        occurred_at=NOW,
        command_fingerprint=fingerprint,
    )


def candidate() -> OCRCandidate:
    artifact = ArtifactReference(
        artifact_id="artifact-1",
        artifact_type=ArtifactType.SCREENSHOT,
        artifact_origin=ArtifactOrigin.ITEMSCOUT,
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        sha256="a" * 64,
        captured_at=NOW,
        width=100,
        height=100,
        mime_type="image/png",
        file_size=10,
        schema_version="artifact-v1",
    )
    return OCRCandidate(
        candidate_id="candidate-1",
        artifact=artifact,
        field_name=OCRField.SEARCH_VOLUME,
        raw_text="100",
        normalized_value=100,
        confidence=Decimal("0.9"),
        captured_at=NOW,
        schema_version="ocr-candidate-v1",
    )


def identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.SEARCH_QUERY,
        market="KR",
        marketplace="coupang",
        canonical_product_id=None,
        marketplace_item_id=None,
        normalized_query="mouse",
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=NOW,
        window_ended_at=NOW + timedelta(minutes=1),
    )


def test_create_round_trip_restart_and_read_queries(tmp_path) -> None:
    path = tmp_path / "reviews.db"
    repository = SQLiteReviewSessionRepository(path)
    created = repository.create(session(), metadata())
    repository.close()

    restarted = SQLiteReviewSessionRepository(path)
    assert restarted.get("review-1") == created
    assert restarted.list() == (created,)
    query = ReviewSessionQueryService(restarted)
    assert query.get(GetReviewSession("review-1")) == created
    assert query.list(ListReviewSessions()) == (created,)
    history = query.history(GetReviewSessionHistory("review-1"))
    assert len(history) == 1
    assert history[0].session == created
    assert history[0].metadata.transition_type == "create"


def test_start_and_skip_round_trip_preserves_revision_and_metadata(tmp_path) -> None:
    persistence = SQLiteVerifiedSignalPersistence(tmp_path / "reviews.db")
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    started = service.start_review(StartReview(
        opened, "founder-1", NOW + timedelta(seconds=1), "command-start"
    ))
    skipped = service.skip_candidate(SkipCandidate(
        started,
        item,
        "founder-1",
        "not relevant",
        NOW + timedelta(seconds=2),
        "command-skip",
    )).session

    assert started.revision == 2
    assert skipped.revision == 3
    assert persistence.sessions.get("review-1") == skipped
    assert persistence.sessions.get_history("review-1")[-1].session.skip_records == skipped.skip_records
    assert persistence.ledger.get_verification_history("candidate-1") == ()


def test_history_is_append_only_and_projection_uses_latest_revision(tmp_path) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / "reviews.db")
    opened = repository.create(session(), metadata())
    started = opened.start(operator_id="founder-1", started_at=NOW + timedelta(seconds=1))
    repository.save_transition(
        opened,
        started,
        metadata("command-start", "fingerprint-start", "start"),
    )
    assert repository.get("review-1") == started
    assert [entry.session.revision for entry in repository.get_history("review-1")] == [1, 2]
    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute("UPDATE review_session_history SET revision = 9")
    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute("DELETE FROM review_session_history")


def test_stale_transition_and_separate_connection_conflict(tmp_path) -> None:
    path = tmp_path / "reviews.db"
    first = SQLiteReviewSessionRepository(path)
    opened = first.create(session(), metadata())
    second = SQLiteReviewSessionRepository(path)
    started = opened.start(operator_id="founder-1", started_at=NOW)
    first.save_transition(opened, started, metadata("start-1", "fp-1", "start"))
    competing = opened.cancel(operator_id="founder-1", cancelled_at=NOW)
    with pytest.raises(ReviewSessionVersionConflictError):
        second.save_transition(opened, competing, metadata("cancel-1", "fp-2", "cancel"))
    assert second.get("review-1") == started


def test_command_retry_is_idempotent_and_changed_payload_conflicts(tmp_path) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / "reviews.db")
    opened = repository.create(session(), metadata())
    assert repository.create(session(), metadata()) == opened
    with pytest.raises(ReviewCommandConflictError):
        repository.create(session(), metadata(fingerprint="changed"))
    assert len(repository.get_history("review-1")) == 1


def test_malformed_and_unsupported_payload_are_explicit(tmp_path) -> None:
    repository = SQLiteReviewSessionRepository(tmp_path / "reviews.db")
    repository.create(session(), metadata())
    repository._connection.execute(
        "UPDATE review_session_current SET payload_json = ? WHERE session_id = ?",
        ('{"schema_version":"future"}', "review-1"),
    )
    from app.application.review import UnsupportedReviewSessionVersionError
    with pytest.raises(UnsupportedReviewSessionVersionError):
        repository.get("review-1")


def test_approve_persists_all_three_areas_atomically(tmp_path) -> None:
    persistence = SQLiteVerifiedSignalPersistence(tmp_path / "reviews.db")
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    started = service.start_review(StartReview(opened, "founder-1", NOW))
    result = service.approve_candidate(ApproveCandidate(
        session=started,
        candidate=item,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
        command_id="approve-1",
    ))
    assert result.session.revision == 3
    assert persistence.sessions.get("review-1") == result.session
    assert persistence.ledger.get_latest_verification("candidate-1") == result.verification
    assert len(persistence.sessions.get_history("review-1")) == 3

    replay = service.approve_candidate(ApproveCandidate(
        session=started,
        candidate=item,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
        command_id="approve-1",
    ))
    assert replay == result
    assert len(persistence.sessions.get_history("review-1")) == 3
    assert len(persistence.ledger.get_verification_history("candidate-1")) == 1


def test_session_history_failure_rolls_back_verification_signal_and_session(tmp_path) -> None:
    persistence = SQLiteVerifiedSignalPersistence(tmp_path / "reviews.db")
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW
    ))
    started = service.start_review(StartReview(opened, "founder-1", NOW))
    persistence._connection.execute(
        """CREATE TRIGGER fail_review_history BEFORE INSERT ON review_session_history
        WHEN NEW.revision = 3 BEGIN SELECT RAISE(ABORT, 'forced failure'); END"""
    )
    command = ApproveCandidate(
        session=started,
        candidate=item,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
    )
    with pytest.raises(ReviewPersistenceError):
        service.approve_candidate(command)
    assert persistence.ledger.get_verification_history("candidate-1") == ()
    assert persistence.sessions.get("review-1") == started
    assert len(persistence.sessions.get_history("review-1")) == 2
    assert persistence._connection.in_transaction is False
