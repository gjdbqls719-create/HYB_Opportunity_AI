from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.market_intelligence import DemandAssessment


class DemandIntelligenceStatus(StrEnum):
    ASSESSED = "assessed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DemandIntelligenceResult:
    status: DemandIntelligenceStatus
    assessment: DemandAssessment | None = None
    missing_metrics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, DemandIntelligenceStatus):
            object.__setattr__(self, "status", DemandIntelligenceStatus(self.status))
        object.__setattr__(self, "missing_metrics", tuple(self.missing_metrics))
        if self.status is DemandIntelligenceStatus.ASSESSED:
            if not isinstance(self.assessment, DemandAssessment):
                raise ValueError("assessed result requires DemandAssessment")
            if self.missing_metrics:
                raise ValueError("assessed result cannot contain missing_metrics")
        else:
            if self.assessment is not None:
                raise ValueError("unavailable result cannot contain assessment")
            if not self.missing_metrics:
                raise ValueError("unavailable result requires missing_metrics")
