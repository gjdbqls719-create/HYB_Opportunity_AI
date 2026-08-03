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
    ReviewPersistenceError,
    SkipCandidate,
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
from app.application.market_observation import MarketObservationType
from app.infrastructure.review import SQLiteVerifiedSignalPersistence


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
    persistence = SQLiteVerifiedSignalPersistence(":memory:")
    ledger = persistence.ledger
    item = candidate()
    ledger.save_candidate(item)
    service = ReviewWorkflowService(ledger, persistence=persistence)
    session = service.create_session(CreateReviewSession(
        session_id="session-1",
        artifact_id="artifact-1",
        candidate_ids=("candidate-1",),
        operator_id="founder-1",
        created_at=NOW,
    ))
    return service, persistence, item, session


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
    service, _, item, opened = setup_workflow()
    reviewed = service.approve_candidate(approve_command(start(service, opened), item)).session
    completed = service.complete_review(CompleteReview(
        reviewed, "founder-1", NOW + timedelta(minutes=2)
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
    service, persistence, item, opened = setup_workflow()
    ledger = persistence.ledger
    before = candidate()
    started = start(service, opened)
    result = service.approve_candidate(approve_command(started, item))
    assert item == before
    assert dict(result.session.candidate_statuses)["candidate-1"].value == "approved"
    assert result.verification.verified_value == 1234
    assert ledger.get_latest_verification("candidate-1") == result.verification
    assert result.signal.evidence.status is MarketEvidenceStatus.HUMAN_VERIFIED
    assert result.signal.evidence.value == 1234
    assert result.signal.candidate_id == "candidate-1"
    assert result.signal.verification_id == "verification-1"
    assert persistence.observations.get_latest(
        MarketObservationType.EXTERNAL_SIGNAL, identity()
    ) == result.signal


def test_correct_uses_human_value_without_mutating_candidate() -> None:
    service, persistence, item, opened = setup_workflow()
    ledger = persistence.ledger
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
    assert persistence.observations.get_history(
        MarketObservationType.EXTERNAL_SIGNAL, identity()
    ) == (result.signal,)


def test_duplicate_approve_is_rejected_without_second_history_fact() -> None:
    service, persistence, item, opened = setup_workflow()
    ledger = persistence.ledger
    started = start(service, opened)
    service.approve_candidate(approve_command(started, item))
    with pytest.raises(DuplicateCandidateReviewError):
        service.approve_candidate(approve_command(
            started, item, verification_id="verification-2", signal_id="signal-2"
        ))
    assert len(ledger.get_verification_history("candidate-1")) == 1


def test_duplicate_correct_is_rejected_without_second_history_fact() -> None:
    service, persistence, item, opened = setup_workflow()
    started = start(service, opened)
    command = CorrectCandidate(
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
    )
    service.correct_candidate(command)
    with pytest.raises(DuplicateCandidateReviewError):
        service.correct_candidate(replace(
            command, verification_id="verification-2", signal_id="signal-2"
        ))
    assert len(persistence.ledger.get_verification_history("candidate-1")) == 1


@pytest.mark.parametrize("terminal", (ReviewSessionStatus.COMPLETED, ReviewSessionStatus.CANCELLED))
def test_terminal_session_rejects_candidate_changes(terminal: ReviewSessionStatus) -> None:
    service, _, item, opened = setup_workflow()
    if terminal is ReviewSessionStatus.COMPLETED:
        reviewed = service.approve_candidate(approve_command(start(service, opened), item)).session
        terminal_session = service.complete_review(CompleteReview(
            reviewed, "founder-1", NOW + timedelta(minutes=2)
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
            replace(started, candidate_ids=("other",), candidate_statuses=()), item
        ))
    mismatched = candidate("artifact-other")
    with pytest.raises(ReviewWorkflowError, match="artifact"):
        service.approve_candidate(approve_command(started, mismatched))

    unsaved = replace(item, candidate_id="candidate-unsaved")
    session = replace(
        started,
        candidate_ids=("candidate-unsaved",),
        candidate_statuses=(),
    )
    with pytest.raises(ReviewWorkflowError, match="does not exist"):
        service.approve_candidate(approve_command(session, unsaved))


def test_operator_is_required_and_must_match_session() -> None:
    service, _, _, opened = setup_workflow()
    with pytest.raises(ValueError, match="operator_id"):
        service.start_review(StartReview(opened, " "))
    with pytest.raises(ValueError, match="match"):
        service.start_review(StartReview(opened, "other"))


def test_pending_candidate_prevents_completion() -> None:
    service, _, _, opened = setup_workflow()
    with pytest.raises(InvalidReviewSessionTransitionError, match="pending"):
        service.complete_review(CompleteReview(
            start(service, opened), "founder-1", NOW + timedelta(minutes=2)
        ))


def test_skip_allows_completion_without_creating_facts() -> None:
    service, persistence, item, opened = setup_workflow()
    before = item
    skipped = service.skip_candidate(SkipCandidate(
        session=start(service, opened),
        candidate=item,
        operator_id="founder-1",
        reason="not relevant",
        skipped_at=NOW + timedelta(minutes=1),
    )).session
    completed = service.complete_review(CompleteReview(
        skipped, "founder-1", NOW + timedelta(minutes=2)
    ))
    assert completed.status is ReviewSessionStatus.COMPLETED
    assert item == before
    assert skipped.skip_records[0].reason == "not relevant"
    assert skipped.skip_records[0].skipped_at == NOW + timedelta(minutes=1)
    assert persistence.ledger.get_verification_history("candidate-1") == ()
    assert persistence.observations.get_history(
        MarketObservationType.EXTERNAL_SIGNAL, identity()
    ) == ()


def test_duplicate_skip_is_rejected() -> None:
    service, _, item, opened = setup_workflow()
    command = SkipCandidate(
        start(service, opened), item, "founder-1", "irrelevant", NOW
    )
    skipped = service.skip_candidate(command).session
    with pytest.raises(DuplicateCandidateReviewError):
        service.skip_candidate(replace(command, session=skipped))


def test_skipped_candidate_cannot_be_approved_or_persisted() -> None:
    service, persistence, item, opened = setup_workflow()
    skipped = service.skip_candidate(SkipCandidate(
        start(service, opened), item, "founder-1", "irrelevant", NOW
    )).session
    with pytest.raises(DuplicateCandidateReviewError):
        service.approve_candidate(approve_command(skipped, item))
    assert persistence.ledger.get_verification_history("candidate-1") == ()
    assert persistence.observations.get_history(
        MarketObservationType.EXTERNAL_SIGNAL, identity()
    ) == ()


def test_atomic_persistence_rolls_back_verification_when_signal_save_fails() -> None:
    service, persistence, item, opened = setup_workflow()
    persistence.observations.save = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("signal unavailable")
    )
    with pytest.raises(ReviewPersistenceError) as captured:
        service.approve_candidate(approve_command(start(service, opened), item))
    assert captured.value.partial_completion is False
    assert persistence.ledger.get_verification_history("candidate-1") == ()


@pytest.mark.parametrize(
    "table_name",
    (
        "human_verification_history",
        "human_verification_current",
        "market_observation_history",
        "market_observation_current",
    ),
)
def test_atomic_persistence_rolls_back_each_insert_failure(table_name) -> None:
    service, persistence, item, opened = setup_workflow()
    persistence._connection.execute(
        f"""CREATE TRIGGER fail_{table_name}
        BEFORE INSERT ON {table_name}
        BEGIN SELECT RAISE(ABORT, 'forced failure'); END"""
    )
    with pytest.raises(ReviewPersistenceError):
        service.approve_candidate(approve_command(start(service, opened), item))
    assert _review_fact_counts(persistence) == (0, 0, 0, 0)
    assert persistence._connection.in_transaction is False


def test_atomic_persistence_rolls_back_commit_failure() -> None:
    service, persistence, item, opened = setup_workflow()
    connection = persistence._connection
    connection.execute("CREATE TABLE commit_parent (id INTEGER PRIMARY KEY)")
    connection.execute(
        """CREATE TABLE commit_child (
        id INTEGER PRIMARY KEY,
        parent_id INTEGER,
        FOREIGN KEY (parent_id) REFERENCES commit_parent(id)
            DEFERRABLE INITIALLY DEFERRED
        )"""
    )
    connection.execute(
        """CREATE TRIGGER fail_review_commit
        AFTER INSERT ON market_observation_current
        BEGIN INSERT INTO commit_child (id, parent_id) VALUES (1, 999); END"""
    )
    with pytest.raises(ReviewPersistenceError):
        service.approve_candidate(approve_command(start(service, opened), item))
    assert _review_fact_counts(persistence) == (0, 0, 0, 0)
    assert connection.in_transaction is False


def _review_fact_counts(persistence) -> tuple[int, int, int, int]:
    return tuple(
        persistence._connection.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]
        for table_name in (
            "human_verification_history",
            "human_verification_current",
            "market_observation_history",
            "market_observation_current",
        )
    )


def test_verification_is_immutable() -> None:
    service, _, item, opened = setup_workflow()
    verification = service.approve_candidate(
        approve_command(start(service, opened), item)
    ).verification
    with pytest.raises(FrozenInstanceError):
        verification.verified_value = 1  # type: ignore[misc]


def test_same_context_multi_candidate_review_persists_independent_signals() -> None:
    shared_artifact = artifact()
    candidates = tuple(
        OCRCandidate(
            candidate_id=f"candidate-{index}",
            artifact=shared_artifact,
            field_name=field_name,
            raw_text=str(index),
            normalized_value=index,
            confidence=Decimal("0.8"),
            captured_at=NOW + timedelta(seconds=index),
            schema_version="ocr-candidate-v1",
        )
        for index, field_name in enumerate(
            (OCRField.SEARCH_VOLUME, OCRField.RATING, OCRField.REVIEW_COUNT), start=1
        )
    )
    persistence = SQLiteVerifiedSignalPersistence(":memory:")
    for item in candidates:
        persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    session = start(service, service.create_session(CreateReviewSession(
        "session-multi",
        shared_artifact.artifact_id,
        tuple(item.candidate_id for item in candidates),
        "founder-1",
        NOW,
    )))
    signal_names = ("search volume", "rating", "review count")
    results = []
    for index, (item, signal_name) in enumerate(zip(candidates, signal_names), start=1):
        command = approve_command(
            session,
            item,
            verification_id=f"verification-{index}",
            verified_at=NOW + timedelta(minutes=index),
            signal_id=f"signal-{index}",
            signal_name=signal_name,
        )
        result = (
            service.correct_candidate(CorrectCandidate(
                session=command.session,
                candidate=command.candidate,
                corrected_value=45,
                verification_id=command.verification_id,
                operator_id=command.operator_id,
                verified_at=command.verified_at,
                identity=command.identity,
                signal_id=command.signal_id,
                signal_name=command.signal_name,
                signal_direction=command.signal_direction,
            ))
            if index == 2
            else service.approve_candidate(command)
        )
        session = result.session
        results.append(result)
    completed = service.complete_review(CompleteReview(
        session, "founder-1", NOW + timedelta(minutes=5)
    ))

    assert completed.status is ReviewSessionStatus.COMPLETED
    assert sum(
        len(persistence.ledger.get_verification_history(item.candidate_id))
        for item in candidates
    ) == 3
    history = persistence.observations.get_history(
        MarketObservationType.EXTERNAL_SIGNAL, identity()
    )
    assert len(history) == 3
    assert {signal.candidate_id for signal in history} == {
        item.candidate_id for item in candidates
    }
    assert {signal.verification_id for signal in history} == {
        f"verification-{index}" for index in range(1, 4)
    }
    assert {signal.signal_name for signal in history} == set(signal_names)
    for result in results:
        assert persistence.observations.get_latest(
            MarketObservationType.EXTERNAL_SIGNAL,
            identity(),
            signal_name=result.signal.signal_name,
        ) == result.signal
    assert results[0].signal in history
    with pytest.raises(InvalidReviewSessionTransitionError):
        service.approve_candidate(approve_command(completed, candidates[0]))


def test_skip_rejects_candidate_with_mismatched_artifact() -> None:
    service, _, item, opened = setup_workflow()
    mismatched = replace(item, artifact=artifact("artifact-other"))
    with pytest.raises(ReviewWorkflowError, match="artifact"):
        service.skip_candidate(SkipCandidate(
            start(service, opened), mismatched, "founder-1", "irrelevant", NOW
        ))
