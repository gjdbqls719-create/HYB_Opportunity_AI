from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing.models import SourcingEconomicsSourceReference


SOURCING_ECONOMICS_BINDING_SCHEMA_VERSION = "sourcing-economics-binding-v1"
SOURCING_ECONOMICS_BINDING_REFERENCE_SCHEMA_VERSION = "sourcing-economics-binding-reference-v1"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class SourcingEconomicsBindingReference:
    binding_id: str
    schema_version: str = SOURCING_ECONOMICS_BINDING_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _text(self.binding_id, "binding_id"))
        if self.schema_version != SOURCING_ECONOMICS_BINDING_REFERENCE_SCHEMA_VERSION:
            raise ValueError("unsupported Sourcing Economics Binding reference version")


@dataclass(frozen=True, slots=True)
class SourcingEconomicsBinding:
    binding_id: str
    opportunity_identity: OpportunityIdentity
    source_reference: SourcingEconomicsSourceReference
    requested_at: datetime
    bound_at: datetime
    schema_version: str = SOURCING_ECONOMICS_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _text(self.binding_id, "binding_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.source_reference, SourcingEconomicsSourceReference):
            raise TypeError("source_reference must be SourcingEconomicsSourceReference")
        _aware(self.requested_at, "requested_at")
        _aware(self.bound_at, "bound_at")
        if self.schema_version != SOURCING_ECONOMICS_BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported Sourcing Economics Binding version")

    @property
    def reference(self) -> SourcingEconomicsBindingReference:
        return SourcingEconomicsBindingReference(self.binding_id)


__all__ = [name for name in globals() if name.startswith("Sourcing") or name.startswith("SOURCING")]
