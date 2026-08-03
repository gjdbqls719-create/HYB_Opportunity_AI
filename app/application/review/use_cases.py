from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domain.market_intelligence import (
    ExternalSignalDirection,
    MarketObservationIdentity,
    OCRCandidate,
    ReviewSession,
)


@dataclass(frozen=True, slots=True)
class CreateReviewSession:
    session_id: str
    artifact_id: str
    candidate_ids: tuple[str, ...]
    operator_id: str
    created_at: datetime
    schema_version: str = "review-session-v1"
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartReview:
    session: ReviewSession
    operator_id: str
    started_at: datetime | None = None
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteReview:
    session: ReviewSession
    operator_id: str
    completed_at: datetime
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class CancelReview:
    session: ReviewSession
    operator_id: str
    cancelled_at: datetime
    command_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ApproveCandidate:
    session: ReviewSession
    candidate: OCRCandidate
    verification_id: str
    operator_id: str
    verified_at: datetime
    identity: MarketObservationIdentity
    signal_id: str
    signal_name: str
    signal_direction: ExternalSignalDirection
    comment: str | None = None
    confidence: Decimal = Decimal("1")
    verification_schema_version: str = "human-verification-v1"
    signal_schema_version: str = "external-signal-v1"
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class CorrectCandidate:
    session: ReviewSession
    candidate: OCRCandidate
    corrected_value: Any
    verification_id: str
    operator_id: str
    verified_at: datetime
    identity: MarketObservationIdentity
    signal_id: str
    signal_name: str
    signal_direction: ExternalSignalDirection
    comment: str | None = None
    confidence: Decimal = Decimal("1")
    verification_schema_version: str = "human-verification-v1"
    signal_schema_version: str = "external-signal-v1"
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class SkipCandidate:
    session: ReviewSession
    candidate: OCRCandidate
    operator_id: str
    reason: str
    skipped_at: datetime
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartReviewCommand:
    session_id: str
    expected_revision: int
    command_id: str
    operator_id: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class CompleteReviewCommand:
    session_id: str
    expected_revision: int
    command_id: str
    operator_id: str
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CancelReviewCommand:
    session_id: str
    expected_revision: int
    command_id: str
    operator_id: str
    cancelled_at: datetime
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ApproveCandidateCommand:
    session_id: str
    candidate_id: str
    expected_revision: int
    command_id: str
    verification_id: str
    operator_id: str
    verified_at: datetime
    signal_id: str
    identity: MarketObservationIdentity | None = None
    signal_name: str | None = None
    signal_direction: ExternalSignalDirection | None = None
    comment: str | None = None
    confidence: Decimal = Decimal("1")
    verification_schema_version: str = "human-verification-v1"
    signal_schema_version: str = "external-signal-v1"


@dataclass(frozen=True, slots=True)
class CorrectCandidateCommand(ApproveCandidateCommand):
    corrected_value: Any = None


@dataclass(frozen=True, slots=True)
class SkipCandidateCommand:
    session_id: str
    candidate_id: str
    expected_revision: int
    command_id: str
    operator_id: str
    reason: str
    skipped_at: datetime
