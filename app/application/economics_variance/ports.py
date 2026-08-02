from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.application.actual_economics import ActualEconomicsRepository
from app.domain.opportunity import EstimatedEconomicsSnapshot


class EstimatedBaselineNotFoundError(LookupError):
    pass


class ActualEconomicsForVarianceNotFoundError(LookupError):
    pass


class DuplicateEstimatedBaselineError(ValueError):
    pass


@runtime_checkable
class EstimatedEconomicsSnapshotRepository(Protocol):
    def create(self, snapshot: EstimatedEconomicsSnapshot) -> None: ...
    def get_admission_baseline(self, opportunity_id: str) -> EstimatedEconomicsSnapshot | None: ...


__all__ = [
    "ActualEconomicsForVarianceNotFoundError",
    "ActualEconomicsRepository",
    "DuplicateEstimatedBaselineError",
    "EstimatedBaselineNotFoundError",
    "EstimatedEconomicsSnapshotRepository",
]
