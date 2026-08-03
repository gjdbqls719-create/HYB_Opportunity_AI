from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.opportunity import ProductionSafetyAssessment


PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION = "production-safety-snapshot-v1"


class ProductionSafetySnapshotNotFoundError(LookupError):
    pass


class ProductionSafetySnapshotIdentityConflictError(ValueError):
    pass


class DuplicateProductionSafetySnapshotError(
    ProductionSafetySnapshotIdentityConflictError
):
    pass


class MalformedProductionSafetySnapshotError(ValueError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ProductionSafetySnapshot:
    opportunity_id: str
    assessment: ProductionSafetyAssessment
    snapshot_at: datetime
    rule_version: str
    schema_version: str = PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_id", _required(self.opportunity_id, "opportunity_id"))
        if not isinstance(self.assessment, ProductionSafetyAssessment):
            raise TypeError("assessment must be ProductionSafetyAssessment")
        if not isinstance(self.snapshot_at, datetime):
            raise TypeError("snapshot_at must be a datetime")
        if self.snapshot_at.tzinfo is None or self.snapshot_at.utcoffset() is None:
            raise ValueError("snapshot_at must be timezone-aware")
        object.__setattr__(self, "rule_version", _required(self.rule_version, "rule_version"))
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


class ProductionSafetySnapshotRepository(Protocol):
    def get_production_safety_snapshot(
        self, opportunity_id: str
    ) -> ProductionSafetySnapshot | None:
        ...


class GetProductionSafetySnapshot:
    def __init__(self, repository: ProductionSafetySnapshotRepository) -> None:
        self._repository = repository

    def execute(self, opportunity_id: str) -> ProductionSafetyAssessment:
        normalized = _required(opportunity_id, "opportunity_id")
        snapshot = self._repository.get_production_safety_snapshot(normalized)
        if snapshot is None:
            raise ProductionSafetySnapshotNotFoundError(
                "production safety snapshot not found"
            )
        if snapshot.opportunity_id != normalized:
            raise ProductionSafetySnapshotIdentityConflictError(
                "production safety snapshot opportunity_id does not match request"
            )
        return snapshot.assessment
