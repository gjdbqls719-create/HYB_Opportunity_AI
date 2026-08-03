"""Read-only API DTOs for Founder Review sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.review import ReviewSessionDetail
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


@dataclass(frozen=True, slots=True)
class ReviewSessionDetailResponseDTO:
    detail: ReviewSessionDetail

    def to_dict(self) -> dict[str, object]:
        session = ReviewSessionResponseDTO.from_session(self.detail.session).to_dict()
        session["artifact_id"] = self.detail.session.artifact_id
        session["operator_id"] = self.detail.session.operator_id
        session["candidates"] = [
            self._candidate(value) for value in self.detail.candidates
        ]
        return session

    @staticmethod
    def _candidate(value) -> dict[str, object]:
        candidate = value.candidate
        artifact = candidate.artifact
        context = value.context
        skip = value.skip_record
        return {
            "candidate_id": candidate.candidate_id,
            "status": value.status.value,
            "field_name": candidate.field_name.value,
            "raw_text": candidate.raw_text,
            "normalized_value": candidate.normalized_value,
            "confidence": str(candidate.confidence),
            "captured_at": candidate.captured_at.isoformat(),
            "schema_version": candidate.schema_version,
            "artifact": {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type.value,
                "origin": artifact.artifact_origin.value,
                "source_type": artifact.source_type.value,
                "mime_type": artifact.mime_type,
                "width": artifact.width,
                "height": artifact.height,
                "file_size": artifact.file_size,
                "captured_at": artifact.captured_at.isoformat(),
                "schema_version": artifact.schema_version,
                "preview_available": False,
            },
            "context": (
                {
                    "signal_name": context.signal_name,
                    "signal_direction": context.signal_direction.value,
                    "artifact_identity": context.artifact_identity,
                    "created_at": context.created_at.isoformat(),
                    "schema_version": context.schema_version,
                    "market_observation_identity": {
                        "scope": context.market_observation_identity.scope.value,
                        "market": context.market_observation_identity.market,
                        "marketplace": context.market_observation_identity.marketplace,
                        "canonical_product_id": context.market_observation_identity.canonical_product_id,
                        "marketplace_item_id": context.market_observation_identity.marketplace_item_id,
                        "normalized_query": context.market_observation_identity.normalized_query,
                        "category": context.market_observation_identity.category,
                        "variant_identity": context.market_observation_identity.variant_identity,
                        "condition": context.market_observation_identity.condition,
                        "window_started_at": context.market_observation_identity.window_started_at.isoformat(),
                        "window_ended_at": context.market_observation_identity.window_ended_at.isoformat(),
                    },
                }
                if context is not None
                else None
            ),
            "skip": (
                {
                    "operator_id": skip.operator_id,
                    "reason": skip.reason,
                    "skipped_at": skip.skipped_at.isoformat(),
                }
                if skip is not None
                else None
            ),
        }


__all__ = [
    "ReviewSessionDetailResponseDTO",
    "ReviewSessionListResponseDTO",
    "ReviewSessionResponseDTO",
]
