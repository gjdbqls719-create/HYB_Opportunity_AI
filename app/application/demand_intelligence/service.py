from __future__ import annotations

from app.application.demand_intelligence.models import (
    DemandIntelligenceResult,
    DemandIntelligenceStatus,
)
from app.application.demand_intelligence.ports import MarketObservationRepository
from app.application.demand_intelligence.use_cases import AnalyzeDemand
from app.application.market_observation import MarketObservationType
from app.domain.market_intelligence import (
    DemandEvidenceUnavailableError,
    DemandObservation,
    analyze_demand,
)


class DemandIntelligenceService:
    def __init__(self, repository: MarketObservationRepository) -> None:
        if not isinstance(repository, MarketObservationRepository):
            raise TypeError("repository must implement MarketObservationRepository")
        self._repository = repository

    def analyze(self, query: AnalyzeDemand) -> DemandIntelligenceResult:
        observation = self._repository.get_latest(MarketObservationType.DEMAND, query.identity)
        if observation is None:
            return DemandIntelligenceResult(
                status=DemandIntelligenceStatus.UNAVAILABLE,
                missing_metrics=("demand_observation",),
            )
        if not isinstance(observation, DemandObservation):
            raise TypeError("demand repository query returned wrong observation type")
        try:
            assessment = analyze_demand(
                observation,
                generated_at=query.generated_at,
                schema_version=query.schema_version,
            )
        except DemandEvidenceUnavailableError as error:
            return DemandIntelligenceResult(
                status=DemandIntelligenceStatus.UNAVAILABLE,
                missing_metrics=error.missing_metrics,
            )
        return DemandIntelligenceResult(
            status=DemandIntelligenceStatus.ASSESSED,
            assessment=assessment,
        )
