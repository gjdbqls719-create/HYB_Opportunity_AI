from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.opportunity import VerifiedEconomicsInput


VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION = "verified-economics-snapshot-v1"


class VerifiedEconomicsSnapshotNotFoundError(LookupError):
    pass


class VerifiedEconomicsSnapshotIdentityConflictError(ValueError):
    pass


class DuplicateVerifiedEconomicsSnapshotError(
    VerifiedEconomicsSnapshotIdentityConflictError
):
    pass


class MalformedVerifiedEconomicsSnapshotError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedEconomicsSnapshot:
    opportunity_id: str
    inputs: VerifiedEconomicsInput
    snapshot_at: datetime
    schema_version: str = VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_id, str) or not self.opportunity_id.strip():
            raise ValueError("opportunity_id must be non-empty text")
        object.__setattr__(self, "opportunity_id", self.opportunity_id.strip())
        if not isinstance(self.inputs, VerifiedEconomicsInput):
            raise TypeError("inputs must be VerifiedEconomicsInput")
        if not isinstance(self.snapshot_at, datetime):
            raise TypeError("snapshot_at must be a datetime")
        if self.snapshot_at.tzinfo is None or self.snapshot_at.utcoffset() is None:
            raise ValueError("snapshot_at must be timezone-aware")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("schema_version must be non-empty text")
        object.__setattr__(self, "schema_version", self.schema_version.strip())


class VerifiedEconomicsSnapshotRepository(Protocol):
    def get_verified_economics_snapshot(
        self, opportunity_id: str
    ) -> VerifiedEconomicsSnapshot | None:
        ...


class GetVerifiedEconomicsSnapshot:
    def __init__(self, repository: VerifiedEconomicsSnapshotRepository) -> None:
        self._repository = repository

    def execute(self, opportunity_id: str) -> VerifiedEconomicsInput:
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise ValueError("opportunity_id must be non-empty text")
        normalized = opportunity_id.strip()
        snapshot = self._repository.get_verified_economics_snapshot(normalized)
        if snapshot is None:
            raise VerifiedEconomicsSnapshotNotFoundError(
                "verified economics snapshot not found"
            )
        if snapshot.opportunity_id != normalized:
            raise VerifiedEconomicsSnapshotIdentityConflictError(
                "verified economics snapshot opportunity_id does not match request"
            )
        return snapshot.inputs
