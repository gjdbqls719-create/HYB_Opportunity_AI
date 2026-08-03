from datetime import timedelta

import pytest

from app.application.review import (
    ApproveCandidateCommand,
    CancelReviewCommand,
    CreateReviewSession,
    GetReviewCancelMetadata,
    GetReviewCommandContext,
    GetReviewCommandReceipt,
    MalformedReviewSessionError,
    ReviewCommandConflictError,
    ReviewCommandContext,
    ReviewCommandReceipt,
    ReviewHistoryError,
    ReviewSessionQueryService,
    ReviewWorkflowService,
    StartReviewCommand,
    UnsupportedReviewSessionVersionError,
)
from app.infrastructure.review import SQLiteReviewSessionRepository, SQLiteVerifiedSignalPersistence
from tests.test_review_session_persistence import NOW, candidate, identity


def setup(path):
    persistence = SQLiteVerifiedSignalPersistence(path)
    item = candidate()
    persistence.ledger.save_candidate(item)
    service = ReviewWorkflowService(persistence.ledger, persistence=persistence)
    opened = service.create_session(CreateReviewSession(
        "review-1", "artifact-1", ("candidate-1",), "founder-1", NOW,
        command_id="create-1",
    ))
    context = ReviewCommandContext(
        session_id="review-1",
        candidate_id="candidate-1",
        market_observation_identity=identity(),
        signal_name="search volume",
        signal_direction="positive",
        artifact_identity="artifact-1",
        created_at=NOW,
    )
    service.save_command_context(context)
    return persistence, service, opened, context


def complete_state(connection):
    tables = (
        "ocr_candidate_history",
        "ocr_candidate_current",
        "human_verification_history",
        "human_verification_current",
        "market_observation_history",
        "market_observation_current",
        "review_session_history",
        "review_session_current",
        "review_command_context_history",
        "review_command_context_current",
        "review_command_receipts",
        "review_cancel_metadata",
    )
    return tuple(
        tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
        for table in tables
    )


def test_context_persistence_immutability_and_restart_round_trip(tmp_path) -> None:
    path = tmp_path / "context.db"
    persistence, service, _, context = setup(path)
    assert service.save_command_context(context) == context
    with pytest.raises(Exception, match="immutable"):
        persistence._connection.execute(
            "UPDATE review_command_context_current SET projected_at = projected_at"
        )
    with pytest.raises(Exception, match="immutable"):
        persistence._connection.execute("DELETE FROM review_command_context_history")
    persistence.close()
    restarted = SQLiteReviewSessionRepository(path)
    assert restarted.get_context("review-1", "candidate-1") == context


def test_context_drives_approve_and_receipt_restart_replay(tmp_path) -> None:
    path = tmp_path / "receipt.db"
    persistence, service, opened, _ = setup(path)
    started = service.start_review(StartReviewCommand(
        "review-1", opened.revision, "start-1", "founder-1", NOW
    ))
    command = ApproveCandidateCommand(
        session_id="review-1",
        candidate_id="candidate-1",
        expected_revision=started.revision,
        command_id="approve-1",
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        signal_id="signal-1",
    )
    result = service.approve_candidate(command)
    receipt = persistence.sessions.get_receipt("approve-1")
    assert receipt == ReviewCommandReceipt(
        command_id="approve-1",
        session_id="review-1",
        candidate_id="candidate-1",
        transition_type="approved",
        resulting_revision=result.session.revision,
        verification_id="verification-1",
        external_signal_id="signal-1",
        transition_timestamp=NOW + timedelta(minutes=1),
        completed_at=None,
    )
    with pytest.raises(Exception, match="immutable"):
        persistence._connection.execute(
            "UPDATE review_command_receipts SET payload_json = payload_json"
        )
    persistence._connection.rollback()
    with pytest.raises(Exception, match="immutable"):
        persistence._connection.execute("DELETE FROM review_command_receipts")
    persistence._connection.rollback()
    persistence.close()

    restarted = SQLiteVerifiedSignalPersistence(path)
    restarted_service = ReviewWorkflowService(restarted.ledger, persistence=restarted)
    replay = restarted_service.approve_candidate(command)
    assert replay == result
    assert len(restarted.ledger.get_verification_history("candidate-1")) == 1
    assert len(restarted.sessions.get_history("review-1")) == 3


def test_receipt_failure_rolls_back_verification_signal_and_session(tmp_path) -> None:
    persistence, service, opened, _ = setup(tmp_path / "rollback.db")
    started = service.start_review(StartReviewCommand(
        "review-1", opened.revision, "start-1", "founder-1", NOW
    ))
    before = complete_state(persistence._connection)
    persistence._connection.execute(
        """CREATE TRIGGER fail_receipt BEFORE INSERT ON review_command_receipts
        BEGIN SELECT RAISE(ABORT, 'receipt failure'); END"""
    )
    command = ApproveCandidateCommand(
        session_id="review-1",
        candidate_id="candidate-1",
        expected_revision=started.revision,
        command_id="approve-1",
        verification_id="verification-1",
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        signal_id="signal-1",
    )
    with pytest.raises(ReviewHistoryError):
        service.approve_candidate(command)
    assert complete_state(persistence._connection) == before
    assert persistence._connection.in_transaction is False


def test_cancel_metadata_is_immutable_and_restart_safe(tmp_path) -> None:
    path = tmp_path / "cancel.db"
    persistence, service, opened, _ = setup(path)
    command = CancelReviewCommand(
        "review-1", opened.revision, "cancel-1", "founder-1",
        NOW + timedelta(minutes=1), "duplicate artifact",
    )
    cancelled = service.cancel_review(command)
    metadata = persistence.sessions.get_cancel_metadata("review-1")
    assert metadata.reason == "duplicate artifact"
    assert metadata.cancelled_at == NOW + timedelta(minutes=1)
    assert metadata.revision == cancelled.revision
    with pytest.raises(Exception, match="immutable"):
        persistence._connection.execute("DELETE FROM review_cancel_metadata")
    persistence.close()
    restarted = SQLiteReviewSessionRepository(path)
    assert restarted.get_cancel_metadata("review-1") == metadata


def test_context_receipt_cancel_queries_are_read_only(tmp_path) -> None:
    persistence, service, opened, context = setup(tmp_path / "queries.db")
    service.cancel_review(CancelReviewCommand(
        "review-1", opened.revision, "cancel-1", "founder-1", NOW, "reason"
    ))
    query = ReviewSessionQueryService(persistence.sessions)
    before = complete_state(persistence._connection)
    first = (
        query.context(GetReviewCommandContext("review-1", "candidate-1")),
        query.receipt(GetReviewCommandReceipt("cancel-1")),
        query.cancel_metadata(GetReviewCancelMetadata("review-1")),
    )
    second = (
        query.context(GetReviewCommandContext("review-1", "candidate-1")),
        query.receipt(GetReviewCommandReceipt("cancel-1")),
        query.cancel_metadata(GetReviewCancelMetadata("review-1")),
    )
    assert first == second
    assert first[0] == context
    assert complete_state(persistence._connection) == before
    assert persistence._connection.in_transaction is False


@pytest.mark.parametrize("kind", ("context", "receipt"))
def test_malformed_and_unsupported_context_receipt_are_explicit(tmp_path, kind) -> None:
    persistence, _, _, _ = setup(tmp_path / f"malformed-{kind}.db")
    connection = persistence._connection
    if kind == "context":
        connection.execute("DROP TRIGGER trg_review_command_context_current_no_update")
        connection.execute(
            """UPDATE review_command_context_current SET payload_json = ?
            WHERE session_id = 'review-1' AND candidate_id = 'candidate-1'""",
            ('{"schema_version":"future"}',),
        )
        with pytest.raises(UnsupportedReviewSessionVersionError):
            persistence.sessions.get_context("review-1", "candidate-1")
        connection.execute(
            """UPDATE review_command_context_current SET payload_json = ?
            WHERE session_id = 'review-1' AND candidate_id = 'candidate-1'""",
            ('{',),
        )
        with pytest.raises(MalformedReviewSessionError):
            persistence.sessions.get_context("review-1", "candidate-1")
    else:
        connection.execute("DROP TRIGGER trg_review_command_receipts_no_update")
        connection.execute(
            "UPDATE review_command_receipts SET payload_json = ? WHERE command_id = 'create-1'",
            ('{"schema_version":"future"}',),
        )
        with pytest.raises(UnsupportedReviewSessionVersionError):
            persistence.sessions.get_receipt("create-1")
        connection.execute(
            "UPDATE review_command_receipts SET payload_json = ? WHERE command_id = 'create-1'",
            ('{',),
        )
        with pytest.raises(MalformedReviewSessionError):
            persistence.sessions.get_receipt("create-1")


def test_duplicate_receipt_payload_conflict(tmp_path) -> None:
    persistence, _, opened, _ = setup(tmp_path / "duplicate.db")
    receipt = persistence.sessions.get_receipt("create-1")
    assert persistence.sessions.save_receipt(
        receipt, persistence.sessions.get_history("review-1")[0].metadata.command_fingerprint
    ) == receipt
    with pytest.raises(ReviewCommandConflictError):
        persistence.sessions.get_receipt("create-1", "changed")
