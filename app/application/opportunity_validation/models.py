from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from app.domain.opportunity import OpportunityLifecycleStatus
from app.application.opportunity_validation.reference import canonicalize_discovery_reference


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _finite(value: float, name: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


@dataclass(frozen=True, slots=True)
class ValidationAdmissionSnapshot:
    opportunity_id: str
    discovery_reference: str
    marketplace: str
    title: str
    admission_recommendation: str
    admission_score: float
    admission_roi: float
    currency: str
    admission_safety_status: str
    captured_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "opportunity_id", "discovery_reference", "marketplace", "title",
            "admission_recommendation", "currency", "admission_safety_status",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        object.__setattr__(
            self,
            "discovery_reference",
            canonicalize_discovery_reference(self.discovery_reference),
        )
        object.__setattr__(self, "marketplace", self.marketplace.lower())
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "admission_score", _finite(self.admission_score, "admission_score"))
        object.__setattr__(self, "admission_roi", _finite(self.admission_roi, "admission_roi"))
        _aware(self.captured_at, "captured_at")


@dataclass(frozen=True, slots=True)
class ValidationQueueItem:
    opportunity_id: str
    discovery_reference: str
    marketplace: str
    title: str
    recommendation: str
    score: float
    roi: float
    currency: str
    safety_status: str
    lifecycle_status: OpportunityLifecycleStatus
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "opportunity_id": self.opportunity_id,
            "discovery_reference": self.discovery_reference,
            "marketplace": self.marketplace,
            "title": self.title,
            "recommendation": self.recommendation,
            "score": self.score,
            "roi": self.roi,
            "currency": self.currency,
            "safety_status": self.safety_status,
            "lifecycle_status": self.lifecycle_status.value,
            "lifecycle_version": self.lifecycle_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AddToValidationQueueCommand:
    discovery_reference: str
    marketplace: str
    title: str
    admission_recommendation: str
    admission_score: float
    admission_roi: float
    currency: str
    admission_safety_status: str
    operator_id: str
    reason: str
    captured_at: datetime
    opportunity_id: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationQueueQuery:
    statuses: tuple[OpportunityLifecycleStatus, ...] = (
        OpportunityLifecycleStatus.DISCOVERED,
        OpportunityLifecycleStatus.UNDER_REVIEW,
    )
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ValidationActionCommand:
    opportunity_id: str
    expected_version: int
    operator_id: str
    reason: str
    occurred_at: datetime
    note: str | None = None
