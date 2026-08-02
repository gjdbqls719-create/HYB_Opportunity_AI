from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.review import (
    ApproveCandidate,
    CancelReview,
    CompleteReview,
    CorrectCandidate,
    CreateReviewSession,
    DuplicateCandidateReviewError,
    ReviewWorkflowError,
    ReviewWorkflowService,
    StartReview,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    InvalidReviewSessionTransitionError,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
    OCRCandidate,
    OCRField,
    ReviewSessionStatus,
)
from app.infrastructure.external_signal_ledger import SQLiteExternalSignalLedgerRepository


NOW = datetime(2026, 8, 13, 9, tzinfo=timezone.utc)


def artifact(artifact_id="artifact-1") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
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


def candidate(artifact_id="artifact-1") -> OCRCandidate:
    return OCRCandidate(
        candidate_id="candidate-1",
        artifact=artifact(artifact_id),
        field_name=OCRField.SEARCH_VOLUME,
        raw_text="1,234",
        normalized_value=1234,
        confidence=Decimal("0.8"),
        captured_at=NOW + timedelta(seconds=1),
        schema_version="ocr-candidate-v1",
    )


def identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.SEARCH_QUERY,
        market="KR",
        marketplace="coupang",
        canonical_product_id=None,
        marketplace_item_id=None,
        normalized_query="wireless mouse",
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=NOW,
        window_ended_at=NOW + timedelta(minutes=5),
    )


def setup_workflow():
    ledger = SQLiteExternalSignalLedgerRepository(":memory:")
    item = candidate()
    ledger.save_candidate(item)
    service = ReviewWorkflowService(ledger)
    session = service.create_session(CreateReviewSession(
        session_id="session-1",
        artifact_id="artifact-1",
        candidate_ids=("candidate-1",),
        operator_id="founder-1",
        created_at=NOW,
    ))
    return service, ledger, item, session


def start(service, session):
    return service.start_review(StartReview(session, "founder-1"))


def approve_command(session, item, **overrides):
    values = dict(
        session=session,
        candidate=item,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
    )
    values.update(overrides)
    return ApproveCandidate(**values)


def test_session_create_start_and_immutability() -> None:
    service, _, _, opened = setup_workflow()
    assert opened.status is ReviewSessionStatus.OPEN
    assert opened.completed_at is None
    started = start(service, opened)
    assert started.status is ReviewSessionStatus.IN_PROGRESS
    assert opened.status is ReviewSessionStatus.OPEN
    with pytest.raises(FrozenInstanceError):
        opened.status = ReviewSessionStatus.COMPLETED  # type: ignore[misc]


def test_session_complete_and_terminal_rules() -> None:
    service, _, _, opened = setup_workflow()
    completed = service.complete_review(CompleteReview(
        start(service, opened), "founder-1", NOW + timedelta(minutes=2)
    ))
    assert completed.status is ReviewSessionStatus.COMPLETED
    assert completed.completed_at == NOW + timedelta(minutes=2)
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.start_review(StartReview(completed, "founder-1"))
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.cancel_review(CancelReview(completed, "founder-1", NOW + timedelta(minutes=3)))


def test_session_cancel_and_terminal_rules() -> None:
    service, _, _, opened = setup_workflow()
    cancelled = service.cancel_review(CancelReview(
        opened, "founder-1", NOW + timedelta(minutes=1)
    ))
    assert cancelled.status is ReviewSessionStatus.CANCELLED
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.start_review(StartReview(cancelled, "founder-1"))
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.complete_review(CompleteReview(cancelled, "founder-1", NOW + timedelta(minutes=2)))


def test_approve_creates_verification_ledger_fact_and_verified_signal() -> None:
    service, ledger, item, opened = setup_workflow()
    before = candidate()
    started = start(service, opened)
    result = service.approve_candidate(approve_command(started, item))
    assert item == before
    assert result.session == started
    assert result.verification.verified_value == 1234
    assert ledger.get_latest_verification("candidate-1") == result.verification
    assert result.signal.evidence.status is MarketEvidenceStatus.HUMAN_VERIFIED
    assert result.signal.evidence.value == 1234


def test_correct_uses_human_value_without_mutating_candidate() -> None:
    service, ledger, item, opened = setup_workflow()
    started = start(service, opened)
    result = service.correct_candidate(CorrectCandidate(
        session=started,
        candidate=item,
        corrected_value=1200,
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        identity=identity(),
        signal_id="signal-1",
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.NEUTRAL,
        comment="corrected comma parsing",
    ))
    assert item.normalized_value == 1234
    assert result.verification.verified_value == 1200
    assert result.signal.evidence.value == 1200
    assert ledger.get_latest_verification("candidate-1") == result.verification


def test_duplicate_approve_is_rejected_without_second_history_fact() -> None:
    service, ledger, item, opened = setup_workflow()
    started = start(service, opened)
    service.approve_candidate(approve_command(started, item))
    with pytest.raises(DuplicateCandidateReviewError):
        service.approve_candidate(approve_command(
            started, item, verification_id="verification-2", signal_id="signal-2"
        ))
    assert len(ledger.get_verification_history("candidate-1")) == 1


@pytest.mark.parametrize("terminal", (ReviewSessionStatus.COMPLETED, ReviewSessionStatus.CANCELLED))
def test_terminal_session_rejects_candidate_changes(terminal: ReviewSessionStatus) -> None:
    service, _, item, opened = setup_workflow()
    if terminal is ReviewSessionStatus.COMPLETED:
        terminal_session = service.complete_review(CompleteReview(
            start(service, opened), "founder-1", NOW + timedelta(minutes=2)
        ))
    else:
        terminal_session = service.cancel_review(CancelReview(
            opened, "founder-1", NOW + timedelta(minutes=2)
        ))
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.approve_candidate(approve_command(terminal_session, item))


def test_candidate_membership_artifact_and_ledger_existence_are_required() -> None:
    service, _, item, opened = setup_workflow()
    started = start(service, opened)
    with pytest.raises(ReviewWorkflowError, match="belong"):
        service.approve_candidate(approve_command(
            replace(started, candidate_ids=("other",)), item
        ))
    mismatched = candidate("artifact-other")
    with pytest.raises(ReviewWorkflowError, match="artifact"):
        service.approve_candidate(approve_command(started, mismatched))

    unsaved = replace(item, candidate_id="candidate-unsaved")
    session = replace(started, candidate_ids=("candidate-unsaved",))
    with pytest.raises(ReviewWorkflowError, match="does not exist"):
        service.approve_candidate(approve_command(session, unsaved))


def test_operator_is_required_and_must_match_session() -> None:
    service, _, _, opened = setup_workflow()
    with pytest.raises(ValueError, match="operator_id"):
        service.start_review(StartReview(opened, " "))
    with pytest.raises(ValueError, match="match"):
        service.start_review(StartReview(opened, "other"))
