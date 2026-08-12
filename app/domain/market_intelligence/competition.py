from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from app.domain.market_intelligence.evidence import MarketEvidence
from app.domain.market_intelligence.assessment_subject import (
    AssessmentSubject,
    assessment_subject_kind,
    validate_evidence_context,
)


COMPETITION_METRICS = frozenset({
    "competitor_count",
    "rocket_seller_count",
    "lowest_price",
    "highest_price",
    "median_price",
    "price_spread",
    "sponsored_result_count",
    "organic_result_count",
})

_COUNT_METRICS = frozenset({
    "competitor_count",
    "rocket_seller_count",
    "sponsored_result_count",
    "organic_result_count",
})

_PRICE_METRICS = frozenset({
    "lowest_price",
    "highest_price",
    "median_price",
    "price_spread",
})


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
class CompetitionObservation:
    """Immutable competition snapshot.

    ``competitor_count`` is a distinct market metric. Sponsored and organic
    result counts describe observed search result cards and must not be treated
    as equivalent to competitor count.
    """

    observation_id: str
    identity: AssessmentSubject
    observed_at: datetime
    schema_version: str
    evidence: Mapping[str, MarketEvidence]

    def __post_init__(self) -> None:
        assessment_subject_kind(self.identity)
        if not isinstance(self.evidence, Mapping):
            raise TypeError("evidence must be a mapping")

        values = dict(self.evidence)
        unsupported = sorted(set(values).difference(COMPETITION_METRICS))
        if unsupported:
            raise ValueError(f"unsupported competition metric: {', '.join(unsupported)}")

        for metric, item in values.items():
            if not isinstance(item, MarketEvidence):
                raise TypeError("competition evidence values must be MarketEvidence")
            validate_evidence_context(self.identity, item)
            if item.value is None:
                continue
            if metric in _COUNT_METRICS:
                if isinstance(item.value, bool) or not isinstance(item.value, int):
                    raise TypeError(f"{metric} must be int")
                if item.value < 0:
                    raise ValueError(f"{metric} cannot be negative")
            elif metric in _PRICE_METRICS:
                if not isinstance(item.value, Decimal):
                    raise TypeError(f"{metric} must be Decimal")
                if not item.value.is_finite() or item.value < 0:
                    raise ValueError(f"{metric} must be finite and non-negative")
                if item.unit is None:
                    raise ValueError(f"{metric} requires currency unit")

        object.__setattr__(self, "observation_id", _required_text(self.observation_id, "observation_id"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "evidence", MappingProxyType(values))
