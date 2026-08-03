from dataclasses import dataclass
from datetime import datetime

from app.domain.market_intelligence import (
    ExternalMarketSignal,
    HumanVerification,
    InvalidReviewSessionTransitionError,
    ExternalSignalDirection,
    MarketObservationIdentity,
    ReviewSession,
)


class ReviewWorkflowError(ValueError):
    pass


class DuplicateCandidateReviewError(ReviewWorkflowError):
    pass


class ReviewSessionNotFoundError(ReviewWorkflowError):
    pass


class DuplicateReviewSessionError(ReviewWorkflowError):
    pass


class ReviewSessionVersionConflictError(ReviewWorkflowError):
    pass


class ReviewCandidateNotFoundError(ReviewWorkflowError):
    pass


class ReviewCandidateMembershipError(ReviewWorkflowError):
    pass


class ReviewArtifactMismatchError(ReviewWorkflowError):
    pass


class ReviewOperatorMismatchError(ReviewWorkflowError):
    pass


class PendingCandidatesError(InvalidReviewSessionTransitionError, ReviewWorkflowError):
    pass


class ReviewPersistenceError(RuntimeError):
    """Verified review facts were not durably stored as one successful workflow."""

    def __init__(self, message: str, *, partial_completion: bool) -> None:
        super().__init__(message)
        self.partial_completion = partial_completion


class ReviewSessionPersistenceError(ReviewPersistenceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, partial_completion=False)


class ReviewHistoryError(ReviewPersistenceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, partial_completion=False)


class ReviewProjectionError(ReviewPersistenceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, partial_completion=False)


class ReviewCommitError(ReviewPersistenceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, partial_completion=False)


class ReviewSessionHistoryError(ReviewHistoryError):
    pass


class ReviewSessionProjectionError(ReviewProjectionError):
    pass


class ReviewSessionCommitError(ReviewCommitError):
    pass


class MalformedReviewSessionError(ReviewSessionPersistenceError):
    pass


class UnsupportedReviewSessionVersionError(MalformedReviewSessionError):
    pass


class ReviewCommandConflictError(ReviewWorkflowError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewTransitionMetadata:
    event_id: str
    command_id: str
    transition_type: str
    occurred_at: datetime
    command_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("event_id", "command_id", "transition_type", "command_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReviewSessionHistoryEntry:
    session: ReviewSession
    metadata: ReviewTransitionMetadata
    prior_status: str | None
    resulting_status: str


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ReviewCommandContext:
    session_id: str
    candidate_id: str
    market_observation_identity: MarketObservationIdentity
    signal_name: str
    signal_direction: ExternalSignalDirection
    artifact_identity: str
    created_at: datetime
    schema_version: str = "review-command-context-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id"))
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        object.__setattr__(self, "signal_name", _text(self.signal_name, "signal_name"))
        object.__setattr__(self, "signal_direction", ExternalSignalDirection(self.signal_direction))
        object.__setattr__(self, "artifact_identity", _text(self.artifact_identity, "artifact_identity"))
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class ReviewCommandReceipt:
    command_id: str
    session_id: str
    candidate_id: str | None
    transition_type: str
    resulting_revision: int
    verification_id: str | None
    external_signal_id: str | None
    transition_timestamp: datetime
    completed_at: datetime | None
    schema_version: str = "review-command-receipt-v1"

    def __post_init__(self) -> None:
        for name in ("command_id", "session_id", "transition_type", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.candidate_id is not None:
            object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        if not isinstance(self.resulting_revision, int) or isinstance(self.resulting_revision, bool) or self.resulting_revision < 1:
            raise ValueError("resulting_revision must be a positive integer")
        for name in ("verification_id", "external_signal_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _text(value, name))
        object.__setattr__(self, "transition_timestamp", _aware(self.transition_timestamp, "transition_timestamp"))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", _aware(self.completed_at, "completed_at"))


@dataclass(frozen=True, slots=True)
class ReviewCancelMetadata:
    session_id: str
    reason: str
    operator_id: str
    cancelled_at: datetime
    revision: int
    schema_version: str = "review-cancel-metadata-v1"

    def __post_init__(self) -> None:
        for name in ("session_id", "reason", "operator_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "cancelled_at", _aware(self.cancelled_at, "cancelled_at"))
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be a positive integer")


@dataclass(frozen=True, slots=True)
class CandidateReviewResult:
    session: ReviewSession
    verification: HumanVerification
    signal: ExternalMarketSignal


@dataclass(frozen=True, slots=True)
class SkipCandidateResult:
    session: ReviewSession


__all__ = [
    "CandidateReviewResult",
    "DuplicateCandidateReviewError",
    "DuplicateReviewSessionError",
    "MalformedReviewSessionError",
    "PendingCandidatesError",
    "ReviewArtifactMismatchError",
    "ReviewCandidateMembershipError",
    "ReviewCandidateNotFoundError",
    "ReviewCommandConflictError",
    "ReviewCommandContext",
    "ReviewCommandReceipt",
    "ReviewCancelMetadata",
    "ReviewCommitError",
    "ReviewHistoryError",
    "ReviewOperatorMismatchError",
    "ReviewPersistenceError",
    "ReviewProjectionError",
    "ReviewSessionCommitError",
    "ReviewSessionHistoryEntry",
    "ReviewSessionHistoryError",
    "ReviewSessionNotFoundError",
    "ReviewSessionPersistenceError",
    "ReviewSessionProjectionError",
    "ReviewSessionVersionConflictError",
    "ReviewTransitionMetadata",
    "ReviewWorkflowError",
    "SkipCandidateResult",
    "UnsupportedReviewSessionVersionError",
]
