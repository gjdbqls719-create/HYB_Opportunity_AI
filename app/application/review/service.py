from __future__ import annotations

from typing import Any

from app.application.external_signal import (
    CreateExternalSignal as BuildExternalSignal,
    ExternalSignalTrustService,
    VerifyOCRCandidate,
)
from app.application.external_signal_ledger import ExternalSignalLedgerRepository
from app.application.review.models import (
    CandidateReviewResult,
    DuplicateCandidateReviewError,
    ReviewWorkflowError,
    ReviewPersistenceError,
    SkipCandidateResult,
)
from app.application.review.ports import MarketObservationRepository, VerifiedSignalPersistence
from app.application.review.use_cases import (
    ApproveCandidate,
    CancelReview,
    CompleteReview,
    CorrectCandidate,
    CreateReviewSession,
    StartReview,
    SkipCandidate,
)
from app.domain.market_intelligence import (
    CandidateReviewStatus,
    CandidateSkipRecord,
    InvalidReviewSessionTransitionError,
    OCRCandidate,
    ReviewSession,
    ReviewSessionStatus,
)


class ReviewWorkflowService:
    def __init__(
        self,
        ledger: ExternalSignalLedgerRepository,
        *,
        trust_service: ExternalSignalTrustService | None = None,
        observation_repository: MarketObservationRepository | None = None,
        persistence: VerifiedSignalPersistence | None = None,
    ) -> None:
        if not isinstance(ledger, ExternalSignalLedgerRepository):
            raise TypeError("ledger must implement ExternalSignalLedgerRepository")
        self._ledger = ledger
        self._trust = trust_service or ExternalSignalTrustService()
        self._observations = observation_repository
        self._persistence = persistence

    def create_session(self, command: CreateReviewSession) -> ReviewSession:
        return ReviewSession(
            session_id=command.session_id,
            artifact_id=command.artifact_id,
            candidate_ids=command.candidate_ids,
            status=ReviewSessionStatus.OPEN,
            created_at=command.created_at,
            completed_at=None,
            operator_id=command.operator_id,
            schema_version=command.schema_version,
        )

    def start_review(self, command: StartReview) -> ReviewSession:
        return command.session.start(operator_id=command.operator_id)

    def complete_review(self, command: CompleteReview) -> ReviewSession:
        return command.session.complete(
            operator_id=command.operator_id,
            completed_at=command.completed_at,
        )

    def cancel_review(self, command: CancelReview) -> ReviewSession:
        return command.session.cancel(
            operator_id=command.operator_id,
            cancelled_at=command.cancelled_at,
        )

    def approve_candidate(self, command: ApproveCandidate) -> CandidateReviewResult:
        return self._review_candidate(command, command.candidate.normalized_value)

    def correct_candidate(self, command: CorrectCandidate) -> CandidateReviewResult:
        return self._review_candidate(command, command.corrected_value)

    def skip_candidate(self, command: SkipCandidate) -> SkipCandidateResult:
        command.session.require_reviewable(operator_id=command.operator_id)
        self._require_candidate(command.session, command.candidate)
        if not isinstance(command.reason, str) or not command.reason.strip():
            raise ValueError("reason must be non-empty text")
        if command.skipped_at.tzinfo is None or command.skipped_at.utcoffset() is None:
            raise ValueError("skipped_at must be timezone-aware")
        try:
            session = command.session.mark_candidate(
                command.candidate.candidate_id,
                CandidateReviewStatus.SKIPPED,
                operator_id=command.operator_id,
                skip_record=CandidateSkipRecord(
                    candidate_id=command.candidate.candidate_id,
                    operator_id=command.operator_id,
                    reason=command.reason,
                    skipped_at=command.skipped_at,
                ),
            )
        except InvalidReviewSessionTransitionError as error:
            raise DuplicateCandidateReviewError(str(error)) from error
        return SkipCandidateResult(session)

    def _review_candidate(
        self,
        command: ApproveCandidate | CorrectCandidate,
        verified_value: Any,
    ) -> CandidateReviewResult:
        session = command.session
        session.require_reviewable(operator_id=command.operator_id)
        candidate = command.candidate
        self._require_candidate(session, candidate)
        if self._ledger.get_latest_verification(candidate.candidate_id) is not None:
            raise DuplicateCandidateReviewError(
                f"candidate already reviewed: {candidate.candidate_id}"
            )
        status = (
            CandidateReviewStatus.CORRECTED
            if isinstance(command, CorrectCandidate)
            else CandidateReviewStatus.APPROVED
        )
        try:
            reviewed_session = session.mark_candidate(
                candidate.candidate_id, status, operator_id=command.operator_id
            )
        except InvalidReviewSessionTransitionError as error:
            raise DuplicateCandidateReviewError(str(error)) from error
        verification = self._trust.verify_ocr_candidate(VerifyOCRCandidate(
            verification_id=command.verification_id,
            candidate=candidate,
            verified_value=verified_value,
            operator_id=command.operator_id,
            verified_at=command.verified_at,
            comment=command.comment,
            schema_version=command.verification_schema_version,
        ))
        signal = self._trust.create_external_signal(BuildExternalSignal(
            signal_id=command.signal_id,
            identity=command.identity,
            candidate=candidate,
            verification=verification,
            signal_name=command.signal_name,
            signal_direction=command.signal_direction,
            confidence=command.confidence,
            schema_version=command.signal_schema_version,
        ))
        try:
            if self._persistence is not None:
                self._persistence.save(verification, signal)
            else:
                self._ledger.save_verification(verification)
                if self._observations is None:
                    raise ReviewPersistenceError(
                        "market observation repository is required",
                        partial_completion=True,
                    )
                try:
                    self._observations.save(signal)
                except Exception as error:
                    raise ReviewPersistenceError(
                        "verification saved but external signal persistence failed",
                        partial_completion=True,
                    ) from error
        except ReviewPersistenceError:
            raise
        except Exception as error:
            raise ReviewPersistenceError(
                "verified signal workflow persistence failed",
                partial_completion=False,
            ) from error
        return CandidateReviewResult(reviewed_session, verification, signal)

    def _require_candidate(self, session: ReviewSession, candidate: OCRCandidate) -> None:
        if candidate.candidate_id not in session.candidate_ids:
            raise ReviewWorkflowError("candidate does not belong to review session")
        if candidate.artifact.artifact_id != session.artifact_id:
            raise ReviewWorkflowError("candidate artifact does not match review session")
        history = self._ledger.get_candidate_history(
            candidate.artifact.artifact_id,
            candidate.field_name,
        )
        if candidate not in history:
            raise ReviewWorkflowError("candidate does not exist in ledger")
