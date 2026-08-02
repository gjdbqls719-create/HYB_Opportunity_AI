from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MarketObservationScope(StrEnum):
    LISTING = "listing"
    CANONICAL_PRODUCT = "canonical_product"
    SEARCH_QUERY = "search_query"
    CATEGORY = "category"


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


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class MarketObservationIdentity:
    scope: MarketObservationScope
    market: str
    marketplace: str
    canonical_product_id: str | None
    marketplace_item_id: str | None
    normalized_query: str | None
    category: str | None
    variant_identity: str | None
    condition: str | None
    window_started_at: datetime
    window_ended_at: datetime

    def __post_init__(self) -> None:
        try:
            scope = MarketObservationScope(self.scope)
        except ValueError as error:
            raise ValueError("unsupported market observation scope") from error

        optional_values = {}
        for name in (
            "canonical_product_id", "marketplace_item_id", "normalized_query",
            "category", "variant_identity", "condition",
        ):
            optional_values[name] = _optional_text(getattr(self, name), name)

        required_by_scope = {
            MarketObservationScope.LISTING: "marketplace_item_id",
            MarketObservationScope.CANONICAL_PRODUCT: "canonical_product_id",
            MarketObservationScope.SEARCH_QUERY: "normalized_query",
            MarketObservationScope.CATEGORY: "category",
        }
        required_name = required_by_scope[scope]
        if optional_values[required_name] is None:
            raise ValueError(f"{scope.value} scope requires {required_name}")

        started_at = _aware(self.window_started_at, "window_started_at")
        ended_at = _aware(self.window_ended_at, "window_ended_at")
        if ended_at < started_at:
            raise ValueError("window_ended_at cannot precede window_started_at")

        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "market", _required_text(self.market, "market"))
        object.__setattr__(self, "marketplace", _required_text(self.marketplace, "marketplace").lower())
        for name, value in optional_values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "window_started_at", started_at)
        object.__setattr__(self, "window_ended_at", ended_at)
