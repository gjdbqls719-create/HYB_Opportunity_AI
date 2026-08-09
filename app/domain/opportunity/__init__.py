"""Opportunity domain models and evaluation values."""

from app.domain.opportunity.decision import OpportunityDecision
from app.domain.opportunity.actual_economics import (
    ActualEconomics,
    ActualEconomicsAction,
    ActualEconomicsEvent,
    ActualEconomicsStatus,
    InvalidActualEconomicsTransitionError,
)
from app.domain.opportunity.evaluation import OpportunityEvaluation
from app.domain.opportunity.economics import (
    EconomicEvidence,
    EconomicsCalculation,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.domain.opportunity.models import (
    OpportunityFactors,
    OpportunityGrade,
    OpportunityScore,
)
from app.domain.opportunity.variance import (
    EconomicsVariance,
    EstimatedEconomicsSnapshot,
    MetricVariance,
    SnapshotValidationError,
    VarianceAvailability,
    calculate_economics_variance,
)
from app.domain.opportunity.reasons import OpportunityReason
from app.domain.opportunity.production_safety import (
    ProductionSafetyAssessment,
    ProductionSafetyStatus,
)
from app.domain.opportunity.economics_source_composition import (
    ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME,
    ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION,
    ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION,
    EconomicsSourceBlockingCode,
    EconomicsSourceBlockingReason,
    EconomicsSourceComposition,
    EconomicsSourceCompositionState,
)
from app.domain.opportunity.conservative_economics import (
    CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION,
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    CONSERVATIVE_ECONOMICS_ROUNDING,
    CONSERVATIVE_ECONOMICS_SCHEMA_VERSION,
    ConservativeEconomicsAssumption,
    ConservativeEconomicsAssumptionKind,
    ConservativeEconomicsBlockingCode,
    ConservativeEconomicsBlockingReason,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
    calculate_conservative_unit_values,
    conservative_decimal_context,
)


from app.domain.opportunity.founder_decision import FounderDecision, FounderDecisionType
from app.domain.opportunity.lifecycle import (
    ArchivedLifecycleError,
    InvalidLifecycleTransitionError,
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.domain.opportunity.domestic_selling import (
    DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION,
    DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION,
    DomesticProductEquivalenceVerification,
    DomesticSellingOpportunityAdmission,
)

__all__ = [
    "ActualEconomics",
    "ActualEconomicsAction",
    "ActualEconomicsEvent",
    "ActualEconomicsStatus",
    "ArchivedLifecycleError",
    "EconomicEvidence",
    "EconomicsCalculation",
    "EconomicsVariance",
    "EconomicsSourceBlockingCode",
    "EconomicsSourceBlockingReason",
    "EconomicsSourceComposition",
    "EconomicsSourceCompositionState",
    "ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME",
    "ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION",
    "ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION",
    "CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION",
    "CONSERVATIVE_ECONOMICS_POLICY_NAME",
    "CONSERVATIVE_ECONOMICS_POLICY_VERSION",
    "CONSERVATIVE_ECONOMICS_ROUNDING",
    "CONSERVATIVE_ECONOMICS_SCHEMA_VERSION",
    "ConservativeEconomicsAssumption",
    "ConservativeEconomicsAssumptionKind",
    "ConservativeEconomicsBlockingCode",
    "ConservativeEconomicsBlockingReason",
    "ConservativeEconomicsResult",
    "ConservativeEconomicsStatus",
    "DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION",
    "DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION",
    "DomesticProductEquivalenceVerification",
    "DomesticSellingOpportunityAdmission",
    "calculate_conservative_unit_values",
    "conservative_decimal_context",
    "EstimatedEconomicsSnapshot",
    "EvidenceStatus",
    "FounderDecision",
    "FounderDecisionType",
    "InvalidLifecycleTransitionError",
    "InvalidActualEconomicsTransitionError",
    "MoneyInput",
    "MetricVariance",
    "OpportunityDecision",
    "OpportunityEvaluation",
    "OpportunityFactors",
    "OpportunityGrade",
    "OpportunityLifecycle",
    "OpportunityLifecycleAction",
    "OpportunityLifecycleStatus",
    "OpportunityLifecycleTransition",
    "OpportunityReason",
    "OpportunityScore",
    "ProductionSafetyAssessment",
    "ProductionSafetyStatus",
    "RateInput",
    "SnapshotValidationError",
    "VerifiedEconomicsInput",
    "VarianceAvailability",
    "calculate_economics_variance",
]
