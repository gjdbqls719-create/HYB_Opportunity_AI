"""Common Market Intelligence evidence and observation identity contracts."""

from app.domain.market_intelligence.evidence import MarketEvidence, MarketEvidenceStatus
from app.domain.market_intelligence.competition import CompetitionObservation
from app.domain.market_intelligence.competition_analysis import (
    CompetitionAssessment,
    CompetitionEvidenceUnavailableError,
    CompetitionLevel,
    PricePressure,
    RocketCompetitionLevel,
    analyze_competition,
)
from app.domain.market_intelligence.demand import DemandObservation
from app.domain.market_intelligence.external_signal import (
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
)
from app.domain.market_intelligence.identity import (
    MarketObservationIdentity,
    MarketObservationScope,
)

__all__ = [
    "MarketEvidence",
    "MarketEvidenceStatus",
    "CompetitionObservation",
    "CompetitionAssessment",
    "CompetitionEvidenceUnavailableError",
    "CompetitionLevel",
    "DemandObservation",
    "ExternalMarketSignal",
    "ExternalSignalDirection",
    "ExternalSignalSourceType",
    "MarketObservationIdentity",
    "MarketObservationScope",
    "PricePressure",
    "RocketCompetitionLevel",
    "analyze_competition",
]
