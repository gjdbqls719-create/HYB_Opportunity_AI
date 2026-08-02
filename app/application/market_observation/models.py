from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    ExternalMarketSignal,
    MarketObservationIdentity,
)


MarketObservation = CompetitionObservation | DemandObservation | ExternalMarketSignal


class MarketObservationType(StrEnum):
    COMPETITION = "competition"
    DEMAND = "demand"
    EXTERNAL_SIGNAL = "external_signal"

    @classmethod
    def from_observation(cls, observation: MarketObservation) -> MarketObservationType:
        if isinstance(observation, CompetitionObservation):
            return cls.COMPETITION
        if isinstance(observation, DemandObservation):
            return cls.DEMAND
        if isinstance(observation, ExternalMarketSignal):
            return cls.EXTERNAL_SIGNAL
        raise TypeError("unsupported market observation")


@dataclass(frozen=True, slots=True)
class SaveMarketObservation:
    observation: MarketObservation

    def __post_init__(self) -> None:
        MarketObservationType.from_observation(self.observation)


@dataclass(frozen=True, slots=True)
class GetLatestObservation:
    observation_type: MarketObservationType
    identity: MarketObservationIdentity
    as_of: datetime
    freshness_window: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.observation_type, MarketObservationType):
            object.__setattr__(self, "observation_type", MarketObservationType(self.observation_type))
        if not isinstance(self.identity, MarketObservationIdentity):
            raise TypeError("identity must be MarketObservationIdentity")
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be datetime")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if not isinstance(self.freshness_window, timedelta):
            raise TypeError("freshness_window must be timedelta")
        if self.freshness_window < timedelta(0):
            raise ValueError("freshness_window cannot be negative")


@dataclass(frozen=True, slots=True)
class GetObservationHistory:
    observation_type: MarketObservationType
    identity: MarketObservationIdentity
    limit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observation_type, MarketObservationType):
            object.__setattr__(self, "observation_type", MarketObservationType(self.observation_type))
        if not isinstance(self.identity, MarketObservationIdentity):
            raise TypeError("identity must be MarketObservationIdentity")
        if self.limit is not None and (
            isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1
        ):
            raise ValueError("limit must be a positive integer or None")


@dataclass(frozen=True, slots=True)
class LatestMarketObservation:
    observation: MarketObservation
    age: timedelta
    is_stale: bool

    def __post_init__(self) -> None:
        MarketObservationType.from_observation(self.observation)
        if self.age < timedelta(0):
            raise ValueError("observation age cannot be negative")
