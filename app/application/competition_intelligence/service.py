from __future__ import annotations

from app.application.competition_intelligence.models import (
    CompetitionIntelligenceResult,
    CompetitionIntelligenceStatus,
)
from app.application.competition_intelligence.ports import MarketObservationRepository
from app.application.competition_intelligence.use_cases import AnalyzeCompetition
from app.application.market_observation import MarketObservationType
from app.domain.market_intelligence import (
    CompetitionEvidenceUnavailableError,
    CompetitionObservation,
    analyze_competition,
)


class CompetitionIntelligenceService:
    def __init__(self, repository: MarketObservationRepository) -> None:
        if not isinstance(repository, MarketObservationRepository):
            raise TypeError("repository must implement MarketObservationRepository")
        self._repository = repository

    def analyze(self, query: AnalyzeCompetition) -> CompetitionIntelligenceResult:
        observation = self._repository.get_latest(
            MarketObservationType.COMPETITION,
            query.identity,
        )
        if observation is None:
            return CompetitionIntelligenceResult(
                status=CompetitionIntelligenceStatus.UNAVAILABLE,
                missing_metrics=("competition_observation",),
            )
        if not isinstance(observation, CompetitionObservation):
            raise TypeError("competition repository query returned wrong observation type")
        try:
            assessment = analyze_competition(
                observation,
                generated_at=query.generated_at,
                schema_version=query.schema_version,
            )
        except CompetitionEvidenceUnavailableError as error:
            return CompetitionIntelligenceResult(
                status=CompetitionIntelligenceStatus.UNAVAILABLE,
                missing_metrics=error.missing_metrics,
            )
        return CompetitionIntelligenceResult(
            status=CompetitionIntelligenceStatus.ASSESSED,
            assessment=assessment,
        )
