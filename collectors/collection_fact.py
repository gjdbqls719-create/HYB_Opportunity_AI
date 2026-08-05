from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models import Product


@dataclass(frozen=True, slots=True)
class CollectionFact:
    """Facts preserved when one raw collector item becomes a Product."""

    product: Product
    observed_at: datetime
    collector_name: str
    source_reference: str


__all__ = ["CollectionFact"]
