from __future__ import annotations

from datetime import timedelta

from app.application.market_observation.models import (
    GetLatestObservation,
    GetObservationHistory,
    LatestMarketObservation,
    MarketObservation,
    SaveMarketObservation,
)
from app.application.market_observation.ports import MarketObservationRepository


class MarketObservationService:
    def __init__(self, repository: MarketObservationRepository) -> None:
        if not isinstance(repository, MarketObservationRepository):
            raise TypeError("repository must implement MarketObservationRepository")
        self._repository = repository

    def save(self, command: SaveMarketObservation) -> MarketObservation:
        self._repository.save(command.observation)
        return command.observation

    def get_latest(self, query: GetLatestObservation) -> LatestMarketObservation | None:
        observation = self._repository.get_latest(query.observation_type, query.identity)
        if observation is None:
            return None
        observed_at = observation.observed_at if hasattr(observation, "observed_at") else observation.captured_at
        age = max(query.as_of - observed_at, timedelta(0))
        return LatestMarketObservation(
            observation=observation,
            age=age,
            is_stale=age > query.freshness_window,
        )

    def get_history(self, query: GetObservationHistory) -> tuple[MarketObservation, ...]:
        return self._repository.get_history(
            query.observation_type,
            query.identity,
            limit=query.limit,
        )
