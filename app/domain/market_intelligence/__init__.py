"""Common Market Intelligence evidence and observation identity contracts."""

from app.domain.market_intelligence.artifact import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
)
from app.domain.market_intelligence.evidence import MarketEvidence, MarketEvidenceStatus
from app.domain.market_intelligence.competition import CompetitionObservation
from app.domain.market_intelligence.assessment_subject import (
    AssessmentSubject,
    AssessmentSubjectKind,
    assessment_subject_kind,
    is_new_to_market_target_subject,
)
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
from app.domain.market_intelligence.review_session import (
    CandidateSkipRecord,
    CandidateReviewStatus,
    InvalidReviewSessionTransitionError,
    ReviewSession,
    ReviewSessionStatus,
)
from app.domain.market_intelligence.domestic_market_validation import (
    DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION,
    DOMESTIC_MARKET_VALIDATION_POLICY_NAME,
    DOMESTIC_MARKET_VALIDATION_POLICY_VERSION,
    DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION,
    DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION,
    DomesticMarketAnalysisSourceManifest,
    DomesticMarketMetricEvidence,
    DomesticMarketValidationAssessment,
    DomesticMarketValidationReason,
    DomesticMarketValidationReasonCode,
    DomesticMarketValidationSourceManifest,
    DomesticMarketValidationState,
    DomesticMarketVerification,
)

__all__ = [
    "AssessmentSubject",
    "AssessmentSubjectKind",
    "CandidateSkipRecord",
    "CandidateReviewStatus",
    "ArtifactOrigin",
    "ArtifactReference",
    "ArtifactType",
    "MarketEvidence",
    "MarketEvidenceStatus",
    "CompetitionObservation",
    "assessment_subject_kind",
    "is_new_to_market_target_subject",
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
    "InvalidReviewSessionTransitionError",
    "ReviewSession",
    "ReviewSessionStatus",
    "analyze_competition",
    "analyze_demand",
    "DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION",
    "DOMESTIC_MARKET_VALIDATION_POLICY_NAME",
    "DOMESTIC_MARKET_VALIDATION_POLICY_VERSION",
    "DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION",
    "DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION",
    "DomesticMarketAnalysisSourceManifest",
    "DomesticMarketMetricEvidence",
    "DomesticMarketValidationAssessment",
    "DomesticMarketValidationReason",
    "DomesticMarketValidationReasonCode",
    "DomesticMarketValidationSourceManifest",
    "DomesticMarketValidationState",
    "DomesticMarketVerification",
]
