from dataclasses import dataclass

from app.domain.market_intelligence import (
    ExternalMarketSignal,
    HumanVerification,
    ReviewSession,
)


class ReviewWorkflowError(ValueError):
    pass


class DuplicateCandidateReviewError(ReviewWorkflowError):
    pass


class ReviewPersistenceError(RuntimeError):
    """Verified review facts were not durably stored as one successful workflow."""

    def __init__(self, message: str, *, partial_completion: bool) -> None:
        super().__init__(message)
        self.partial_completion = partial_completion


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
    "ReviewPersistenceError",
    "ReviewWorkflowError",
    "SkipCandidateResult",
]
