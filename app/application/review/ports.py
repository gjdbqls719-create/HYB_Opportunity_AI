"""Persistence ports used by the review workflow."""

from typing import Protocol, runtime_checkable

from app.application.external_signal_ledger import ExternalSignalLedgerRepository
from app.application.market_observation import MarketObservationRepository
from app.application.review.models import (
    ReviewCancelMetadata,
    ReviewCommandContext,
    ReviewCommandReceipt,
    ReviewSessionHistoryEntry,
    ReviewTransitionMetadata,
)
from app.domain.market_intelligence import ExternalMarketSignal, HumanVerification, ReviewSession


@runtime_checkable
class ReviewSessionRepository(Protocol):
    def create(self, session: ReviewSession, metadata: ReviewTransitionMetadata) -> ReviewSession: ...
    def get(self, session_id: str) -> ReviewSession | None: ...
    def list(self) -> tuple[ReviewSession, ...]: ...
    def save_transition(
        self,
        previous_session: ReviewSession,
        next_session: ReviewSession,
        metadata: ReviewTransitionMetadata,
        *,
        _manage_transaction: bool = True,
    ) -> ReviewSession: ...
    def get_history(self, session_id: str) -> tuple[ReviewSessionHistoryEntry, ...]: ...
    def get_command_session(
        self, command_id: str, command_fingerprint: str
    ) -> ReviewSession | None: ...
    def rebuild_current(self, session_id: str | None = None) -> tuple[ReviewSession, ...]: ...
    def validate_current(self, expected: ReviewSession) -> None: ...
    def save_context(self, context: ReviewCommandContext) -> ReviewCommandContext: ...
    def get_context(self, session_id: str, candidate_id: str) -> ReviewCommandContext | None: ...
    def save_receipt(
        self, receipt: ReviewCommandReceipt, command_fingerprint: str,
        *, _manage_transaction: bool = True,
    ) -> ReviewCommandReceipt: ...
    def get_receipt(
        self, command_id: str, command_fingerprint: str | None = None
    ) -> ReviewCommandReceipt | None: ...
    def save_cancel_metadata(
        self, value: ReviewCancelMetadata, *, _manage_transaction: bool = True
    ) -> ReviewCancelMetadata: ...
    def get_cancel_metadata(self, session_id: str) -> ReviewCancelMetadata | None: ...
    def get_revision(self, session_id: str, revision: int) -> ReviewSession | None: ...


@runtime_checkable
class VerifiedSignalPersistence(Protocol):
    def save(
        self,
        verification: HumanVerification,
        signal: ExternalMarketSignal,
        *,
        previous_session: ReviewSession | None = None,
        next_session: ReviewSession | None = None,
        transition_metadata: ReviewTransitionMetadata | None = None,
        receipt: ReviewCommandReceipt | None = None,
    ) -> None: ...


__all__ = [
    "ExternalSignalLedgerRepository",
    "MarketObservationRepository",
    "ReviewSessionRepository",
    "VerifiedSignalPersistence",
]
