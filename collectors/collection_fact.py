from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models import Product
from collectors.descriptor import CollectorDescriptor


@dataclass(frozen=True, slots=True)
class CollectionFact:
    """Facts preserved when one raw collector item becomes a Product."""

    product: Product
    observed_at: datetime
    collector_descriptor: CollectorDescriptor
    source_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.collector_descriptor, CollectorDescriptor):
            raise TypeError("collector_descriptor must be CollectorDescriptor")

    @property
    def collector_name(self) -> str:
        return self.collector_descriptor.collector_name

    @property
    def collector_version(self) -> str:
        return self.collector_descriptor.collector_version


__all__ = ["CollectionFact"]
