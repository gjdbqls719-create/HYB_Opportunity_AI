"""Immutable snapshot contract for an authoritative PriceIntelligence result."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity


PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION = "price-intelligence-snapshot-v1"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _decimal(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class PriceIntelligenceSnapshot:
    snapshot_id: str
    opportunity_identity: OpportunityIdentity
    market_observation_identity: MarketObservationIdentity
    product_observation_snapshot_ids: tuple[str, ...]
    currency: str
    lowest_price: Decimal
    average_price: Decimal
    median_price: Decimal
    highest_price: Decimal
    price_range: Decimal
    price_variation_rate: Decimal
    price_stability_level: str
    recommended_selling_price: Decimal
    sample_size: int
    analyzer_version: str
    generated_at: datetime
    schema_version: str = PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "snapshot_id",
            "currency",
            "price_stability_level",
            "analyzer_version",
            "schema_version",
        ):
            _required_text(getattr(self, name), name)
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        source_ids = self.product_observation_snapshot_ids
        if not isinstance(source_ids, tuple):
            raise TypeError("product_observation_snapshot_ids must be a tuple")
        if not source_ids:
            raise ValueError("product_observation_snapshot_ids must not be empty")
        if any(not isinstance(value, str) or not value.strip() for value in source_ids):
            raise ValueError(
                "product_observation_snapshot_ids must contain non-empty text"
            )
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("product_observation_snapshot_ids must be unique")
        for name in (
            "lowest_price",
            "average_price",
            "median_price",
            "highest_price",
            "price_range",
            "price_variation_rate",
            "recommended_selling_price",
        ):
            _decimal(getattr(self, name), name)
        if (
            isinstance(self.sample_size, bool)
            or not isinstance(self.sample_size, int)
            or self.sample_size < 1
        ):
            raise ValueError("sample_size must be a positive integer")
        if self.sample_size != len(source_ids):
            raise ValueError(
                "sample_size must match product_observation_snapshot_ids"
            )
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
