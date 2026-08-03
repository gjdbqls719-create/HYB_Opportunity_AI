from __future__ import annotations

import hashlib
from dataclasses import replace
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
    PendingCandidatesError,
    ReviewArtifactMismatchError,
    ReviewCancelMetadata,
    ReviewCandidateMembershipError,
    ReviewCandidateNotFoundError,
    ReviewOperatorMismatchError,
    ReviewCommandContext,
    ReviewCommandReceipt,
    ReviewPersistenceError,
    ReviewSessionNotFoundError,
    ReviewSessionPersistenceError,
    ReviewTransitionMetadata,
    SkipCandidateResult,
)
from app.application.review.ports import (
    MarketObservationRepository,
    ReviewSessionRepository,
    VerifiedSignalPersistence,
)
from app.application.review.use_cases import (
    ApproveCandidate,
    ApproveCandidateCommand,
    CancelReview,
    CancelReviewCommand,
    CompleteReview,
    CompleteReviewCommand,
    CorrectCandidate,
    CorrectCandidateCommand,
    CreateReviewSession,
    SkipCandidate,
    SkipCandidateCommand,
    StartReview,
    StartReviewCommand,
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
        session_repository: ReviewSessionRepository | None = None,
    ) -> None:
        if not isinstance(ledger, ExternalSignalLedgerRepository):
            raise TypeError("ledger must implement ExternalSignalLedgerRepository")
        self._ledger = ledger
        self._trust = trust_service or ExternalSignalTrustService()
        self._observations = observation_repository
        self._persistence = persistence
        self._sessions = session_repository or getattr(persistence, "sessions", None)

    def create_session(self, command: CreateReviewSession) -> ReviewSession:
        if command.contexts is not None:
            context_candidate_ids = tuple(
                context.candidate_id for context in command.contexts
            )
            if (
                len(set(context_candidate_ids)) != len(context_candidate_ids)
                or set(context_candidate_ids) != set(command.candidate_ids)
                or any(
                    context.session_id != command.session_id
                    for context in command.contexts
                )
            ):
                from app.application.review.models import ReviewCommandConflictError

                raise ReviewCommandConflictError(
                    "trusted review contexts must match every session candidate"
                )
        if command.opportunity_id is not None:
            for candidate_id in command.candidate_ids:
                candidate = self._ledger.get_candidate(candidate_id)
                if candidate is None:
                    raise ReviewCandidateNotFoundError(candidate_id)
                if candidate.artifact.artifact_id != command.artifact_id:
                    raise ReviewArtifactMismatchError("candidate artifact does not match review session")
        session = ReviewSession(
            session_id=command.session_id,
            artifact_id=command.artifact_id,
            candidate_ids=command.candidate_ids,
            status=ReviewSessionStatus.OPEN,
            created_at=command.created_at,
            completed_at=None,
            operator_id=command.operator_id,
            schema_version=command.schema_version,
        )
        if self._sessions is not None:
            metadata = self._metadata("create", command, command.created_at)
            receipt = self._receipt(command, session, "create", command.created_at)
            create = getattr(self._persistence, "create_session", None)
            if create is not None:
                create(session, metadata, receipt, contexts=command.contexts or (), opportunity_id=command.opportunity_id)
            else:
                self._sessions.create(session, metadata)
        return session

    def save_command_context(self, context: ReviewCommandContext) -> ReviewCommandContext:
        if self._sessions is None:
            raise ReviewSessionNotFoundError(context.session_id)
        return self._sessions.save_context(context)

    def start_review(self, command: StartReview | StartReviewCommand) -> ReviewSession:
        retry = self._committed_retry(command)
        if retry is not None:
            return retry
        previous = self._command_session(command)
        try:
            next_session = previous.start(
                operator_id=command.operator_id,
                started_at=command.started_at,
            )
        except ValueError as error:
            self._raise_operator_mismatch(error)
            raise
        return self._save_transition(previous, next_session, "start", command, next_session.started_at)

    def complete_review(self, command: CompleteReview | CompleteReviewCommand) -> ReviewSession:
        retry = self._committed_retry(command)
        if retry is not None:
            return retry
        previous = self._command_session(command)
        try:
            next_session = previous.complete(
                operator_id=command.operator_id,
                completed_at=command.completed_at,
            )
        except InvalidReviewSessionTransitionError as error:
            if "pending" in str(error):
                raise PendingCandidatesError(str(error)) from error
            raise
        except ValueError as error:
            self._raise_operator_mismatch(error)
            raise
        return self._save_transition(previous, next_session, "complete", command, command.completed_at)

    def cancel_review(self, command: CancelReview | CancelReviewCommand) -> ReviewSession:
        retry = self._committed_retry(command)
        if retry is not None:
            return retry
        previous = self._command_session(command)
        try:
            next_session = previous.cancel(
                operator_id=command.operator_id,
                cancelled_at=command.cancelled_at,
            )
        except ValueError as error:
            self._raise_operator_mismatch(error)
            raise
        return self._save_transition(previous, next_session, "cancel", command, command.cancelled_at)

    def approve_candidate(
        self, command: ApproveCandidate | ApproveCandidateCommand
    ) -> CandidateReviewResult:
        if (
            isinstance(command, ApproveCandidateCommand)
            and self._sessions is not None
            and self._sessions.get(command.session_id) is None
        ):
            raise ReviewSessionNotFoundError(command.session_id)
        command = self._with_context(command)
        candidate = self._command_candidate(command)
        return self._review_candidate(command, candidate, candidate.normalized_value)

    def correct_candidate(
        self, command: CorrectCandidate | CorrectCandidateCommand
    ) -> CandidateReviewResult:
        if (
            isinstance(command, CorrectCandidateCommand)
            and self._sessions is not None
            and self._sessions.get(command.session_id) is None
        ):
            raise ReviewSessionNotFoundError(command.session_id)
        command = self._with_context(command)
        return self._review_candidate(
            command, self._command_candidate(command), command.corrected_value
        )

    def skip_candidate(
        self, command: SkipCandidate | SkipCandidateCommand
    ) -> SkipCandidateResult:
        retry = self._committed_retry(command)
        if retry is not None:
            return SkipCandidateResult(retry)
        candidate = self._command_candidate(command)
        if isinstance(command, SkipCandidate):
            self._require_candidate(command.session, candidate)
        previous = self._command_session(command)
        try:
            previous.require_reviewable(operator_id=command.operator_id)
        except ValueError as error:
            self._raise_operator_mismatch(error)
            raise
        self._require_candidate(previous, candidate)
        if not isinstance(command.reason, str) or not command.reason.strip():
            raise ValueError("reason must be non-empty text")
        if command.skipped_at.tzinfo is None or command.skipped_at.utcoffset() is None:
            raise ValueError("skipped_at must be timezone-aware")
        try:
            session = previous.mark_candidate(
                candidate.candidate_id,
                CandidateReviewStatus.SKIPPED,
                operator_id=command.operator_id,
                skip_record=CandidateSkipRecord(
                    candidate_id=candidate.candidate_id,
                    operator_id=command.operator_id,
                    reason=command.reason,
                    skipped_at=command.skipped_at,
                ),
            )
        except InvalidReviewSessionTransitionError as error:
            raise DuplicateCandidateReviewError(str(error)) from error
        session = self._save_transition(
            previous, session, "skip", command, command.skipped_at
        )
        return SkipCandidateResult(session)

    def _review_candidate(
        self,
        command: ApproveCandidate | CorrectCandidate | ApproveCandidateCommand | CorrectCandidateCommand,
        candidate: OCRCandidate,
        verified_value: Any,
    ) -> CandidateReviewResult:
        retry = self._committed_retry(command)
        if retry is not None:
            receipt = (
                self._sessions.get_receipt(command.command_id)
                if self._sessions is not None and getattr(command, "command_id", None)
                else None
            )
            receipt_candidate_id = receipt.candidate_id if receipt is not None else candidate.candidate_id
            verification = self._ledger.get_latest_verification(receipt_candidate_id)
            signal_id = receipt.external_signal_id if receipt is not None else command.signal_id
            signals = (
                getattr(self._persistence, "observations", None) or self._observations
            ).get_human_verified_external_signals_by_ids(
                command.identity,
                (signal_id,),
            )
            signal = signals[0] if len(signals) == 1 else None
            if (
                verification is None
                or verification.verification_id != (
                    receipt.verification_id if receipt is not None else command.verification_id
                )
                or signal is None
                or signal.signal_id != signal_id
            ):
                raise ReviewPersistenceError(
                    "committed review command facts cannot be reconstituted",
                    partial_completion=False,
                )
            return CandidateReviewResult(retry, verification, signal)
        if isinstance(command, (ApproveCandidate, CorrectCandidate)):
            command.session.require_reviewable(operator_id=command.operator_id)
            self._require_candidate(command.session, candidate)
        if self._ledger.get_latest_verification(candidate.candidate_id) is not None:
            raise DuplicateCandidateReviewError(
                f"candidate already reviewed: {candidate.candidate_id}"
            )
        session = self._command_session(command)
        try:
            session.require_reviewable(operator_id=command.operator_id)
        except ValueError as error:
            self._raise_operator_mismatch(error)
            raise
        self._require_candidate(session, candidate)
        status = (
            CandidateReviewStatus.CORRECTED
            if isinstance(command, (CorrectCandidate, CorrectCandidateCommand))
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
                metadata = self._metadata(
                    status.value,
                    command,
                    command.verified_at,
                )
                self._persistence.save(
                    verification,
                    signal,
                    previous_session=session if self._sessions is not None else None,
                    next_session=reviewed_session if self._sessions is not None else None,
                    transition_metadata=metadata if self._sessions is not None else None,
                    receipt=(
                        self._receipt(
                            command,
                            reviewed_session,
                            status.value,
                            command.verified_at,
                            verification_id=verification.verification_id,
                            external_signal_id=signal.signal_id,
                        )
                        if self._sessions is not None
                        else None
                    ),
                )
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
        except (ReviewPersistenceError, ReviewSessionPersistenceError):
            raise
        except Exception as error:
            raise ReviewPersistenceError(
                "verified signal workflow persistence failed",
                partial_completion=False,
            ) from error
        return CandidateReviewResult(reviewed_session, verification, signal)

    def _authoritative(self, supplied: ReviewSession) -> ReviewSession:
        if self._sessions is None:
            return supplied
        current = self._sessions.get(supplied.session_id)
        if current is None:
            raise ReviewSessionNotFoundError(supplied.session_id)
        if current.revision != supplied.revision:
            from app.application.review.models import ReviewSessionVersionConflictError
            raise ReviewSessionVersionConflictError(supplied.session_id)
        return current

    def _command_session(self, command) -> ReviewSession:
        if hasattr(command, "session"):
            return self._authoritative(command.session)
        if self._sessions is None:
            raise ReviewSessionNotFoundError(command.session_id)
        current = self._sessions.get(command.session_id)
        if current is None:
            raise ReviewSessionNotFoundError(command.session_id)
        if current.revision != command.expected_revision:
            from app.application.review.models import ReviewSessionVersionConflictError
            raise ReviewSessionVersionConflictError(command.session_id)
        return current

    def _command_candidate(self, command) -> OCRCandidate:
        if hasattr(command, "candidate"):
            return command.candidate
        candidate = self._ledger.get_candidate(command.candidate_id)
        if candidate is None:
            raise ReviewCandidateNotFoundError("candidate does not exist in ledger")
        return candidate

    def _with_context(self, command):
        if not isinstance(command, (ApproveCandidateCommand, CorrectCandidateCommand)):
            return command
        context = (
            self._sessions.get_context(command.session_id, command.candidate_id)
            if self._sessions is not None
            else None
        )
        if context is None:
            if command.identity is None or command.signal_name is None or command.signal_direction is None:
                from app.application.review.models import ReviewCommandConflictError

                raise ReviewCommandConflictError(
                    f"review command context not found: {command.session_id}/{command.candidate_id}"
                )
            return command
        supplied = (command.identity, command.signal_name, command.signal_direction)
        authoritative = (
            context.market_observation_identity,
            context.signal_name,
            context.signal_direction,
        )
        if any(value is not None for value in supplied) and supplied != authoritative:
            from app.application.review.models import ReviewCommandConflictError
            raise ReviewCommandConflictError("supplied review context conflicts with persistence")
        return replace(
            command,
            identity=context.market_observation_identity,
            signal_name=context.signal_name,
            signal_direction=context.signal_direction,
        )

    @staticmethod
    def _raise_operator_mismatch(error: ValueError) -> None:
        if "operator_id" in str(error) or "operator" in str(error):
            raise ReviewOperatorMismatchError(str(error)) from error

    def _committed_retry(self, command) -> ReviewSession | None:
        command_id = getattr(command, "command_id", None)
        if self._sessions is None or command_id is None:
            return None
        fingerprint = hashlib.sha256(repr(command).encode("utf-8")).hexdigest()
        receipt = self._sessions.get_receipt(command_id, fingerprint)
        if receipt is not None:
            session = self._sessions.get_revision(
                receipt.session_id, receipt.resulting_revision
            )
            if session is None:
                raise ReviewPersistenceError(
                    "committed review receipt session revision is missing",
                    partial_completion=False,
                )
            return session
        return self._sessions.get_command_session(command_id, fingerprint)

    def _save_transition(self, previous, next_session, transition_type, command, occurred_at):
        if self._sessions is None:
            return next_session
        metadata = self._metadata(transition_type, command, occurred_at)
        receipt = self._receipt(command, next_session, transition_type, occurred_at)
        cancel_metadata = None
        if transition_type == "cancel" and getattr(command, "reason", None) is not None:
            cancel_metadata = ReviewCancelMetadata(
                session_id=next_session.session_id,
                reason=command.reason,
                operator_id=command.operator_id,
                cancelled_at=command.cancelled_at,
                revision=next_session.revision,
            )
        save = getattr(self._persistence, "save_session_transition", None)
        if save is not None:
            save(previous, next_session, metadata, receipt, cancel_metadata)
            return next_session
        return self._sessions.save_transition(previous, next_session, metadata)

    @staticmethod
    def _receipt(
        command,
        session: ReviewSession,
        transition_type: str,
        occurred_at,
        *,
        verification_id: str | None = None,
        external_signal_id: str | None = None,
    ) -> ReviewCommandReceipt:
        command_id = getattr(command, "command_id", None)
        if command_id is None:
            command_id = hashlib.sha256(repr(command).encode("utf-8")).hexdigest()
        candidate = getattr(command, "candidate", None)
        candidate_id = getattr(command, "candidate_id", None) or (
            candidate.candidate_id if candidate is not None else None
        )
        return ReviewCommandReceipt(
            command_id=command_id,
            session_id=session.session_id,
            candidate_id=candidate_id,
            transition_type=transition_type,
            resulting_revision=session.revision,
            verification_id=verification_id,
            external_signal_id=external_signal_id,
            transition_timestamp=occurred_at,
            completed_at=session.completed_at,
        )

    @staticmethod
    def _metadata(transition_type: str, command, occurred_at) -> ReviewTransitionMetadata:
        fingerprint = hashlib.sha256(repr(command).encode("utf-8")).hexdigest()
        command_id = getattr(command, "command_id", None) or fingerprint
        return ReviewTransitionMetadata(
            event_id=f"review-event-{command_id}",
            command_id=command_id,
            transition_type=transition_type,
            occurred_at=occurred_at,
            command_fingerprint=fingerprint,
        )

    def _require_candidate(self, session: ReviewSession, candidate: OCRCandidate) -> None:
        if candidate.candidate_id not in session.candidate_ids:
            raise ReviewCandidateMembershipError("candidate does not belong to review session")
        if candidate.artifact.artifact_id != session.artifact_id:
            raise ReviewArtifactMismatchError("candidate artifact does not match review session")
        history = self._ledger.get_candidate_history(
            candidate.artifact.artifact_id,
            candidate.field_name,
        )
        if candidate not in history:
            raise ReviewCandidateNotFoundError("candidate does not exist in ledger")
