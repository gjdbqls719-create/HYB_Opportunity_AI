"""Persistence boundary for authoritative PriceIntelligence snapshots."""

from typing import Protocol

from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.price_intelligence import PriceIntelligenceSnapshot


class PriceIntelligenceSnapshotRepository(Protocol):
    def save_snapshot(
        self, snapshot: PriceIntelligenceSnapshot
    ) -> PriceIntelligenceSnapshot: ...

    def get_snapshot(self, snapshot_id: str) -> PriceIntelligenceSnapshot | None: ...

    def get_by_candidate(
        self, candidate_identity: OpportunityCandidateIdentity
    ) -> tuple[PriceIntelligenceSnapshot, ...]: ...

    def get_by_market_identity(
        self, market_observation_identity: MarketObservationIdentity
    ) -> tuple[PriceIntelligenceSnapshot, ...]: ...


__all__ = ["PriceIntelligenceSnapshotRepository"]
