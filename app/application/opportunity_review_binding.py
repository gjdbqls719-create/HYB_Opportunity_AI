from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market_intelligence import MarketObservationIdentity

BINDING_SCHEMA_VERSION = "opportunity-review-binding-v1"

class OpportunityReviewBindingNotFoundError(LookupError): pass
class OpportunityReviewBindingConflictError(ValueError): pass
class OpportunityReviewBindingPersistenceError(RuntimeError): pass

def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be non-empty text")
    return value.strip()

@dataclass(frozen=True, slots=True)
class OpportunityReviewBinding:
    binding_id: str
    opportunity_id: str
    session_id: str
    discovery_reference: str
    market_observation_identity: MarketObservationIdentity
    command_id: str
    bound_at: datetime
    schema_version: str = BINDING_SCHEMA_VERSION

    def __post_init__(self):
        for name in ("binding_id", "opportunity_id", "session_id", "discovery_reference", "command_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.market_observation_identity, MarketObservationIdentity): raise TypeError("market_observation_identity must be MarketObservationIdentity")
        if not isinstance(self.bound_at, datetime) or self.bound_at.tzinfo is None or self.bound_at.utcoffset() is None: raise ValueError("bound_at must be timezone-aware")
