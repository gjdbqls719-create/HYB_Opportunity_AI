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


@dataclass(frozen=True, slots=True)
class CandidateReviewResult:
    session: ReviewSession
    verification: HumanVerification
    signal: ExternalMarketSignal


__all__ = [
    "CandidateReviewResult",
    "DuplicateCandidateReviewError",
    "ReviewWorkflowError",
]
