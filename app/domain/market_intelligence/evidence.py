from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class MarketEvidenceStatus(StrEnum):
    VERIFIED = "verified"
    HUMAN_VERIFIED = "human_verified"
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    EXTRACTION_FAILED = "extraction_failed"


_OBSERVED_STATUSES = frozenset({
    MarketEvidenceStatus.VERIFIED,
    MarketEvidenceStatus.HUMAN_VERIFIED,
    MarketEvidenceStatus.OBSERVED,
})

_VALUE_ABSENT_STATUSES = frozenset({
    MarketEvidenceStatus.UNKNOWN,
    MarketEvidenceStatus.UNAVAILABLE,
    MarketEvidenceStatus.UNSUPPORTED,
    MarketEvidenceStatus.EXTRACTION_FAILED,
})


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware_optional(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class MarketEvidence:
    value: Any
    source: str | None
    reference: str | None
    observed_at: datetime | None
    status: MarketEvidenceStatus
    confidence: Decimal
    market: str
    marketplace: str
    collection_method: str
    schema_version: str
    keyword: str | None = None
    category: str | None = None
    marketplace_item_id: str | None = None
    canonical_product_id: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        try:
            status = MarketEvidenceStatus(self.status)
        except ValueError as error:
            raise ValueError("unsupported market evidence status") from error

        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be Decimal")
        if not self.confidence.is_finite():
            raise ValueError("confidence must be finite")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")

        source = _optional_text(self.source, "source")
        observed_at = _aware_optional(self.observed_at, "observed_at")

        if status in _OBSERVED_STATUSES:
            if self.value is None:
                raise ValueError(f"{status.value} evidence requires value")
            if source is None:
                raise ValueError(f"{status.value} evidence requires source")
            if observed_at is None:
                raise ValueError(f"{status.value} evidence requires observed_at")
        elif status in _VALUE_ABSENT_STATUSES and self.value is not None:
            raise ValueError(f"{status.value} evidence requires value to be None")
        elif status is MarketEvidenceStatus.ESTIMATED and self.value is None:
            raise ValueError("estimated evidence requires value")

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "reference", _optional_text(self.reference, "reference"))
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "market", _required_text(self.market, "market"))
        object.__setattr__(self, "marketplace", _required_text(self.marketplace, "marketplace").lower())
        object.__setattr__(self, "collection_method", _required_text(self.collection_method, "collection_method"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        for name in (
            "keyword", "category", "marketplace_item_id",
            "canonical_product_id", "unit",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
