"""Persistence boundary for authoritative Product Observation snapshots."""

from typing import Protocol

from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.product_observation import ProductObservationSnapshot


class ProductObservationRepository(Protocol):
    def save_snapshot(
        self, snapshot: ProductObservationSnapshot
    ) -> ProductObservationSnapshot: ...

    def get_snapshot(self, snapshot_id: str) -> ProductObservationSnapshot | None: ...

    def get_by_candidate(
        self, candidate_identity: OpportunityCandidateIdentity
    ) -> tuple[ProductObservationSnapshot, ...]: ...

    def get_by_market_identity(
        self, market_observation_identity: MarketObservationIdentity
    ) -> tuple[ProductObservationSnapshot, ...]: ...


__all__ = ["ProductObservationRepository"]
