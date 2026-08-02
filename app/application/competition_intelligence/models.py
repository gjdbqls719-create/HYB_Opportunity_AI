from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.market_intelligence import CompetitionAssessment


class CompetitionIntelligenceStatus(StrEnum):
    ASSESSED = "assessed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CompetitionIntelligenceResult:
    status: CompetitionIntelligenceStatus
    assessment: CompetitionAssessment | None = None
    missing_metrics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, CompetitionIntelligenceStatus):
            object.__setattr__(self, "status", CompetitionIntelligenceStatus(self.status))
        object.__setattr__(self, "missing_metrics", tuple(self.missing_metrics))
        if self.status is CompetitionIntelligenceStatus.ASSESSED:
            if not isinstance(self.assessment, CompetitionAssessment):
                raise ValueError("assessed result requires CompetitionAssessment")
            if self.missing_metrics:
                raise ValueError("assessed result cannot contain missing_metrics")
        else:
            if self.assessment is not None:
                raise ValueError("unavailable result cannot contain assessment")
            if not self.missing_metrics:
                raise ValueError("unavailable result requires missing_metrics")
