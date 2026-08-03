from __future__ import annotations

from dataclasses import dataclass

from app.application.review.models import (
    ReviewCancelMetadata,
    ReviewCommandContext,
    ReviewCommandReceipt,
    ReviewSessionHistoryEntry,
    ReviewSessionNotFoundError,
)
from app.application.review.ports import ReviewSessionRepository
from app.application.external_signal_ledger import ExternalSignalLedgerRepository
from app.domain.market_intelligence import (
    CandidateReviewStatus,
    CandidateSkipRecord,
    OCRCandidate,
    ReviewSession,
)


@dataclass(frozen=True, slots=True)
class GetReviewSession:
    session_id: str


@dataclass(frozen=True, slots=True)
class ListReviewSessions:
    pass


@dataclass(frozen=True, slots=True)
class GetReviewSessionHistory:
    session_id: str


@dataclass(frozen=True, slots=True)
class GetReviewSessionDetail:
    session_id: str


@dataclass(frozen=True, slots=True)
class ReviewCandidateDetail:
    candidate: OCRCandidate
    status: CandidateReviewStatus
    context: ReviewCommandContext | None
    skip_record: CandidateSkipRecord | None


@dataclass(frozen=True, slots=True)
class ReviewSessionDetail:
    session: ReviewSession
    candidates: tuple[ReviewCandidateDetail, ...]


@dataclass(frozen=True, slots=True)
class GetReviewCommandContext:
    session_id: str
    candidate_id: str


@dataclass(frozen=True, slots=True)
class GetReviewCommandReceipt:
    command_id: str


@dataclass(frozen=True, slots=True)
class GetReviewCancelMetadata:
    session_id: str


class ReviewSessionQueryService:
    def __init__(
        self,
        repository: ReviewSessionRepository,
        candidate_repository: ExternalSignalLedgerRepository | None = None,
    ) -> None:
        self._repository = repository
        self._candidates = candidate_repository

    def get(self, query: GetReviewSession) -> ReviewSession:
        session = self._repository.get(query.session_id)
        if session is None:
            raise ReviewSessionNotFoundError(query.session_id)
        return session

    def list(self, _query: ListReviewSessions = ListReviewSessions()) -> tuple[ReviewSession, ...]:
        return self._repository.list()

    def history(self, query: GetReviewSessionHistory) -> tuple[ReviewSessionHistoryEntry, ...]:
        if self._repository.get(query.session_id) is None:
            raise ReviewSessionNotFoundError(query.session_id)
        return self._repository.get_history(query.session_id)

    def detail(self, query: GetReviewSessionDetail) -> ReviewSessionDetail:
        session = self.get(GetReviewSession(query.session_id))
        if self._candidates is None:
            raise ReviewSessionNotFoundError("review candidate repository unavailable")
        statuses = dict(session.candidate_statuses)
        skip_records = {value.candidate_id: value for value in session.skip_records}
        details = []
        for candidate_id in session.candidate_ids:
            candidate = self._candidates.get_candidate(candidate_id)
            if candidate is None:
                raise ReviewSessionNotFoundError(
                    f"review candidate not found: {candidate_id}"
                )
            details.append(ReviewCandidateDetail(
                candidate=candidate,
                status=statuses[candidate_id],
                context=self._repository.get_context(session.session_id, candidate_id),
                skip_record=skip_records.get(candidate_id),
            ))
        return ReviewSessionDetail(session=session, candidates=tuple(details))

    def context(self, query: GetReviewCommandContext) -> ReviewCommandContext:
        value = self._repository.get_context(query.session_id, query.candidate_id)
        if value is None:
            raise ReviewSessionNotFoundError(
                f"review command context not found: {query.session_id}/{query.candidate_id}"
            )
        return value

    def receipt(self, query: GetReviewCommandReceipt) -> ReviewCommandReceipt:
        value = self._repository.get_receipt(query.command_id)
        if value is None:
            raise ReviewSessionNotFoundError(f"review command receipt not found: {query.command_id}")
        return value

    def cancel_metadata(self, query: GetReviewCancelMetadata) -> ReviewCancelMetadata:
        value = self._repository.get_cancel_metadata(query.session_id)
        if value is None:
            raise ReviewSessionNotFoundError(f"review cancel metadata not found: {query.session_id}")
        return value
