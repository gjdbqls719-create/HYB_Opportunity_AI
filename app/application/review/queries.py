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
from app.domain.market_intelligence import ReviewSession


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
    def __init__(self, repository: ReviewSessionRepository) -> None:
        self._repository = repository

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
