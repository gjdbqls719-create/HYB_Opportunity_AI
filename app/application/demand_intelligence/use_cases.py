from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market_intelligence import MarketObservationIdentity


@dataclass(frozen=True, slots=True)
class AnalyzeDemand:
    identity: MarketObservationIdentity
    generated_at: datetime
    schema_version: str = "demand-assessment-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MarketObservationIdentity):
            raise TypeError("identity must be MarketObservationIdentity")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("schema_version must be non-empty text")
        object.__setattr__(self, "schema_version", self.schema_version.strip())
