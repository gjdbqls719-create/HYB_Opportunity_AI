"""Persistence ports used by the review workflow."""

from typing import Protocol, runtime_checkable

from app.application.external_signal_ledger import ExternalSignalLedgerRepository
from app.application.market_observation import MarketObservationRepository
from app.domain.market_intelligence import ExternalMarketSignal, HumanVerification


@runtime_checkable
class VerifiedSignalPersistence(Protocol):
    def save(self, verification: HumanVerification, signal: ExternalMarketSignal) -> None: ...


__all__ = [
    "ExternalSignalLedgerRepository",
    "MarketObservationRepository",
    "VerifiedSignalPersistence",
]
