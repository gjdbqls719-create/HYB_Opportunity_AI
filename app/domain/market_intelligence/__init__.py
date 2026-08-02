"""Common Market Intelligence evidence and observation identity contracts."""

from app.domain.market_intelligence.artifact import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
)
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
from app.domain.market_intelligence.demand_analysis import (
    DemandAssessment,
    DemandAssessmentAvailability,
    DemandEvidenceUnavailableError,
    DemandLevel,
    PopularityLevel,
    ReviewQuality,
    analyze_demand,
)
from app.domain.market_intelligence.external_signal import (
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
)
from app.domain.market_intelligence.identity import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.market_intelligence.ocr_candidate import OCRCandidate, OCRField
from app.domain.market_intelligence.ocr_result import (
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)
from app.domain.market_intelligence.verification import HumanVerification

__all__ = [
    "ArtifactOrigin",
    "ArtifactReference",
    "ArtifactType",
    "MarketEvidence",
    "MarketEvidenceStatus",
    "CompetitionObservation",
    "CompetitionAssessment",
    "CompetitionEvidenceUnavailableError",
    "CompetitionLevel",
    "DemandObservation",
    "DemandAssessment",
    "DemandAssessmentAvailability",
    "DemandEvidenceUnavailableError",
    "DemandLevel",
    "ExternalMarketSignal",
    "ExternalSignalDirection",
    "ExternalSignalSourceType",
    "MarketObservationIdentity",
    "MarketObservationScope",
    "OCRCandidate",
    "OCRField",
    "OCRFieldResult",
    "OCRProvider",
    "OCRResult",
    "PricePressure",
    "PopularityLevel",
    "ReviewQuality",
    "RocketCompetitionLevel",
    "HumanVerification",
    "analyze_competition",
    "analyze_demand",
]
