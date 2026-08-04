"""Immutable source contracts owned by the marketplace collection boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.models import ProductDataSource


PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION = "product-observation-snapshot-v1"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    return value


def _finite_number(value: float, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and converted < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return converted


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ObservedProductSnapshot:
    """Exact immutable copy of the existing runtime Product fields."""

    marketplace: str
    item_id: str
    title: str
    price: float
    currency: str
    condition: str
    url: str
    brand: str
    model_number: str
    category: str
    shipping_cost: float
    seller: str
    image_url: str
    rating: float | None
    review_count: int | None
    in_stock: bool
    data_source: ProductDataSource
    shipping_cost_known: bool

    def __post_init__(self) -> None:
        _required_text(self.marketplace, "marketplace")
        _text(self.item_id, "item_id")
        _required_text(self.title, "title")
        object.__setattr__(self, "price", _finite_number(self.price, "price", minimum=0))
        _required_text(self.currency, "currency")
        for name in (
            "condition",
            "url",
            "brand",
            "model_number",
            "category",
            "seller",
            "image_url",
        ):
            _text(getattr(self, name), name)
        object.__setattr__(
            self,
            "shipping_cost",
            _finite_number(self.shipping_cost, "shipping_cost", minimum=0),
        )
        if self.rating is not None:
            rating = _finite_number(self.rating, "rating")
            if not 0 <= rating <= 5:
                raise ValueError("rating must be between 0 and 5")
            object.__setattr__(self, "rating", rating)
        if self.review_count is not None:
            if (
                isinstance(self.review_count, bool)
                or not isinstance(self.review_count, int)
                or self.review_count < 0
            ):
                raise ValueError("review_count must be a non-negative integer or None")
        for name in ("in_stock", "shipping_cost_known"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if not isinstance(self.data_source, ProductDataSource):
            raise TypeError("data_source must be ProductDataSource")


@dataclass(frozen=True, slots=True)
class CollectorProvenance:
    """Collector-supplied provenance; values must never be inferred downstream."""

    collector_name: str
    collector_version: str
    source_reference: str

    def __post_init__(self) -> None:
        for name in ("collector_name", "collector_version", "source_reference"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ProductObservationSnapshot:
    snapshot_id: str
    opportunity_identity: OpportunityIdentity
    market_observation_identity: MarketObservationIdentity
    product: ObservedProductSnapshot
    collector_provenance: CollectorProvenance
    observed_at: datetime
    schema_version: str = PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.snapshot_id, "snapshot_id")
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        if not isinstance(self.product, ObservedProductSnapshot):
            raise TypeError("product must be ObservedProductSnapshot")
        if not isinstance(self.collector_provenance, CollectorProvenance):
            raise TypeError("collector_provenance must be CollectorProvenance")
        _aware(self.observed_at, "observed_at")
        _required_text(self.schema_version, "schema_version")
