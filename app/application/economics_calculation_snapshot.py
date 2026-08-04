"""Persistence boundary for authoritative EconomicsCalculation snapshots."""

from typing import Protocol

from app.domain.decision_engine import OpportunityIdentity
from app.domain.economics_calculation_snapshot import EconomicsCalculationSnapshot
from app.domain.market_intelligence import MarketObservationIdentity


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


__all__ = ["EconomicsCalculationSnapshotRepository"]
