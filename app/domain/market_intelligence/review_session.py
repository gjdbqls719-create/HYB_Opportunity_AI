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


class CandidateReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    SKIPPED = "skipped"


class InvalidReviewSessionTransitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateSkipRecord:
    candidate_id: str
    operator_id: str
    reason: str
    skipped_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "operator_id", _required_text(self.operator_id, "operator_id"))
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        object.__setattr__(self, "skipped_at", _aware(self.skipped_at, "skipped_at"))


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
    candidate_statuses: tuple[tuple[str, CandidateReviewStatus], ...] = ()
    skip_records: tuple[CandidateSkipRecord, ...] = ()

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
        candidate_statuses = self.candidate_statuses or tuple(
            (candidate_id, CandidateReviewStatus.PENDING) for candidate_id in candidate_ids
        )
        if tuple(candidate_id for candidate_id, _ in candidate_statuses) != candidate_ids:
            raise ValueError("candidate_statuses must match candidate_ids in order")
        candidate_statuses = tuple(
            (candidate_id, CandidateReviewStatus(status))
            for candidate_id, status in candidate_statuses
        )
        skip_records = tuple(self.skip_records)
        if any(not isinstance(record, CandidateSkipRecord) for record in skip_records):
            raise TypeError("skip_records must contain CandidateSkipRecord values")
        if any(record.candidate_id not in candidate_ids for record in skip_records):
            raise ValueError("skip record candidate must belong to review session")
        if len({record.candidate_id for record in skip_records}) != len(skip_records):
            raise ValueError("candidate skip records must be unique")
        skipped_ids = {
            candidate_id
            for candidate_id, candidate_status in candidate_statuses
            if candidate_status is CandidateReviewStatus.SKIPPED
        }
        if {record.candidate_id for record in skip_records} != skipped_ids:
            raise ValueError("skip records must match skipped candidate statuses")
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
        object.__setattr__(self, "candidate_statuses", candidate_statuses)
        object.__setattr__(self, "skip_records", skip_records)
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
        if any(status is CandidateReviewStatus.PENDING for _, status in self.candidate_statuses):
            raise InvalidReviewSessionTransitionError(
                "review cannot be completed while candidates are pending"
            )
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

    def mark_candidate(
        self,
        candidate_id: str,
        status: CandidateReviewStatus,
        *,
        operator_id: str,
        skip_record: CandidateSkipRecord | None = None,
    ) -> ReviewSession:
        self.require_reviewable(operator_id=operator_id)
        candidate_id = _required_text(candidate_id, "candidate_id")
        status = CandidateReviewStatus(status)
        current = dict(self.candidate_statuses)
        if candidate_id not in current:
            raise ValueError("candidate does not belong to review session")
        if current[candidate_id] is not CandidateReviewStatus.PENDING:
            raise InvalidReviewSessionTransitionError("candidate already reviewed")
        if status is CandidateReviewStatus.SKIPPED:
            if skip_record is None or skip_record.candidate_id != candidate_id:
                raise ValueError("skipped candidate requires matching skip record")
            if skip_record.operator_id != self.operator_id:
                raise ValueError("skip record operator must match review session operator")
            if skip_record.skipped_at < self.created_at:
                raise ValueError("skipped_at cannot precede review creation")
        elif skip_record is not None:
            raise ValueError("skip record is only valid for skipped candidate")
        return replace(
            self,
            candidate_statuses=tuple(
                (item_id, status if item_id == candidate_id else item_status)
                for item_id, item_status in self.candidate_statuses
            ),
            skip_records=(
                self.skip_records + (skip_record,)
                if skip_record is not None
                else self.skip_records
            ),
        )

    def _require_operator(self, operator_id: str) -> None:
        if _required_text(operator_id, "operator_id") != self.operator_id:
            raise ValueError("operator_id must match review session operator")
