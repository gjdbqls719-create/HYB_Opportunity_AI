from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.domain.market_intelligence.artifact import _aware, _required_text


class ReviewSessionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InvalidReviewSessionTransitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewSession:
    """Immutable review aggregate; transitions return a new aggregate value."""

    session_id: str
    artifact_id: str
    candidate_ids: tuple[str, ...]
    status: ReviewSessionStatus
    created_at: datetime
    completed_at: datetime | None
    operator_id: str
    schema_version: str

    def __post_init__(self) -> None:
        try:
            status = ReviewSessionStatus(self.status)
        except ValueError as error:
            raise ValueError("unsupported review session status") from error
        candidate_ids = tuple(_required_text(value, "candidate_id") for value in self.candidate_ids)
        if not candidate_ids:
            raise ValueError("candidate_ids must not be empty")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must be unique")
        created_at = _aware(self.created_at, "created_at")
        completed_at = self.completed_at
        if status in (ReviewSessionStatus.OPEN, ReviewSessionStatus.IN_PROGRESS):
            if completed_at is not None:
                raise ValueError("non-terminal review session cannot have completed_at")
        else:
            if completed_at is None:
                raise ValueError("terminal review session requires completed_at")
            _aware(completed_at, "completed_at")
            if completed_at < created_at:
                raise ValueError("completed_at cannot precede created_at")
        object.__setattr__(self, "session_id", _required_text(self.session_id, "session_id"))
        object.__setattr__(self, "artifact_id", _required_text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "candidate_ids", candidate_ids)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "operator_id", _required_text(self.operator_id, "operator_id"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))

    def start(self, *, operator_id: str) -> ReviewSession:
        self._require_operator(operator_id)
        if self.status is not ReviewSessionStatus.OPEN:
            raise InvalidReviewSessionTransitionError("only open review can be started")
        return replace(self, status=ReviewSessionStatus.IN_PROGRESS)

    def complete(self, *, operator_id: str, completed_at: datetime) -> ReviewSession:
        self._require_operator(operator_id)
        if self.status is not ReviewSessionStatus.IN_PROGRESS:
            raise InvalidReviewSessionTransitionError("only in-progress review can be completed")
        return replace(
            self,
            status=ReviewSessionStatus.COMPLETED,
            completed_at=_aware(completed_at, "completed_at"),
        )

    def cancel(self, *, operator_id: str, cancelled_at: datetime) -> ReviewSession:
        self._require_operator(operator_id)
        if self.status is not ReviewSessionStatus.OPEN:
            raise InvalidReviewSessionTransitionError("only open review can be cancelled")
        return replace(
            self,
            status=ReviewSessionStatus.CANCELLED,
            completed_at=_aware(cancelled_at, "cancelled_at"),
        )

    def require_reviewable(self, *, operator_id: str) -> None:
        self._require_operator(operator_id)
        if self.status is not ReviewSessionStatus.IN_PROGRESS:
            raise InvalidReviewSessionTransitionError(
                "candidate review requires an in-progress session"
            )

    def _require_operator(self, operator_id: str) -> None:
        if _required_text(operator_id, "operator_id") != self.operator_id:
            raise ValueError("operator_id must match review session operator")
