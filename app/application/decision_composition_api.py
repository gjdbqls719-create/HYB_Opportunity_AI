from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.application.decision_composition import (
    DECISION_POLICY_VERSION,
    DECISION_SCHEMA_VERSION,
    DecisionCompositionSnapshot,
    FinalizeDecisionComposition,
)


def _required(value: str, name: str) -> str:
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
class FinalizeOpportunityDecisionCompositionCommand:
    opportunity_id: str
    external_signal_ids: tuple[str, ...] | None = None
    generated_at: datetime | None = None
    requested_by: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_id", _required(self.opportunity_id, "opportunity_id"))
        if self.external_signal_ids is not None:
            if not isinstance(self.external_signal_ids, tuple):
                raise TypeError("external_signal_ids must be tuple or None")
            normalized = tuple(_required(value, "external_signal_id") for value in self.external_signal_ids)
            if len(set(normalized)) != len(normalized):
                raise ValueError("external_signal_ids cannot contain duplicates")
            object.__setattr__(self, "external_signal_ids", normalized)
        if self.generated_at is not None:
            object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        if self.requested_by is not None:
            object.__setattr__(self, "requested_by", _required(self.requested_by, "requested_by"))


@dataclass(frozen=True, slots=True)
class DecisionCompositionFinalizationResponseDTO:
    composition_id: str
    opportunity_id: str
    composition_version: int
    generated_at: datetime
    schema_version: str
    policy_version: str
    composition_schema_version: str
    metadata_policy_version: str
    external_signal_ids: tuple[str, ...]
    status: str = "finalized"

    @classmethod
    def from_snapshot(cls, snapshot: DecisionCompositionSnapshot):
        return cls(
            composition_id=snapshot.composition_id,
            opportunity_id=snapshot.opportunity_identity.opportunity_id,
            composition_version=snapshot.composition_version,
            generated_at=snapshot.generated_at,
            schema_version=snapshot.schema_version,
            policy_version=snapshot.policy_version,
            composition_schema_version=snapshot.composition_schema_version,
            metadata_policy_version=snapshot.metadata_policy_version,
            external_signal_ids=snapshot.external_signal_ids,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "composition_id": self.composition_id,
            "opportunity_id": self.opportunity_id,
            "composition_version": self.composition_version,
            "generated_at": self.generated_at.isoformat(),
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "composition_schema_version": self.composition_schema_version,
            "metadata_policy_version": self.metadata_policy_version,
            "external_signal_ids": list(self.external_signal_ids),
            "status": self.status,
        }


class FinalizeOpportunityDecisionComposition:
    def __init__(self, finalizer: FinalizeDecisionComposition, clock: Callable[[], datetime]) -> None:
        self._finalizer = finalizer
        self._clock = clock

    def execute(self, command: FinalizeOpportunityDecisionCompositionCommand):
        if not isinstance(command, FinalizeOpportunityDecisionCompositionCommand):
            raise TypeError("command must be FinalizeOpportunityDecisionCompositionCommand")
        generated_at = command.generated_at or _aware(self._clock(), "clock result")
        snapshot = self._finalizer.execute(
            command.opportunity_id,
            generated_at=generated_at,
            schema_version=DECISION_SCHEMA_VERSION,
            policy_version=DECISION_POLICY_VERSION,
            external_signal_ids=command.external_signal_ids,
        )
        return DecisionCompositionFinalizationResponseDTO.from_snapshot(snapshot)
