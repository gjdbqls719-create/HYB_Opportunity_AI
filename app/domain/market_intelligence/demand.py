from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from app.domain.market_intelligence.evidence import MarketEvidence
from app.domain.market_intelligence.identity import MarketObservationIdentity


DEMAND_METRICS = frozenset({
    "coupang_popularity_rank",
    "itemscout_popularity_rank",
    "search_volume",
    "review_count",
    "rating",
    "sales_proxy",
    "observed_result_position",
})

_RANK_METRICS = frozenset({
    "coupang_popularity_rank",
    "itemscout_popularity_rank",
    "observed_result_position",
})

_COUNT_METRICS = frozenset({"search_volume", "review_count"})


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class DemandObservation:
    """Immutable demand-signal snapshot.

    Popularity, ranking, reviews, ratings, search volume, and sales proxy are
    demand proxies. They do not represent verified demand or actual sales.
    ``sales_proxy`` uses Decimal so derived fractional values remain exact.
    """

    observation_id: str
    identity: MarketObservationIdentity
    observed_at: datetime
    schema_version: str
    evidence: Mapping[str, MarketEvidence]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MarketObservationIdentity):
            raise TypeError("identity must be MarketObservationIdentity")
        if not isinstance(self.evidence, Mapping):
            raise TypeError("evidence must be a mapping")

        values = dict(self.evidence)
        unsupported = sorted(set(values).difference(DEMAND_METRICS))
        if unsupported:
            raise ValueError(f"unsupported demand metric: {', '.join(unsupported)}")

        for metric, item in values.items():
            if not isinstance(item, MarketEvidence):
                raise TypeError("demand evidence values must be MarketEvidence")
            if item.market != self.identity.market:
                raise ValueError("evidence market must match observation identity")
            if item.marketplace != self.identity.marketplace:
                raise ValueError("evidence marketplace must match observation identity")
            if item.value is None:
                continue
            if metric in _RANK_METRICS:
                if isinstance(item.value, bool) or not isinstance(item.value, int):
                    raise TypeError(f"{metric} must be int")
                if item.value < 1:
                    raise ValueError(f"{metric} must be at least 1")
            elif metric in _COUNT_METRICS:
                if isinstance(item.value, bool) or not isinstance(item.value, int):
                    raise TypeError(f"{metric} must be int")
                if item.value < 0:
                    raise ValueError(f"{metric} cannot be negative")
            elif metric == "rating":
                if not isinstance(item.value, Decimal):
                    raise TypeError("rating must be Decimal")
                if not item.value.is_finite() or not Decimal("0") <= item.value <= Decimal("5"):
                    raise ValueError("rating must be between 0 and 5")
            elif metric == "sales_proxy":
                if not isinstance(item.value, Decimal):
                    raise TypeError("sales_proxy must be Decimal")
                if not item.value.is_finite() or item.value < 0:
                    raise ValueError("sales_proxy must be finite and non-negative")

        object.__setattr__(self, "observation_id", _required_text(self.observation_id, "observation_id"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "evidence", MappingProxyType(values))
