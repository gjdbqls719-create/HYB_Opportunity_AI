"""Read-only API DTOs for Founder Review sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market_intelligence import CandidateReviewStatus, ReviewSession


@dataclass(frozen=True, slots=True)
class ReviewSessionResponseDTO:
    session_id: str
    status: str
    revision: int
    candidate_count: int
    pending_count: int
    completed_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    schema_version: str

    @classmethod
    def from_session(cls, session: ReviewSession) -> ReviewSessionResponseDTO:
        if not isinstance(session, ReviewSession):
            raise TypeError("session must be ReviewSession")
        pending_count = sum(
            status is CandidateReviewStatus.PENDING
            for _, status in session.candidate_statuses
        )
        candidate_count = len(session.candidate_ids)
        return cls(
            session_id=session.session_id,
            status=session.status.value,
            revision=session.revision,
            candidate_count=candidate_count,
            pending_count=pending_count,
            completed_count=candidate_count - pending_count,
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            schema_version=session.schema_version,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "revision": self.revision,
            "candidate_count": self.candidate_count,
            "pending_count": self.pending_count,
            "completed_count": self.completed_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ReviewSessionListResponseDTO:
    items: tuple[ReviewSessionResponseDTO, ...]
    total_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if any(not isinstance(item, ReviewSessionResponseDTO) for item in self.items):
            raise TypeError("items must contain ReviewSessionResponseDTO values")
        if self.total_count != len(self.items):
            raise ValueError("total_count must match items")

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total_count": self.total_count,
        }


__all__ = ["ReviewSessionListResponseDTO", "ReviewSessionResponseDTO"]
