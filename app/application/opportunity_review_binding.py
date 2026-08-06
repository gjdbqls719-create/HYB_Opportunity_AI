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


def validate_opportunity_review_binding(
    bindings,
    *,
    opportunity_id: str,
    discovery_reference: str,
    market_observation_identity: MarketObservationIdentity,
) -> OpportunityReviewBinding:
    bindings = tuple(bindings)
    if not bindings:
        raise OpportunityReviewBindingNotFoundError("opportunity review binding not found")
    if len(bindings) != 1:
        raise OpportunityReviewBindingConflictError("opportunity must have exactly one review binding")
    binding = bindings[0]
    if binding.opportunity_id != opportunity_id:
        raise OpportunityReviewBindingConflictError("review binding opportunity identity mismatch")
    if binding.discovery_reference != discovery_reference:
        raise OpportunityReviewBindingConflictError("review binding discovery reference mismatch")
    if binding.market_observation_identity != market_observation_identity:
        raise OpportunityReviewBindingConflictError("review binding market identity mismatch")
    if binding.schema_version != BINDING_SCHEMA_VERSION:
        raise OpportunityReviewBindingConflictError("unsupported opportunity review binding version")
    return binding
