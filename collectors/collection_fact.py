from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market_intelligence import MarketObservationIdentity
from app.models import Product
from collectors.descriptor import CollectorDescriptor


@dataclass(frozen=True, slots=True)
class CollectionFact:
    """Facts preserved when one raw collector item becomes a Product."""

    product: Product
    observed_at: datetime
    collector_descriptor: CollectorDescriptor
    source_reference: str
    candidate_market_identity: MarketObservationIdentity | None = None
    candidate_handoff_policy_name: str | None = None
    candidate_handoff_policy_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.collector_descriptor, CollectorDescriptor):
            raise TypeError("collector_descriptor must be CollectorDescriptor")
        handoff_values = (
            self.candidate_market_identity,
            self.candidate_handoff_policy_name,
            self.candidate_handoff_policy_version,
        )
        if any(value is None for value in handoff_values) and any(
            value is not None for value in handoff_values
        ):
            raise ValueError(
                "Candidate handoff identity and policy must be supplied together"
            )
        if (
            self.candidate_market_identity is not None
            and not isinstance(
                self.candidate_market_identity, MarketObservationIdentity
            )
        ):
            raise TypeError(
                "candidate_market_identity must be MarketObservationIdentity"
            )

    @property
    def collector_name(self) -> str:
        return self.collector_descriptor.collector_name

    @property
    def collector_version(self) -> str:
        return self.collector_descriptor.collector_version


__all__ = ["CollectionFact"]
