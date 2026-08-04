"""Persistence boundary for authoritative EconomicsCalculation snapshots."""

from typing import Protocol

from app.domain.decision_engine import OpportunityIdentity
from app.domain.economics_calculation_snapshot import EconomicsCalculationSnapshot
from app.domain.market_intelligence import MarketObservationIdentity


class EconomicsCalculationSnapshotPersistenceError(RuntimeError): pass
class EconomicsCalculationSnapshotNotFoundError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotConflictError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotOpportunityNotFoundError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotBindingNotFoundError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotBindingMismatchError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotMarketIdentityConflictError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotVerifiedSourceNotFoundError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotVerifiedSourceConflictError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotPriceSourceNotFoundError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotPriceSourceConflictError(EconomicsCalculationSnapshotPersistenceError): pass
class MalformedEconomicsCalculationSnapshotPersistenceError(EconomicsCalculationSnapshotPersistenceError): pass
class UnsupportedEconomicsCalculationSnapshotVersionError(MalformedEconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotHistoryError(EconomicsCalculationSnapshotPersistenceError): pass
class EconomicsCalculationSnapshotCommitError(EconomicsCalculationSnapshotPersistenceError): pass


class EconomicsCalculationSnapshotRepository(Protocol):
    def save_snapshot(
        self, snapshot: EconomicsCalculationSnapshot
    ) -> EconomicsCalculationSnapshot: ...

    def get_snapshot(self, snapshot_id: str) -> EconomicsCalculationSnapshot | None: ...

    def get_by_opportunity(
        self, opportunity_identity: OpportunityIdentity
    ) -> tuple[EconomicsCalculationSnapshot, ...]: ...

    def get_by_market_identity(
        self, market_observation_identity: MarketObservationIdentity
    ) -> tuple[EconomicsCalculationSnapshot, ...]: ...

    def get_by_verified_economics_source(
        self, opportunity_id: str
    ) -> tuple[EconomicsCalculationSnapshot, ...]: ...


__all__ = [name for name in globals() if name.startswith("EconomicsCalculation") or name.startswith("MalformedEconomics") or name.startswith("UnsupportedEconomics")]
