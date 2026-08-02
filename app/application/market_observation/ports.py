from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.application.market_observation.models import (
    MarketObservation,
    MarketObservationType,
)
from app.domain.market_intelligence import MarketObservationIdentity


class DuplicateMarketObservationError(ValueError):
    pass


@runtime_checkable
class MarketObservationRepository(Protocol):
    def save(self, observation: MarketObservation) -> None: ...

    def get_latest(
        self,
        observation_type: MarketObservationType,
        identity: MarketObservationIdentity,
    ) -> MarketObservation | None: ...

    def get_history(
        self,
        observation_type: MarketObservationType,
        identity: MarketObservationIdentity,
        *,
        limit: int | None = None,
    ) -> tuple[MarketObservation, ...]: ...
