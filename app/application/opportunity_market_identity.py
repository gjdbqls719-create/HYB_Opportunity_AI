from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)


MARKET_IDENTITY_BINDING_SCHEMA_VERSION = "opportunity-market-identity-v1"


class OpportunityMarketIdentityBindingNotFoundError(LookupError):
    pass


class OpportunityMarketIdentityConflictError(ValueError):
    pass


class DuplicateOpportunityMarketIdentityBindingError(
    OpportunityMarketIdentityConflictError
):
    pass


class MalformedOpportunityMarketIdentityBindingError(ValueError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class OpportunityMarketIdentityBinding:
    opportunity_id: str
    discovery_reference: str
    market_observation_identity: MarketObservationIdentity
    bound_at: datetime
    schema_version: str = MARKET_IDENTITY_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_id", _required(self.opportunity_id, "opportunity_id"))
        object.__setattr__(
            self,
            "discovery_reference",
            _required(self.discovery_reference, "discovery_reference"),
        )
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError(
                "market_observation_identity must be MarketObservationIdentity"
            )
        if self.market_observation_identity.scope not in {
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        }:
            raise ValueError(
                "market identity scope must be listing or canonical_product"
            )
        if not isinstance(self.bound_at, datetime):
            raise TypeError("bound_at must be a datetime")
        if self.bound_at.tzinfo is None or self.bound_at.utcoffset() is None:
            raise ValueError("bound_at must be timezone-aware")
        object.__setattr__(
            self,
            "schema_version",
            _required(self.schema_version, "schema_version"),
        )


class OpportunityMarketIdentityRepository(Protocol):
    def get_market_identity_binding(
        self, opportunity_id: str
    ) -> OpportunityMarketIdentityBinding | None:
        ...


class GetOpportunityMarketIdentity:
    def __init__(self, repository: OpportunityMarketIdentityRepository) -> None:
        self._repository = repository

    def execute(self, opportunity_id: str) -> MarketObservationIdentity:
        normalized = _required(opportunity_id, "opportunity_id")
        binding = self._repository.get_market_identity_binding(normalized)
        if binding is None:
            raise OpportunityMarketIdentityBindingNotFoundError(
                "opportunity market identity binding not found"
            )
        if binding.opportunity_id != normalized:
            raise OpportunityMarketIdentityConflictError(
                "market identity binding opportunity_id does not match request"
            )
        return binding.market_observation_identity
