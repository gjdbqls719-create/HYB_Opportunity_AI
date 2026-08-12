from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
import sqlite3
from typing import Any, Literal

import requests

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from engine.orchestrator import find_best_opportunities
from presentation.dashboard import build_dashboard_cards
from presentation.dashboard_list import build_opportunity_list_card
from app.application.sourcing import (
    AdmitFounderSourcing,
    AdmitFounderSourcingCommand,
    DomesticSellingProductLineageReference,
    InvalidSourcingCommandError,
    ReviseFounderSourcingQuote,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionNotFoundError,
    SourcingAdmissionReplayConflictError,
    SourcingAuthorityError,
    SourcingAuthorityProductionEntry,
    SourcingIdentityGenerationError,
    SourcingProductMatchNotVerifiedError,
    SourcingQuoteRevisionConflictError,
    SourcingDomesticSellingLineageError,
)
from app.application.domestic_selling_opportunity import (
    AdmitDomesticSellingOpportunity,
    AdmitDomesticSellingOpportunityCommand,
    DomesticSellingOpportunityCardinalityConflictError,
    DomesticSellingOpportunityError,
    DomesticSellingOpportunityLineageError,
    DomesticSellingOpportunityPolicyError,
    DomesticSellingOpportunityReplayConflictError,
    DomesticSellingOpportunitySourceNotFoundError,
    DomesticSellingOpportunityVerificationError,
)
from app.application.new_to_market_domestic_selling import (
    AdmitNewToMarketDomesticSellingOpportunity,
    AdmitNewToMarketDomesticSellingOpportunityCommand,
    NewToMarketDomesticSellingCardinalityConflictError,
    NewToMarketDomesticSellingError,
    NewToMarketDomesticSellingLineageError,
    NewToMarketDomesticSellingPolicyError,
    NewToMarketDomesticSellingReplayConflictError,
    NewToMarketDomesticSellingSourceNotFoundError,
    NewToMarketDomesticSellingVerificationError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    BoundedKRSearchConclusion,
    BoundedKRSearchManifest,
    BoundedKRSearchScopeKind,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    DomesticSellingProductLineage,
    LandedCostComponentKind,
    MatchVerificationStatus,
    SellingProductLineage,
    ShippingScope,
    ShippingTerm,
    SourcingEvidenceKind,
    SourcingEvidenceReference,
    SourcingMoneyFact,
    SourcingQuantityFact,
    SourcingEconomicsSourceReference,
)
from app.infrastructure.sourcing import (
    MalformedSourcingAuthorityPersistenceError,
    ProductionFounderSourcingAdmissionIdentityGenerator,
    ProductionProductMatchVerificationIdentityGenerator,
    ProductionSourcingProductIdentityGenerator,
    ProductionSupplierIdentityGenerator,
    ProductionSupplierQuoteIdentityGenerator,
    SQLiteSourcingAuthorityRepository,
    SourcingAuthorityPersistenceError,
    UnsupportedSourcingAuthorityVersionError,
)
from app.infrastructure.domestic_selling_opportunity import (
    DomesticSellingOpportunityPersistenceError,
    MalformedDomesticSellingOpportunityPersistenceError,
    ProductionDomesticSellingOpportunityAdmissionIdentityGenerator,
    ProductionDomesticSellingOpportunityIdentityGenerator,
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.new_to_market_domestic_selling import (
    MalformedNewToMarketDomesticSellingPersistenceError,
    NewToMarketDomesticSellingPersistenceError,
    ProductionNewToMarketDomesticOpportunityIdentityGenerator,
    ProductionNewToMarketDomesticSellingAdmissionIdentityGenerator,
    ProductionNewToMarketDomesticSellingTargetIdentityGenerator,
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)
from app.application.opportunity_lifecycle import (
    LifecycleNotFoundError,
    LifecycleVersionConflictError,
)
from app.application.dashboard_api import (
    DashboardDecisionConflictError,
    DashboardDecisionNotFoundError,
    DashboardDecisionUnavailableError,
    GetOpportunityDecisionDashboard,
    ProductionOpportunityDecisionDashboardProvider,
)
from app.application.decision_composition import (
    DecisionCompositionCommitError,
    DecisionCompositionIdentityConflictError,
    DecisionCompositionNotFoundError,
    DecisionCompositionPersistenceError,
    DecisionCompositionProjectionError,
    DecisionCompositionProvenanceError,
    DecisionCompositionVersionConflictError,
    DuplicateDecisionCompositionError,
    MalformedDecisionCompositionError,
    MissingDecisionCompositionSourceError,
    UnsupportedDecisionCompositionVersionError,
    FinalizeDecisionComposition,
)
from app.application.decision_composition_api import (
    FinalizeOpportunityDecisionComposition,
    FinalizeOpportunityDecisionCompositionCommand,
)
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    DuplicateActiveValidationError,
    OpportunityValidationService,
    ValidationActionCommand,
    ValidationQueueQuery,
)
from app.application.opportunity_review_binding import OpportunityReviewBindingConflictError, OpportunityReviewBindingNotFoundError, OpportunityReviewBindingPersistenceError
from app.application.opportunity_review_ui import OpportunityReviewUIQueryService
from app.application.decision_readiness import DecisionReadinessNotFoundError, DecisionReadinessService
from app.application.production_safety_api import EvaluateProductionSafetyApi, GetProductionSafetyOperationalDetail
from app.application.production_safety_evaluation import (
    EvaluateAndPersistProductionSafety,
    EvaluateAndPersistProductionSafetyCommand,
    ProductionSafetyChainNotFoundError,
    ProductionSafetyEvaluationCommandConflictError,
    ProductionSafetyEvaluationPersistenceError,
    ProductionSafetyProductNotFoundError,
    ProductionSafetySelectedProductConflictError,
    ProductionSafetySourceLineageError,
)
from app.application.production_safety_runtime_adapter import ProductionSafetyRuntimeAdapter
from app.application.discovery import (
    FOUNDER_CONSERVATIVE_EBAY_US_V1,
    DiscoveryCompletionReplayError,
    DiscoveryRuntimeCorrelationError,
    PersistedDiscoveryExecutionEntry,
    PersistedDiscoveryResultReader,
    resolve_founder_discovery_policy_profile,
)
from app.application.ocr import (
    AdmitExternalOCRExecution,
    ArtifactAdmissionConflictError,
    ExternalOCRAdmissionResult,
    ExternalOCRCandidateAdmission,
    OCRAdmissionDependencyError,
    OCRAdmissionValidationError,
    OCRExecutionConflictError,
    OCRExecutionPersistenceError,
)
from app.application.candidate_issuance import (
    CandidateDiscoveryCommandNotFoundError,
    CandidateDiscoveryReferenceConflictError,
    CandidateDiscoveryResultNotFoundError,
    CandidateExecutionMismatchError,
    CandidateFinalizedGroupNotFoundError,
    CandidateGroupNotInResultError,
    CandidateIdentityGenerationError,
    CandidateIssuanceCommandConflictError,
    CandidateIssuanceNotFoundError,
    CandidateIssuanceProductionEntry,
    CandidateIssuanceReplayConflictError,
    CandidateLineageConflictError,
    CandidateMarketIdentityConflictError,
    CandidatePersistenceError,
    DuplicateOpportunityCandidateError,
    IssueOpportunityCandidateCommand,
    MalformedCandidateIssuanceCommandError,
)
from app.application.candidate_promotion import (
    CandidateAlreadyPromotedError,
    CandidateForPromotionNotFoundError,
    CandidatePromotionCommandConflictError,
    CandidatePromotionCommitError,
    CandidatePromotionContextNotFoundError,
    CandidatePromotionHistoryError,
    CandidatePromotionIdentityConflictError,
    CandidatePromotionMarketIdentityConflictError,
    CandidatePromotionPersistenceError,
    CandidatePromotionProductionEntry,
    CandidatePromotionReceiptError,
    MalformedCandidatePromotionPersistenceError,
    OpportunityAlreadyBoundToCandidateError,
    PromoteOpportunityCandidateCommand,
    PromoteOpportunityCandidateV2Command,
    CandidatePromotionV2SourceNotFoundError,
    CandidatePromotionV2LineageConflictError,
)
from app.application.product_snapshot_capture import (
    CandidateProductSnapshotCaptureProductionEntry,
    CandidateProductSnapshotCaptureRequest,
    ProductSnapshotSourceConflictError,
    ProductSnapshotSourceObservationNotFoundError,
    SnapshotOwnerCommandConflictError,
    SnapshotOwnerPersistenceError,
)
from app.application.price_analysis import (
    CandidatePriceAnalysisProductionEntry,
    CandidatePriceAnalysisRequest,
    PriceAnalysisCandidateMismatchError,
    PriceAnalysisCommandConflictError,
    PriceAnalysisExecutionError,
    PriceAnalysisGroupMismatchError,
    PriceAnalysisMarketIdentityConflictError,
    PriceAnalysisPersistenceError,
    PriceAnalysisProductOrderConflictError,
    PriceAnalysisSourceNotFoundError,
)
from app.application.economics_calculation_owner import (
    EconomicsCalculationBindingConflictError,
    EconomicsCalculationCommandConflictError,
    EconomicsCalculationExecutionError,
    EconomicsCalculationMarketIdentityConflictError,
    EconomicsCalculationOwnerPersistenceError,
    EconomicsCalculationPriceSourceConflictError,
    EconomicsCalculationSourceNotFoundError,
    EconomicsCalculationVerifiedSourceConflictError,
    EconomicsSnapshotProductionEntry,
    EconomicsSnapshotProductionRequest,
)
from app.application.conservative_economics import (
    ConservativeEconomicsOpportunityConflictError,
    ConservativeEconomicsPolicyError,
    ConservativeEconomicsProductionEntry,
    ConservativeEconomicsProductionRequest,
    ConservativeEconomicsReplayConflictError,
    ConservativeEconomicsScenario,
    ConservativeEconomicsSourceError,
)
from app.application.capital_readiness import (
    CapitalReadinessPolicyError,
    CapitalReadinessProductionEntry,
    CapitalReadinessProductionRequest,
    CapitalReadinessReplayConflictError,
    CapitalReadinessSourceConflictError,
    CapitalReadinessSourceNotFoundError,
    EvaluateCapitalReadiness,
)
from app.application.capital_investment import (
    AdmitDeployableCapitalSnapshot,
    AdmitDeployableCapitalSnapshotCommand,
    AdmitIntendedOrderQuantity,
    CapitalInvestmentLineageError,
    CapitalInvestmentReplayConflictError,
    CapitalInvestmentSourceNotFoundError,
)
from app.application.capital_requirement import (
    CalculatePlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementLineageError,
    PlannedAcquisitionCapitalRequirementPolicyError,
    PlannedAcquisitionCapitalRequirementReplayConflictError,
    PlannedAcquisitionCapitalRequirementSourceNotFoundError,
)
from app.application.capital_gate import (
    CapitalGatePolicyError,
    CapitalGateReplayConflictError,
    CapitalGateSourceNotFoundError,
    EvaluateCapitalGate,
)
from app.application.founder_capital_approval import (
    ApproveFounderCapital,
    FounderCapitalApprovalAmountError,
    FounderCapitalApprovalCurrencyError,
    FounderCapitalApprovalGateStateError,
    FounderCapitalApprovalPolicyError,
    FounderCapitalApprovalReplayConflictError,
    FounderCapitalApprovalSourceNotFoundError,
)
from app.application.real_money_execution_intent import (
    EvaluateRealMoneyExecutionIntent,
    RealMoneyExecutionIntentPolicyError,
    RealMoneyExecutionIntentReadyConflictError,
    RealMoneyExecutionIntentReplayConflictError,
    RealMoneyExecutionIntentSourceNotFoundError,
)
from app.application.purchase_execution import (
    PurchaseExecutionCardinalityConflictError,
    PurchaseExecutionExactMatchError,
    PurchaseExecutionIntentStateError,
    PurchaseExecutionReplayConflictError,
    PurchaseExecutionSourceNotFoundError,
    RecordPurchaseExecution,
)
from app.application.actual_acquisition_settlement import (
    ActualAcquisitionSettlementOpportunityConflictError,
    ActualAcquisitionSettlementReplayConflictError,
    ActualAcquisitionSettlementRevisionConflictError,
    ActualAcquisitionSettlementSourceNotFoundError,
    ActualAcquisitionSettlementTerminalConflictError,
    AdmitActualAcquisitionSettlement,
)
from app.application.goods_receipt import (
    AdmitGoodsReceipt,
    GoodsReceiptCumulativeQuantityConflictError,
    GoodsReceiptOpportunityConflictError,
    GoodsReceiptReplayConflictError,
    GoodsReceiptSourceLineageError,
    GoodsReceiptSourceNotFoundError,
    GoodsReceiptUnitConflictError,
)
from app.application.actual_sale_settlement import (
    AdmitActualSaleSettlement,
    ActualSaleSettlementOpportunityConflictError,
    ActualSaleSettlementOversellConflictError,
    ActualSaleSettlementProductConflictError,
    ActualSaleSettlementReplayConflictError,
    ActualSaleSettlementReportConflictError,
    ActualSaleSettlementRevisionConflictError,
    ActualSaleSettlementSourceLineageError,
    ActualSaleSettlementSourceNotFoundError,
    ActualSaleSettlementTerminalConflictError,
    ActualSaleSettlementWindowConflictError,
)
from app.application.actual_outcome import (
    ActualOutcomeOpportunityConflictError,
    ActualOutcomeReplayConflictError,
    ActualOutcomeSourceConflictError,
    ActualOutcomeSourceIntegrityError,
    ActualOutcomeSourceNotFoundError,
    CalculateActualOutcome,
)
from app.application.conservative_actual_variance import (
    CalculateConservativeActualVariance,
    ConservativeActualVarianceOpportunityConflictError,
    ConservativeActualVariancePolicyError,
    ConservativeActualVarianceProductionEntry,
    ConservativeActualVarianceProductionRequest,
    ConservativeActualVarianceReplayConflictError,
    ConservativeActualVarianceSourceConflictError,
    ConservativeActualVarianceSourceIntegrityError,
    ConservativeActualVarianceSourceNotFoundError,
)
from app.application.owned_inventory import (
    GetOwnedInventoryPositionsV2,
    OwnedInventoryOpportunityNotFoundError,
    OwnedInventorySourceConflictError,
)
from app.application.capital_production import (
    ActualAcquisitionSettlementProductionEntry,
    ActualAcquisitionSettlementProductionRequest,
    GoodsReceiptProductionEntry,
    GoodsReceiptProductionRequest,
    ActualSaleSettlementProductionEntry,
    ActualSaleSettlementProductionRequest,
    ActualOutcomeProductionEntry,
    ActualOutcomeProductionRequest,
    CapitalGateProductionEntry,
    CapitalGateProductionRequest,
    CapitalProductionOpportunityConflictError,
    FounderCapitalApprovalProductionEntry,
    FounderCapitalApprovalProductionRequest,
    IntendedOrderQuantityProductionEntry,
    IntendedOrderQuantityProductionRequest,
    PlannedCapitalRequirementProductionEntry,
    PlannedCapitalRequirementProductionRequest,
    RealMoneyExecutionIntentProductionEntry,
    RealMoneyExecutionIntentProductionRequest,
    PurchaseExecutionProductionEntry,
    PurchaseExecutionProductionRequest,
)
from app.domain.capital import (
    ActualAcquisitionCostCategory,
    ActualAcquisitionCostFact,
    ActualAcquisitionEvidenceReference,
    ActualAcquisitionFXSettlement,
    ActualAcquisitionFactAvailability,
    GoodsReceiptEvidenceReference,
    OtherMandatoryAcquisitionCosts,
    OtherMandatoryAcquisitionCostItem,
    PurchaseExecutionEvidenceReference,
    ActualSaleEvidenceReference,
    ActualSaleFactAvailability,
    ActualSaleFinalityFact,
    ActualSaleMonetaryCategory,
    ActualSaleMonetaryFact,
    ActualSalePayoutFact,
    ActualSalePayoutReconciliationState,
    OtherActualSaleCostItem,
    OtherActualSaleCosts,
    UpfrontCostScopeStatus,
)
from app.application.economics_production import (
    AcquisitionNormalizationProductionEntry,
    AcquisitionNormalizationProductionRequest,
    EconomicsProductionOpportunityConflictError,
    EconomicsProductionSourceNotFoundError,
    EconomicsSourceCompositionProductionEntry,
    EconomicsSourceCompositionProductionRequest,
    LandedCostProductionEntry,
    LandedCostProductionRequest,
    ShippingAllocationProductionEntry,
    ShippingAllocationProductionRequest,
    SourcingEconomicsBindingProductionEntry,
    SourcingEconomicsBindingProductionRequest,
)
from app.application.economics_source_composition import (
    ComposeEconomicsSources,
    EconomicsSourceCompositionPolicyError,
    EconomicsSourceCompositionReplayConflictError,
    EconomicsSourceCompositionSourceError,
)
from app.application.sourcing import (
    AcquisitionCostNormalizationPolicyError,
    AcquisitionCostNormalizationReplayConflictError,
    AcquisitionCostNormalizationSourceError,
    AdmitFXObservation,
    AdmitFXObservationCommand,
    AdmitShippingAllocationAuthority,
    BindSourcingEconomicsSource,
    ComposeLandedCost,
    FXObservationReplayConflictError,
    LandedCostCompositionExactSourceError,
    LandedCostCompositionOpportunityMismatchError,
    LandedCostCompositionReplayConflictError,
    LandedCostCompositionSourceNotFoundError,
    NormalizeAcquisitionCosts,
    ShippingAllocationAuthorityReplayConflictError,
    ShippingAllocationBasisConflictError,
    ShippingAllocationComponentNotFoundError,
    ShippingAllocationOpportunityMismatchError,
    ShippingAllocationProvenanceError,
    ShippingAllocationSourceNotFoundError,
    SourcingEconomicsBindingNotFoundError,
    SourcingEconomicsBindingOpportunityMismatchError,
    SourcingEconomicsBindingReplayConflictError,
    SourcingEconomicsExactRevisionError,
    SourcingEconomicsSourceNotFoundError,
    CriticalCostCompletenessProductionEntry,
    CriticalCostCompletenessProductionRequest,
    CriticalCostCompletenessReplayConflictError,
    CriticalCostSourceMismatchError,
    CriticalCostSourceNotFoundError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
    PersistCriticalCostCompleteness,
)
from app.application.snapshot_chain_binding import (
    CompleteSnapshotChainProductionEntry,
    CompleteSnapshotChainProductionRequest,
    SnapshotChainBindingCommandConflictError,
    SnapshotChainBindingConflictError,
    SnapshotChainBindingNotFoundError,
    SnapshotChainBindingPersistenceError,
    SnapshotChainCandidateMismatchError,
    SnapshotChainEconomicsSourceConflictError,
    SnapshotChainIncompleteError,
    SnapshotChainMarketIdentityConflictError,
    SnapshotChainOpportunityMismatchError,
    SnapshotChainPriceSourceConflictError,
    SnapshotChainProductSourceConflictError,
    SnapshotChainVerifiedSourceConflictError,
)
from app.application.discovery_persistence import (
    DiscoveryExecutionIdentityConflictError,
    DiscoveryExecutionNotFoundError,
    DiscoveryExecutionReplayConflict,
    DiscoveryExecutionResultNotFound,
    DiscoveryGroupConflictError,
    DiscoveryGroupMembershipError,
    MalformedDiscoveryExecutionResult,
    MalformedDiscoveryGroupPersistenceError,
    DiscoveryObservationConflictError,
    DiscoveryPersistenceError,
    DiscoveryReplayConflict,
    DuplicateDiscoveryExecutionError,
    DuplicateDiscoveryObservationError,
    DuplicateFinalizedGroupError,
    MissingDiscoveryCommand,
    PersistDiscoveryCommand,
)
from app.application.verified_economics_admission import (
    FinalizeVerifiedEconomicsAdmission,
    FinalizeVerifiedEconomicsAdmissionCommand,
    VerifiedEconomicsAdmissionConflictError,
    VerifiedEconomicsAdmissionNotFoundError,
    VerifiedEconomicsAdmissionPersistenceError,
)
from app.application.competition_observation_admission import (
    CompetitionAdmissionConflictError, CompetitionAdmissionNotFoundError,
    CompetitionAdmissionUnavailableError, FinalizeCompetitionObservationAdmission,
    FinalizeCompetitionObservationAdmissionCommand,
)
from app.application.demand_observation_admission import (
    DemandAdmissionConflictError, DemandAdmissionNotFoundError,
    DemandAdmissionUnavailableError, FinalizeDemandObservationAdmission,
    FinalizeDemandObservationAdmissionCommand,
)
from app.application.domestic_market_validation import (
    DomesticMarketValidationPolicyError,
    DomesticMarketValidationProductionEntry,
    DomesticMarketValidationProductionRequest,
    DomesticMarketValidationReplayConflictError,
    DomesticMarketValidationSourceConflictError,
    DomesticMarketValidationSourceNotFoundError,
    ValidateDomesticMarketForCapital,
)
from app.application.review import (
    ApproveCandidateCommand,
    CancelReviewCommand,
    CompleteReviewCommand,
    CorrectCandidateCommand,
    CreateReviewSession,
    DuplicateCandidateReviewError,
    DuplicateReviewSessionError,
    GetReviewSessionDetail,
    GetReviewSession,
    ListReviewSessions,
    PendingCandidatesError,
    ReviewArtifactMismatchError,
    ReviewCandidateMembershipError,
    ReviewCandidateNotFoundError,
    ReviewCommandConflictError,
    ReviewCommandContext,
    ReviewOperatorMismatchError,
    ReviewPersistenceError,
    ReviewSessionNotFoundError,
    ReviewSessionQueryService,
    ReviewSessionVersionConflictError,
    ReviewWorkflowService,
    SkipCandidateCommand,
    StartReviewCommand,
)
from app.application.review_api import (
    ReviewSessionDetailResponseDTO,
    ReviewSessionListResponseDTO,
    ReviewSessionResponseDTO,
)
from app.domain.opportunity import NewToMarketDomesticSellingTargetIdentity
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    CompetitionObservation,
    DemandObservation,
    DomesticMarketVerification,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    InvalidReviewSessionTransitionError,
    MarketObservationIdentity,
    MarketObservationScope,
    MarketEvidence,
    MarketEvidenceStatus,
    OCRField,
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)
from app.domain.opportunity import (
    EconomicEvidence,
    EvidenceStatus,
    InvalidLifecycleTransitionError,
    MoneyInput,
    OpportunityLifecycleStatus,
    RateInput,
    VerifiedEconomicsInput,
)
from app.domain.economics_calculation_snapshot import EconomicsCalculationParameters
from app.domain.discovery_identity import DiscoveryCommand, DiscoveryCommandParameters
from app.infrastructure.discovery import (
    OrchestratorProductionDiscoveryRuntime,
    ProductionCandidateDiscoveryReferenceProvider,
    ProductionCandidateIdentityGenerator,
    ProductionFinalizedGroupIdentityProvider,
    ProductionObservationIdentityProvider,
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.infrastructure.opportunity_validation import (
    ProductionCandidateOpportunityBindingIdentityGenerator,
    ProductionOpportunityIdentityGenerator,
    ProductionCandidatePromotionAdmissionIdentityGenerator,
    SQLiteCandidatePromotionRepository,
    SQLiteValidationQueueRepository,
)
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.infrastructure.price_intelligence import (
    ProductionPriceSnapshotIdentityGenerator,
    SQLitePriceAnalysisRepository,
)
from app.infrastructure.economics_calculation import (
    ProductionEconomicsSnapshotIdentityGenerator,
    SQLiteEconomicsCalculationOwnerRepository,
)
from app.infrastructure.conservative_economics import (
    ConservativeEconomicsPersistenceError,
    ProductionConservativeEconomicsIdentityGenerator,
    SQLiteConservativeEconomicsRepository,
)
from app.infrastructure.capital_readiness import (
    CapitalReadinessPersistenceError,
    ProductionCapitalReadinessIdentityGenerator,
    SQLiteCapitalReadinessRepository,
)
from app.infrastructure.capital_investment import (
    CapitalInvestmentPersistenceError,
    ProductionDeployableCapitalSnapshotIdentityGenerator,
    ProductionIntendedOrderQuantityIdentityGenerator,
    SQLiteCapitalInvestmentFactsRepository,
)
from app.infrastructure.capital_requirement import (
    PlannedAcquisitionCapitalRequirementPersistenceError,
    ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator,
    SQLitePlannedAcquisitionCapitalRequirementRepository,
)
from app.infrastructure.capital_gate import (
    CapitalGatePersistenceError,
    ProductionCapitalGateIdentityGenerator,
    SQLiteCapitalGateRepository,
)
from app.infrastructure.founder_capital_approval import (
    FounderCapitalApprovalPersistenceError,
    ProductionFounderCapitalApprovalIdentityGenerator,
    SQLiteFounderCapitalApprovalRepository,
)
from app.infrastructure.real_money_execution_intent import (
    ProductionRealMoneyExecutionIntentIdentityGenerator,
    RealMoneyExecutionIntentPersistenceError,
    SQLiteRealMoneyExecutionIntentRepository,
)
from app.infrastructure.purchase_execution import (
    ProductionPurchaseExecutionRecordIdentityGenerator,
    PurchaseExecutionPersistenceError,
    SQLitePurchaseExecutionRepository,
)
from app.infrastructure.actual_acquisition_settlement import (
    ActualAcquisitionSettlementPersistenceError,
    ProductionActualAcquisitionSettlementIdentityGenerator,
    SQLiteActualAcquisitionSettlementRepository,
)
from app.infrastructure.goods_receipt import (
    GoodsReceiptPersistenceError,
    ProductionGoodsReceiptRecordIdentityGenerator,
    SQLiteGoodsReceiptRepository,
)
from app.infrastructure.actual_sale_settlement import (
    ActualSaleSettlementPersistenceError,
    ProductionActualSaleSettlementIdentityGenerator,
    SQLiteActualSaleSettlementRepository,
)
from app.infrastructure.actual_outcome import (
    ActualOutcomePersistenceError,
    ProductionActualOutcomeIdentityGenerator,
    SQLiteActualOutcomeRepository,
)
from app.infrastructure.conservative_actual_variance import (
    ConservativeActualVariancePersistenceError,
    ProductionConservativeActualVarianceIdentityGenerator,
    SQLiteConservativeActualVarianceRepository,
)
from app.infrastructure.clock import ProductionUTCClock
from app.infrastructure.economics_source_composition import (
    EconomicsSourceCompositionPersistenceError,
    ProductionEconomicsSourceCompositionIdentityGenerator,
    SQLiteEconomicsSourceCompositionRepository,
)
from app.infrastructure.sourcing import (
    AcquisitionCostNormalizationPersistenceError,
    LandedCostCompositionPersistenceError,
    ProductionAcquisitionCostNormalizationIdentityGenerator,
    ProductionFXObservationIdentityGenerator,
    ProductionShippingAllocationAuthorityIdentityGenerator,
    ProductionSourcingEconomicsBindingIdentityGenerator,
    ShippingAllocationAuthorityPersistenceError,
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteFXObservationRepository,
    SQLiteLandedCostCompositionRepository,
    SQLiteShippingAllocationAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
    SourcingEconomicsBindingPersistenceError,
    CriticalCostCompletenessPersistenceError,
    ProductionCriticalCostCompletenessIdentityGenerator,
    SQLiteCriticalCostCompletenessRepository,
)
from app.infrastructure.sourcing.sqlite_fx_observation_repository import (
    FXObservationPersistenceError,
)
from app.infrastructure.sourcing.identity_suppliers import (
    ProductionLandedCostCompositionIdentityGenerator,
)
from app.infrastructure.domestic_market_validation import (
    DomesticMarketValidationPersistenceError,
    ProductionDomesticMarketValidationIdentityGenerator,
    SQLiteDomesticMarketValidationRepository,
)
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from app.infrastructure.snapshot_chain_identity import (
    ProductionSnapshotChainBindingIdentityGenerator,
)
from app.infrastructure.external_signal_ledger import (
    ProductionOCRCandidateIdentityGenerator,
    SQLiteExternalSignalLedgerRepository,
)
from app.infrastructure.production_safety_evaluation import SQLiteProductionSafetyEvaluationRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.review import (
    SQLiteReviewSessionRepository,
    SQLiteVerifiedSignalPersistence,
)
from storage.price_history import DEFAULT_DATABASE_PATH
from services.currency import (
    CachedExchangeRateProvider,
    CurrencyConverter,
    ExchangeRateNotFoundError,
    ExchangeRateProviderError,
    FrankfurterExchangeRateProvider,
)
from engine.price_intelligence import analyze_product_prices
from engine.opportunity import calculate_verified_economics


PROJECT_NAME = "HYB Opportunity AI"
API_VERSION = "v1"
TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parent.parent
    / "templates"
)


class OpportunitySearchRequest(BaseModel):
    """Opportunity 검색 API의 최소 입력 계약."""

    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1)
    top: int = Field(default=5, ge=1)


class AuthoritativeDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    discovery_execution_id: str = Field(min_length=1)
    requested_at: datetime
    query: str = Field(min_length=1)
    selling_price_multiplier: Decimal
    shipping_cost: Decimal | None
    marketplace_fee_rate: Decimal
    payment_fee_rate: Decimal
    fixed_fee: Decimal | None
    marketplace_fee_known: bool
    payment_fee_known: bool
    fixed_fee_known: bool
    tax_rate: Decimal
    other_cost: Decimal
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    estimated_monthly_sales: int
    competitor_count: int
    risk_level: str = Field(min_length=1)
    limit: int
    match_threshold: Decimal
    target_currency: str | None = None
    policy_references: tuple[tuple[str, str], ...] = ()
    source_references: tuple[tuple[str, str], ...] = ()

    def to_command(self) -> DiscoveryCommand:
        return DiscoveryCommand(
            command_id=self.command_id,
            discovery_execution_id=self.discovery_execution_id,
            parameters=DiscoveryCommandParameters(
                query=self.query,
                selling_price_multiplier=self.selling_price_multiplier,
                shipping_cost=self.shipping_cost,
                marketplace_fee_rate=self.marketplace_fee_rate,
                payment_fee_rate=self.payment_fee_rate,
                fixed_fee=self.fixed_fee,
                marketplace_fee_known=self.marketplace_fee_known,
                payment_fee_known=self.payment_fee_known,
                fixed_fee_known=self.fixed_fee_known,
                tax_rate=self.tax_rate,
                other_cost=self.other_cost,
                minimum_net_profit=self.minimum_net_profit,
                minimum_roi=self.minimum_roi,
                estimated_monthly_sales=self.estimated_monthly_sales,
                competitor_count=self.competitor_count,
                risk_level=self.risk_level,
                limit=self.limit,
                match_threshold=self.match_threshold,
                target_currency=self.target_currency,
                policy_references=self.policy_references,
                source_references=self.source_references,
            ),
            requested_at=self.requested_at,
        )


def _founder_discovery_profile_payload() -> dict[str, object]:
    profile = FOUNDER_CONSERVATIVE_EBAY_US_V1
    return {
        "profile_name": profile.profile_name,
        "profile_version": profile.profile_version,
        "purpose": profile.purpose,
        "marketplace": profile.marketplace,
        "marketplace_source_reference": profile.marketplace_source_reference,
        "selling_price_multiplier": str(profile.selling_price_multiplier),
        "shipping_cost": str(profile.shipping_cost),
        "marketplace_fee_rate": str(profile.marketplace_fee_rate),
        "payment_fee_rate": str(profile.payment_fee_rate),
        "fixed_fee": str(profile.fixed_fee),
        "marketplace_fee_known": profile.marketplace_fee_known,
        "payment_fee_known": profile.payment_fee_known,
        "fixed_fee_known": profile.fixed_fee_known,
        "tax_rate": str(profile.tax_rate),
        "other_cost": str(profile.other_cost),
        "minimum_net_profit": str(profile.minimum_net_profit),
        "minimum_roi": str(profile.minimum_roi),
        "estimated_monthly_sales": profile.estimated_monthly_sales,
        "competitor_count": profile.competitor_count,
        "risk_level": profile.risk_level,
        "match_threshold": str(profile.match_threshold),
        "target_currency": profile.target_currency,
        "policy_references": profile.required_policy_references,
        "source_references": profile.required_source_references,
    }


def _validate_referenced_founder_profile(
    command: DiscoveryCommand,
) -> DiscoveryCommand:
    references = dict(command.parameters.policy_references)
    profile_name = references.get("founder_discovery_profile")
    profile_version = references.get("founder_discovery_profile_version")
    if profile_name is None and profile_version is None:
        return command
    if profile_name is None or profile_version is None:
        raise ValueError(
            "founder discovery profile name and version must be referenced together"
        )
    profile = resolve_founder_discovery_policy_profile(
        profile_name,
        profile_version,
    )
    return profile.validate_command(command)


class AuthoritativeFinalizedGroupResponse(BaseModel):
    finalized_group_id: str
    discovery_execution_id: str
    observation_ids: tuple[str, ...]
    representative_observation_id: str
    grouping_policy_version: str
    finalized_at: datetime


class RepresentativeObservationPreviewResponse(BaseModel):
    title: str
    image_url: str
    marketplace: str
    price: float
    currency: str
    url: str


class CandidateHandoffMarketIdentityResponse(BaseModel):
    scope: MarketObservationScope
    market: str
    marketplace: str
    canonical_product_id: str | None
    marketplace_item_id: str | None
    normalized_query: str | None
    category: str | None
    variant_identity: str | None
    condition: str | None
    window_started_at: datetime
    window_ended_at: datetime


class RepresentativeCandidateHandoffResponse(BaseModel):
    observation_id: str
    market_observation_identity: CandidateHandoffMarketIdentityResponse
    discovery_reference: str
    policy_name: str
    policy_version: str
    observed_at: datetime
    collector_source_reference: str


class FounderFinalizedGroupReadResponse(AuthoritativeFinalizedGroupResponse):
    representative_observation: RepresentativeObservationPreviewResponse
    candidate_handoff: RepresentativeCandidateHandoffResponse | None
    observation_count: int


class AuthoritativeDiscoveryResponse(BaseModel):
    command_id: str
    discovery_execution_id: str
    completed_at: datetime
    is_zero_result: bool
    completion_replayed: bool
    finalized_groups: tuple[AuthoritativeFinalizedGroupResponse, ...]


class DiscoveryExecutionResultReadResponse(BaseModel):
    command_id: str
    discovery_execution_id: str
    completed_at: datetime
    is_zero_result: bool
    finalized_group_ids: tuple[str, ...]


class DiscoveryFinalizedGroupsReadResponse(BaseModel):
    discovery_execution_id: str
    finalized_groups: tuple[FounderFinalizedGroupReadResponse, ...]


class OCRArtifactReferenceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    artifact_type: ArtifactType
    artifact_origin: ArtifactOrigin
    source_type: ExternalSignalSourceType
    sha256: str = Field(min_length=64, max_length=64)
    captured_at: datetime
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    schema_version: str = Field(min_length=1)

    def to_domain(self) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            artifact_origin=self.artifact_origin,
            source_type=self.source_type,
            sha256=self.sha256,
            captured_at=self.captured_at,
            width=self.width,
            height=self.height,
            mime_type=self.mime_type,
            file_size=self.file_size,
            schema_version=self.schema_version,
        )

    @classmethod
    def from_domain(cls, artifact: ArtifactReference) -> "OCRArtifactReferenceDTO":
        return cls(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            artifact_origin=artifact.artifact_origin,
            source_type=artifact.source_type,
            sha256=artifact.sha256,
            captured_at=artifact.captured_at,
            width=artifact.width,
            height=artifact.height,
            mime_type=artifact.mime_type,
            file_size=artifact.file_size,
            schema_version=artifact.schema_version,
        )


class OCRFieldResultDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: OCRField
    raw_text: str
    normalized_value: Any
    confidence: Decimal
    bounding_box: tuple[int, int, int, int] | None = None

    def to_domain(self) -> OCRFieldResult:
        return OCRFieldResult(
            field_name=self.field_name,
            raw_text=self.raw_text,
            normalized_value=self.normalized_value,
            confidence=self.confidence,
            bounding_box=self.bounding_box,
        )

    @classmethod
    def from_domain(cls, field: OCRFieldResult) -> "OCRFieldResultDTO":
        return cls(
            field_name=field.field_name,
            raw_text=field.raw_text,
            normalized_value=field.normalized_value,
            confidence=field.confidence,
            bounding_box=field.bounding_box,
        )


class ExternalOCRAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: OCRArtifactReferenceDTO
    provider: OCRProvider
    provider_version: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    executed_at: datetime
    result_confidence: Decimal
    fields: tuple[OCRFieldResultDTO, ...]
    execution_schema_version: str = Field(min_length=1)

    def to_command(self) -> AdmitExternalOCRExecution:
        artifact = self.artifact.to_domain()
        return AdmitExternalOCRExecution(
            artifact=artifact,
            result=OCRResult(
                request_id=self.request_id,
                artifact_id=artifact.artifact_id,
                provider=self.provider,
                provider_version=self.provider_version,
                executed_at=self.executed_at,
                fields=tuple(field.to_domain() for field in self.fields),
                confidence=self.result_confidence,
                schema_version=self.execution_schema_version,
            ),
        )


class OCRExecutionReplayKeyResponse(BaseModel):
    provider: OCRProvider
    request_id: str
    artifact_id: str


class OCRExecutionProvenanceResponse(BaseModel):
    provider: OCRProvider
    provider_version: str
    request_id: str
    artifact_id: str
    executed_at: datetime
    result_confidence: Decimal
    fields: tuple[OCRFieldResultDTO, ...]
    schema_version: str


class ExternalOCRAdmissionResponse(BaseModel):
    execution_replay_key: OCRExecutionReplayKeyResponse
    artifact_sha256: str
    ordered_candidate_ids: tuple[str, ...]
    artifact: OCRArtifactReferenceDTO
    execution: OCRExecutionProvenanceResponse
    candidate_schema_version: str
    committed_at: datetime
    receipt_schema_version: str
    replayed: bool


class ValidationQueueAdmissionRequest(BaseModel):
    discovery_reference: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)
    title: str = Field(min_length=1)
    admission_recommendation: str = Field(min_length=1)
    admission_score: float
    admission_roi: float
    currency: str = Field(min_length=1)
    admission_safety_status: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    captured_at: datetime
    opportunity_id: str | None = None
    note: str | None = None


class ValidationQueueActionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    occurred_at: datetime
    note: str | None = None


class DecisionCompositionFinalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_signal_ids: tuple[str, ...] | None = None
    generated_at: datetime | None = None
    requested_by: str | None = Field(default=None, min_length=1)


class ProductionSafetyEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    snapshot_chain_binding_id: str = Field(min_length=1)
    selected_product_snapshot_id: str = Field(min_length=1)
    requested_at: datetime


class EconomicEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: EvidenceStatus
    source: str = Field(min_length=1)
    observed_at: datetime | None = None
    reference: str | None = None


class MoneyInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: str | None
    currency: str = Field(min_length=3, max_length=3)
    evidence: EconomicEvidenceRequest


class RateInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate: str | None
    evidence: EconomicEvidenceRequest


class VerifiedEconomicsAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    snapshot_at: datetime
    purchase_cost: MoneyInputRequest
    shipping_cost: MoneyInputRequest
    marketplace_fee_rate: RateInputRequest
    payment_fee_rate: RateInputRequest
    fixed_fee: MoneyInputRequest
    tax_rate: RateInputRequest
    duty_cost: MoneyInputRequest
    other_cost: MoneyInputRequest
    expected_sale_price: MoneyInputRequest


class CompetitionEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any = None
    source: str | None = None
    reference: str | None = None
    observed_at: datetime | None = None
    status: MarketEvidenceStatus
    confidence: str
    collection_method: str = Field(min_length=1)
    keyword: str | None = None
    category: str | None = None
    marketplace_item_id: str | None = None
    canonical_product_id: str | None = None
    unit: str | None = None


class TargetMarketEvidenceRequest(CompetitionEvidenceRequest):
    market: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)


class NewToMarketAssessmentSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^new_to_market_domestic_selling_target$")
    domestic_selling_target_id: str = Field(min_length=1)


class CompetitionObservationAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    submitted_at: datetime
    observation_id: str = Field(min_length=1)
    identity: MarketObservationIdentityRequest
    observed_at: datetime
    evidence: dict[str, CompetitionEvidenceRequest]


class DemandObservationAdmissionRequest(CompetitionObservationAdmissionRequest):
    pass


class TargetCompetitionObservationAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = Field(pattern="^2\\.0\\.0$")
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    submitted_at: datetime
    observation_id: str = Field(min_length=1)
    subject: NewToMarketAssessmentSubjectRequest
    observed_at: datetime
    evidence: dict[str, TargetMarketEvidenceRequest]


class TargetDemandObservationAdmissionRequest(
    TargetCompetitionObservationAdmissionRequest
):
    pass


class StartReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    started_at: datetime


class CancelReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    cancelled_at: datetime


class MarketObservationIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: MarketObservationScope
    market: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)
    canonical_product_id: str | None = None
    marketplace_item_id: str | None = None
    normalized_query: str | None = None
    category: str | None = None
    variant_identity: str | None = None
    condition: str | None = None
    window_started_at: datetime
    window_ended_at: datetime


class DomesticMarketValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    competition_observation_id: str = Field(min_length=1)
    competition_assessment_id: str = Field(min_length=1)
    demand_observation_id: str = Field(min_length=1)
    demand_assessment_id: str = Field(min_length=1)
    accepted_external_signal_ids: tuple[str, ...] = ()
    operator_id: str = Field(min_length=1)
    reviewed_source_ids: tuple[str, ...]
    current_use_confirmed: bool
    verified_at: datetime
    requested_at: datetime
    policy_name: str = Field(default="domestic-market-validation", min_length=1)
    policy_version: str = Field(default="1.0.0", min_length=1)

    def to_application_request(
        self,
        opportunity_id: str,
    ) -> DomesticMarketValidationProductionRequest:
        return DomesticMarketValidationProductionRequest(
            command_id=self.command_id,
            opportunity_id=opportunity_id,
            competition_observation_id=self.competition_observation_id,
            competition_assessment_id=self.competition_assessment_id,
            demand_observation_id=self.demand_observation_id,
            demand_assessment_id=self.demand_assessment_id,
            accepted_external_signal_ids=self.accepted_external_signal_ids,
            verification=DomesticMarketVerification(
                operator_id=self.operator_id,
                verified_at=self.verified_at,
                current_use_confirmed=self.current_use_confirmed,
                reviewed_source_ids=self.reviewed_source_ids,
            ),
            requested_at=self.requested_at,
            policy_name=self.policy_name,
            policy_version=self.policy_version,
        )


class DomesticMarketMetricEvidenceResponse(BaseModel):
    metric: str
    value: int | str
    source: str | None
    reference: str | None
    observed_at: datetime | None
    collection_method: str
    status: str
    confidence: str
    unit: str | None


class DomesticMarketAnalysisSourceResponse(BaseModel):
    observation_id: str
    assessment_id: str
    observation_schema_version: str | None
    assessment_schema_version: str | None
    assessment_policy_version: str | None
    availability: str | None
    evidence: tuple[DomesticMarketMetricEvidenceResponse, ...]


class DomesticMarketSourceManifestResponse(BaseModel):
    opportunity_id: str
    discovery_reference: str
    market_identity: MarketObservationIdentityRequest
    competition: DomesticMarketAnalysisSourceResponse
    demand: DomesticMarketAnalysisSourceResponse
    accepted_external_signal_ids: tuple[str, ...]
    schema_version: str


class DomesticMarketVerificationResponse(BaseModel):
    operator_id: str
    verified_at: datetime
    current_use_confirmed: bool
    reviewed_source_ids: tuple[str, ...]
    schema_version: str


class DomesticMarketValidationResponse(BaseModel):
    command_id: str
    assessment_id: str
    source_manifest: DomesticMarketSourceManifestResponse
    verification: DomesticMarketVerificationResponse
    state: str
    blocking_reasons: tuple[str, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    assessment_schema_version: str
    receipt_schema_version: str
    replayed: bool


class DomesticSellingOpportunityAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    source_product_snapshot_id: str = Field(min_length=1)
    target_market_identity: MarketObservationIdentityRequest
    operator_id: str = Field(min_length=1)
    product_equivalence_confirmed: bool
    evidence_reference: str = Field(min_length=1)
    verified_at: datetime
    requested_at: datetime
    policy_name: str = Field(
        default="domestic-selling-opportunity-admission", min_length=1
    )
    policy_version: str = Field(default="1.0.0", min_length=1)


class BoundedKRSearchManifestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    searched_channels: tuple[str, ...] = Field(min_length=1)
    scope_kind: Literal["query", "category"]
    scope_value: str = Field(min_length=1)
    performed_at: datetime
    operator_id: str = Field(min_length=1)
    evidence_references: tuple[str, ...] = Field(min_length=1)
    conclusion: Literal["exact_kr_identity_not_established"]

    def to_domain(self) -> BoundedKRSearchManifest:
        return BoundedKRSearchManifest(
            searched_channels=self.searched_channels,
            scope_kind=BoundedKRSearchScopeKind(self.scope_kind),
            scope_value=self.scope_value,
            performed_at=self.performed_at,
            operator_id=self.operator_id,
            evidence_references=self.evidence_references,
            conclusion=BoundedKRSearchConclusion(self.conclusion),
        )


class NewToMarketDomesticSellingOpportunityAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    source_product_snapshot_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    decision_reason: str = Field(min_length=1)
    bounded_kr_search: BoundedKRSearchManifestRequest
    verified_at: datetime
    requested_at: datetime
    policy_name: str = Field(
        default="new-to-market-domestic-selling-admission", min_length=1
    )
    policy_version: str = Field(default="1.0.0", min_length=1)


class NewToMarketDomesticSellingOpportunityAdmissionResponse(BaseModel):
    command_id: str
    admission_id: str
    source_opportunity_identity: dict[str, str]
    source_lifecycle: dict[str, str | int]
    source_market_identity: dict[str, Any]
    source_candidate_promotion: dict[str, Any]
    source_product_snapshot: dict[str, str]
    domestic_selling_target: dict[str, str]
    domestic_opportunity_identity: dict[str, str]
    lifecycle: dict[str, str | int]
    target_binding: dict[str, Any]
    bounded_kr_search: dict[str, Any]
    operator_id: str
    decision_reason: str
    policy_name: str
    policy_version: str
    requested_at: datetime
    verified_at: datetime
    admitted_at: datetime
    committed_at: datetime
    admission_schema_version: str
    receipt_schema_version: str
    replayed: bool


class SourcingMoneyFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: CommercialFactAvailability
    amount: str | None = None
    currency: str | None = None

    def to_domain(self) -> SourcingMoneyFact:
        return SourcingMoneyFact(
            self.availability,
            None if self.amount is None else Decimal(self.amount),
            self.currency,
        )


class SourcingQuantityFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: CommercialFactAvailability
    quantity: int | None = None

    def to_domain(self) -> SourcingQuantityFact:
        return SourcingQuantityFact(self.availability, self.quantity)


class SourcingShippingTermRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: ShippingScope
    cost: SourcingMoneyFactRequest

    def to_domain(self) -> ShippingTerm:
        return ShippingTerm(self.scope, self.cost.to_domain())


class SourcingEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: SourcingEvidenceKind
    source_reference: str = Field(min_length=1)
    observed_at: datetime
    artifact_reference: OCRArtifactReferenceDTO | None = None

    def to_domain(self) -> SourcingEvidenceReference:
        return SourcingEvidenceReference(
            self.kind, self.source_reference, self.observed_at,
            None if self.artifact_reference is None else self.artifact_reference.to_domain(),
        )


class SourcingSellingProductLineageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opportunity_id: str = Field(min_length=1)
    discovery_reference: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_opportunity_binding_id: str = Field(min_length=1)
    product_observation_snapshot_id: str = Field(min_length=1)
    market_observation_identity: MarketObservationIdentityRequest

    def to_domain(self) -> SellingProductLineage:
        return SellingProductLineage(
            OpportunityIdentity(self.opportunity_id, self.discovery_reference),
            self.candidate_id, self.candidate_opportunity_binding_id,
            self.product_observation_snapshot_id,
            MarketObservationIdentity(**self.market_observation_identity.model_dump()),
        )

    def to_application(self) -> SellingProductLineage:
        return self.to_domain()


class SourcingDomesticSellingLineageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["domestic_selling_admission"]
    domestic_selling_admission_id: str = Field(min_length=1)

    def to_application(self) -> DomesticSellingProductLineageReference:
        return DomesticSellingProductLineageReference(
            self.domestic_selling_admission_id
        )


class FounderSourcingAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    requested_at: datetime
    verified_at: datetime
    operator_id: str = Field(min_length=1)
    selling_product_lineage: (
        SourcingSellingProductLineageRequest
        | SourcingDomesticSellingLineageRequest
    )
    supplier_platform: str = Field(min_length=1)
    external_supplier_reference: str | None = None
    supplier_display_name: str | None = None
    external_product_reference: str = Field(min_length=1)
    option_reference: str | None = None
    sku_reference: str | None = None
    source_url: str | None = None
    product_observed_at: datetime
    quoted_unit_price: SourcingMoneyFactRequest
    minimum_order_quantity: SourcingQuantityFactRequest
    quoted_quantity: SourcingQuantityFactRequest
    shipping_terms: tuple[SourcingShippingTermRequest, ...]
    lead_time_availability: CommercialFactAvailability
    lead_time_days: int | None = None
    quote_observed_at: datetime
    quote_valid_until: datetime | None = None
    quote_evidence: SourcingEvidenceRequest
    match_status: MatchVerificationStatus
    match_evidence: SourcingEvidenceRequest
    proposal_score: str | None = None
    proposal_version: str | None = None


class SourcingQuoteRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    requested_at: datetime
    operator_id: str = Field(min_length=1)
    quoted_unit_price: SourcingMoneyFactRequest
    minimum_order_quantity: SourcingQuantityFactRequest
    quoted_quantity: SourcingQuantityFactRequest
    shipping_terms: tuple[SourcingShippingTermRequest, ...]
    lead_time_availability: CommercialFactAvailability
    lead_time_days: int | None = None
    quote_observed_at: datetime
    quote_valid_until: datetime | None = None
    quote_evidence: SourcingEvidenceRequest


class SourcingEconomicsBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    admission_id: str = Field(min_length=1)
    admission_revision: int = Field(ge=1)
    quote_id: str = Field(min_length=1)
    quote_revision: int = Field(ge=1)
    requested_at: datetime

    def to_production(self, opportunity_id: str):
        return SourcingEconomicsBindingProductionRequest(
            command_id=self.command_id,
            opportunity_id=opportunity_id,
            source_reference=SourcingEconomicsSourceReference(
                self.admission_id,
                self.admission_revision,
                self.quote_id,
                self.quote_revision,
            ),
            requested_at=self.requested_at,
        )


class LandedCostCompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)
    requested_at: datetime


class ShippingAllocationAuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    composition_id: str = Field(min_length=1)
    component_kind: LandedCostComponentKind
    requested_at: datetime
    effective_allocation_basis: CostAllocationBasis | None = None
    per_order_denominator: int | None = None
    per_order_denominator_unit: str | None = None
    operator_id: str | None = None
    verified_at: datetime | None = None
    evidence_reference: SourcingEvidenceRequest | None = None


class FXObservationAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    base_currency: str = Field(min_length=1)
    quote_currency: str = Field(min_length=1)
    rate: str = Field(min_length=1)
    observed_at: datetime
    provider: str = Field(min_length=1)
    source_reference: str | None = None
    collection_method: str | None = None


class AcquisitionCostNormalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    composition_id: str = Field(min_length=1)
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    target_currency: str = Field(min_length=1)
    requested_at: datetime


class EconomicsSourceCompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    acquisition_normalization_id: str = Field(min_length=1)
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str = Field(min_length=1)
    requested_at: datetime


class SourcingEconomicsBindingResponse(BaseModel):
    command_id: str
    binding_id: str
    opportunity_id: str
    discovery_reference: str
    admission_id: str
    admission_revision: int
    quote_id: str
    quote_revision: int
    requested_at: datetime
    bound_at: datetime
    committed_at: datetime
    binding_schema_version: str
    receipt_schema_version: str
    replayed: bool


class LandedCostComponentResponse(BaseModel):
    kind: str
    availability: str
    amount: str | None
    currency: str | None
    allocation_basis: str


class SourcingQuantityResponse(BaseModel):
    availability: str
    quantity: int | None


class AuthorityEvidenceResponse(BaseModel):
    kind: str
    source_reference: str
    observed_at: datetime
    artifact_reference: dict[str, Any] | None


class LandedCostCompositionResponse(BaseModel):
    command_id: str
    composition_id: str
    opportunity_id: str
    discovery_reference: str
    binding_id: str
    components: tuple[LandedCostComponentResponse, ...]
    minimum_order_quantity: SourcingQuantityResponse
    quoted_quantity: SourcingQuantityResponse
    evidence_reference: AuthorityEvidenceResponse
    requested_at: datetime
    composed_at: datetime
    committed_at: datetime
    composition_schema_version: str
    receipt_schema_version: str
    replayed: bool


class ShippingAllocationDenominatorResponse(BaseModel):
    quantity: int
    source: str
    source_reference: str
    quantity_unit: str | None


class ShippingAllocationAuthorityResponse(BaseModel):
    command_id: str
    authority_id: str
    composition_id: str
    opportunity_id: str
    discovery_reference: str
    component_kind: str
    original_allocation_basis: str
    allocation_basis: str
    basis_authority_source: str
    status: str
    denominator: ShippingAllocationDenominatorResponse | None
    unresolved_code: str | None
    evidence_reference: AuthorityEvidenceResponse
    operator_id: str | None
    verified_at: datetime | None
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    authority_schema_version: str
    receipt_schema_version: str
    replayed: bool


class FXObservationResponse(BaseModel):
    command_id: str
    observation_id: str
    base_currency: str
    quote_currency: str
    rate: str
    observed_at: datetime
    admitted_at: datetime
    provider: str
    source_reference: str | None
    collection_method: str | None
    committed_at: datetime
    observation_schema_version: str
    receipt_schema_version: str
    replayed: bool


class NormalizedAcquisitionComponentResponse(BaseModel):
    kind: str
    original_availability: str
    original_amount: str | None
    original_currency: str | None
    original_allocation_basis: str
    effective_allocation_basis: str
    allocation_authority_id: str | None
    denominator_quantity: int | None
    denominator_source: str | None
    fx_observation_id: str | None
    fx_direction: str
    target_currency: str
    normalized_per_unit_amount: str


class AcquisitionCostNormalizationResponse(BaseModel):
    command_id: str
    normalization_id: str
    opportunity_id: str
    discovery_reference: str
    composition_id: str
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    target_currency: str
    components: tuple[NormalizedAcquisitionComponentResponse, ...]
    total_per_unit_acquisition_cost: str
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    normalized_at: datetime
    committed_at: datetime
    normalization_schema_version: str
    receipt_schema_version: str
    replayed: bool


class EconomicsSourceBlockingReasonResponse(BaseModel):
    code: str
    category: str
    source_reference: str | None


class EconomicsSourceCompositionResponse(BaseModel):
    command_id: str
    composition_id: str
    opportunity_id: str
    discovery_reference: str
    acquisition_normalization_id: str
    acquisition_policy_name: str
    acquisition_policy_version: str
    acquisition_cost_per_unit: str
    economics_currency: str
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    expected_sale_price: dict[str, Any]
    marketplace_fee_rate: dict[str, Any]
    payment_fee_rate: dict[str, Any]
    fixed_fee: dict[str, Any]
    tax_rate: dict[str, Any]
    duty_cost: dict[str, Any]
    other_cost: dict[str, Any]
    state: str
    blocking_reasons: tuple[EconomicsSourceBlockingReasonResponse, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    composed_at: datetime
    committed_at: datetime
    composition_schema_version: str
    receipt_schema_version: str
    replayed: bool


class CandidateIssuanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuance_command_id: str = Field(min_length=1)
    discovery_command_id: str = Field(min_length=1)
    discovery_execution_id: str = Field(min_length=1)
    finalized_group_id: str = Field(min_length=1)
    discovery_reference: str = Field(min_length=1)
    market_observation_identity: MarketObservationIdentityRequest
    requested_at: datetime

    def to_command(self) -> IssueOpportunityCandidateCommand:
        identity = self.market_observation_identity
        return IssueOpportunityCandidateCommand(
            issuance_command_id=self.issuance_command_id,
            discovery_command_id=self.discovery_command_id,
            discovery_execution_id=self.discovery_execution_id,
            finalized_group_id=self.finalized_group_id,
            discovery_reference=self.discovery_reference,
            market_observation_identity=MarketObservationIdentity(
                scope=identity.scope,
                market=identity.market,
                marketplace=identity.marketplace,
                canonical_product_id=identity.canonical_product_id,
                marketplace_item_id=identity.marketplace_item_id,
                normalized_query=identity.normalized_query,
                category=identity.category,
                variant_identity=identity.variant_identity,
                condition=identity.condition,
                window_started_at=identity.window_started_at,
                window_ended_at=identity.window_ended_at,
            ),
            requested_at=self.requested_at,
        )


class CandidateIssuanceResponse(BaseModel):
    candidate_id: str
    discovery_reference: str
    issuance_command_id: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    market_observation_identity: MarketObservationIdentityRequest
    requested_at: datetime
    issued_at: datetime
    receipt_committed_at: datetime
    replayed: bool


class CandidatePromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promotion_command_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    admission_recommendation: str = Field(min_length=1)
    admission_score: float
    admission_roi: float
    currency: str = Field(min_length=1)
    admission_safety_status: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_at: datetime
    opportunity_id: str | None = Field(default=None, min_length=1)
    note: str | None = None

    def to_command(self) -> PromoteOpportunityCandidateCommand:
        return PromoteOpportunityCandidateCommand(
            promotion_command_id=self.promotion_command_id,
            candidate_id=self.candidate_id,
            title=self.title,
            admission_recommendation=self.admission_recommendation,
            admission_score=self.admission_score,
            admission_roi=self.admission_roi,
            currency=self.currency,
            admission_safety_status=self.admission_safety_status,
            operator_id=self.operator_id,
            reason=self.reason,
            requested_at=self.requested_at,
            opportunity_id=self.opportunity_id,
            note=self.note,
        )


class CandidatePromotionResponse(BaseModel):
    promotion_command_id: str
    candidate_id: str
    opportunity_id: str
    binding_id: str
    discovery_reference: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    market_observation_identity: MarketObservationIdentityRequest
    marketplace: str
    title: str
    admission_recommendation: str
    admission_score: float
    admission_roi: float
    currency: str
    admission_safety_status: str
    lifecycle_status: OpportunityLifecycleStatus
    lifecycle_version: int
    requested_at: datetime
    promoted_at: datetime
    committed_at: datetime
    replayed: bool


class ProductSnapshotCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    finalized_group_id: str = Field(min_length=1)
    product_snapshot_ids: tuple[str, ...] = Field(min_length=1)
    requested_at: datetime

    def to_application_request(self) -> CandidateProductSnapshotCaptureRequest:
        return CandidateProductSnapshotCaptureRequest(
            command_id=self.command_id,
            candidate_id=self.candidate_id,
            finalized_group_id=self.finalized_group_id,
            product_snapshot_ids=self.product_snapshot_ids,
            requested_at=self.requested_at,
        )


class ProductSnapshotSourceBindingResponse(BaseModel):
    product_snapshot_id: str
    collected_observation_id: str
    candidate_id: str
    capture_command_id: str
    bound_at: datetime


class ProductSnapshotCaptureResponse(BaseModel):
    command_id: str
    candidate_id: str
    finalized_group_id: str
    market_observation_identity: MarketObservationIdentityRequest
    product_snapshot_ids: tuple[str, ...]
    source_bindings: tuple[ProductSnapshotSourceBindingResponse, ...]
    committed_at: datetime
    replayed: bool


class PriceAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    finalized_group_id: str = Field(min_length=1)
    product_snapshot_capture_command_id: str = Field(min_length=1)
    fallback_multiplier: Decimal
    analyzer_version: str = Field(min_length=1)
    requested_at: datetime

    def to_application_request(self) -> CandidatePriceAnalysisRequest:
        return CandidatePriceAnalysisRequest(
            command_id=self.command_id,
            candidate_id=self.candidate_id,
            finalized_group_id=self.finalized_group_id,
            product_snapshot_capture_command_id=(
                self.product_snapshot_capture_command_id
            ),
            fallback_multiplier=self.fallback_multiplier,
            analyzer_version=self.analyzer_version,
            requested_at=self.requested_at,
        )


class PriceAnalysisResponse(BaseModel):
    command_id: str
    candidate_id: str
    finalized_group_id: str
    price_snapshot_id: str
    product_snapshot_ids: tuple[str, ...]
    market_observation_identity: MarketObservationIdentityRequest
    analyzer_version: str
    fallback_multiplier: Decimal
    requested_at: datetime
    generated_at: datetime
    committed_at: datetime
    currency: str
    lowest_price: Decimal
    average_price: Decimal
    median_price: Decimal
    highest_price: Decimal
    price_range: Decimal
    price_variation_rate: Decimal
    price_stability_level: str
    recommended_selling_price: Decimal
    sample_size: int
    replayed: bool


class EconomicsCalculationParametersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: str = Field(min_length=1)
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    estimated_monthly_sales: int = Field(ge=0)
    competitor_count: int = Field(ge=0)
    risk_level: str = Field(min_length=1)
    context_items: tuple[tuple[str, Any], ...] = ()

    def to_domain(self) -> EconomicsCalculationParameters:
        return EconomicsCalculationParameters(
            marketplace=self.marketplace,
            minimum_net_profit=self.minimum_net_profit,
            minimum_roi=self.minimum_roi,
            estimated_monthly_sales=self.estimated_monthly_sales,
            competitor_count=self.competitor_count,
            risk_level=self.risk_level,
            context_items=self.context_items,
        )


class EconomicsSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    price_analysis_command_id: str = Field(min_length=1)
    calculation_parameters: EconomicsCalculationParametersRequest
    calculation_version: str = Field(min_length=1)
    requested_at: datetime

    def to_application_request(self) -> EconomicsSnapshotProductionRequest:
        return EconomicsSnapshotProductionRequest(
            command_id=self.command_id,
            opportunity_id=self.opportunity_id,
            price_analysis_command_id=self.price_analysis_command_id,
            calculation_parameters=self.calculation_parameters.to_domain(),
            calculation_version=self.calculation_version,
            requested_at=self.requested_at,
        )


class EconomicsSnapshotResponse(BaseModel):
    command_id: str
    opportunity_id: str
    discovery_reference: str
    candidate_id: str
    candidate_opportunity_binding_id: str
    price_analysis_command_id: str
    price_intelligence_snapshot_id: str
    verified_economics_opportunity_id: str
    economics_snapshot_id: str
    market_observation_identity: MarketObservationIdentityRequest
    calculation_parameters: EconomicsCalculationParametersRequest
    calculation_version: str
    requested_at: datetime
    generated_at: datetime
    committed_at: datetime
    currency: str
    revenue: Decimal | None
    marketplace_fee: Decimal | None
    payment_fee: Decimal | None
    tax_cost: Decimal | None
    landed_cost: Decimal | None
    selling_cost: Decimal | None
    total_cost: Decimal | None
    net_profit: Decimal | None
    break_even: Decimal | None
    roi: Decimal
    landed_cost_roi: Decimal
    margin_rate: Decimal
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    passes_net_profit_filter: bool
    passes_roi_filter: bool
    passes_profitability_filter: bool
    replayed: bool


class CandidatePromotionV2Request(BaseModel):
    """Founder selection of exact persisted Candidate/Product provenance."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2.0.0"] = "2.0.0"
    promotion_command_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    finalized_group_id: str = Field(min_length=1)
    representative_product_snapshot_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_at: datetime
    note: str | None = None

    def to_command(self) -> PromoteOpportunityCandidateV2Command:
        return PromoteOpportunityCandidateV2Command(**self.model_dump())


class CandidatePromotionV2Response(BaseModel):
    """O1 lineage only; this response is not BUY/economics/safety authority."""

    contract_version: Literal["2.0.0"]
    promotion_command_id: str
    candidate_id: str
    opportunity_id: str
    binding_id: str
    admission_id: str
    discovery_reference: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    product_snapshot_capture_command_id: str
    product_snapshot_ids: tuple[str, ...]
    representative_product_snapshot_id: str
    market_observation_identity: MarketObservationIdentityRequest
    marketplace: str
    title: str
    currency: str
    admission_kind: Literal["founder_selected_for_deeper_validation"]
    operator_id: str
    reason: str
    lifecycle_status: OpportunityLifecycleStatus
    lifecycle_version: int
    requested_at: datetime
    promoted_at: datetime
    committed_at: datetime
    replayed: bool


class ConservativeEconomicsScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_name: str = Field(min_length=1)
    scenario_version: str = Field(min_length=1)
    sale_price_factor: Decimal
    assumption_owner: str = Field(min_length=1)

    def to_domain(self) -> ConservativeEconomicsScenario:
        return ConservativeEconomicsScenario(
            scenario_name=self.scenario_name,
            scenario_version=self.scenario_version,
            sale_price_factor=self.sale_price_factor,
            assumption_owner=self.assumption_owner,
        )


class ConservativeEconomicsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    source_composition_id: str = Field(min_length=1)
    scenario: ConservativeEconomicsScenarioRequest
    requested_at: datetime

    def to_application_request(
        self, opportunity_id: str
    ) -> ConservativeEconomicsProductionRequest:
        return ConservativeEconomicsProductionRequest(
            command_id=self.command_id,
            opportunity_id=opportunity_id,
            source_composition_id=self.source_composition_id,
            scenario=self.scenario.to_domain(),
            requested_at=self.requested_at,
        )


class ConservativeEconomicsAssumptionResponse(BaseModel):
    kind: str
    value: Decimal
    owner: str


class ConservativeEconomicsBlockingReasonResponse(BaseModel):
    code: str
    category: str
    source_reference: str | None


class ConservativeEconomicsResponse(BaseModel):
    command_id: str
    result_id: str
    opportunity_id: str
    discovery_reference: str
    source_composition_id: str
    source_composition_schema_version: str
    status: str
    economics_currency: str
    authoritative_expected_sale_price: Decimal | None
    expected_sale_price_evidence_status: str
    expected_sale_price_evidence_reference: str | None
    conservative_sale_price: Decimal | None
    acquisition_cost_per_unit: Decimal
    marketplace_fee: Decimal | None
    payment_fee: Decimal | None
    fixed_fee: Decimal | None
    accepted_tax_cost: Decimal | None
    accepted_duty_cost: Decimal | None
    accepted_other_cost: Decimal | None
    total_unit_cost: Decimal | None
    conservative_profit_per_unit: Decimal | None
    conservative_margin: Decimal | None
    conservative_acquisition_roi: Decimal | None
    assumptions: tuple[ConservativeEconomicsAssumptionResponse, ...]
    scenario_name: str
    scenario_version: str
    blocking_reasons: tuple[ConservativeEconomicsBlockingReasonResponse, ...]
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    result_schema_version: str
    receipt_schema_version: str
    replayed: bool


class CriticalCostAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    composition_id: str = Field(min_length=1)
    acquisition_normalization_id: str = Field(min_length=1)
    verified_economics_opportunity_id: str = Field(min_length=1)
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str = Field(min_length=1)
    requested_at: datetime


class CriticalCostReasonResponse(BaseModel):
    code: str
    severity: str
    category: str
    source_reference: str | None


class CriticalCostAssessmentResponse(BaseModel):
    command_id: str
    assessment_id: str
    opportunity_id: str
    discovery_reference: str
    state: str
    blocking_reasons: tuple[CriticalCostReasonResponse, ...]
    warning_reasons: tuple[CriticalCostReasonResponse, ...]
    composition_id: str
    acquisition_normalization_id: str
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    assessment_schema_version: str
    receipt_schema_version: str
    replayed: bool


class CapitalReadinessAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    conservative_economics_result_id: str = Field(min_length=1)
    domestic_market_validation_assessment_id: str = Field(min_length=1)
    critical_cost_assessment_id: str = Field(min_length=1)
    requested_at: datetime


class CapitalReadinessSourceManifestResponse(BaseModel):
    opportunity_id: str
    discovery_reference: str
    conservative_economics_result_id: str
    economics_source_composition_id: str
    acquisition_normalization_id: str
    landed_cost_composition_id: str
    domestic_market_validation_assessment_id: str
    critical_cost_assessment_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    product_match_verification_id: str
    quote_valid_until: datetime | None
    schema_version: str


class CapitalReadinessAssessmentResponse(BaseModel):
    command_id: str
    assessment_id: str
    opportunity_id: str
    discovery_reference: str
    state: str
    blocking_reasons: tuple[str, ...]
    source_manifest: CapitalReadinessSourceManifestResponse
    critical_cost_normalization_id: str | None
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    assessment_schema_version: str
    receipt_schema_version: str
    replayed: bool


class IntendedOrderQuantityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    sourcing_admission_id: str = Field(min_length=1)
    sourcing_admission_revision: int = Field(ge=1)
    quote_id: str = Field(min_length=1)
    quote_revision: int = Field(ge=1)
    quantity: int = Field(ge=1)
    quantity_unit: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    declared_at: datetime
    requested_at: datetime


class IntendedOrderQuantityResponse(BaseModel):
    command_id: str
    intent_id: str
    opportunity_id: str
    discovery_reference: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    quantity: int
    quantity_unit: str
    operator_id: str
    declared_at: datetime
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    intent_schema_version: str
    receipt_schema_version: str
    replayed: bool


class DeployableCapitalSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    amount: StrictStr = Field(min_length=1)
    currency: str = Field(min_length=1)
    as_of: datetime
    operator_id: str = Field(min_length=1)
    requested_at: datetime


class DeployableCapitalSnapshotResponse(BaseModel):
    command_id: str
    snapshot_id: str
    amount: str
    currency: str
    as_of: datetime
    operator_id: str
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    semantics_version: str
    snapshot_schema_version: str
    receipt_schema_version: str
    replayed: bool


class PlannedCapitalRequirementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    intended_order_quantity_id: str = Field(min_length=1)
    acquisition_normalization_id: str = Field(min_length=1)
    scope_status: UpfrontCostScopeStatus
    operator_id: str = Field(min_length=1)
    verified_at: datetime
    requested_at: datetime


class PlannedCapitalRequirementResponse(BaseModel):
    command_id: str
    requirement_id: str
    opportunity_id: str
    discovery_reference: str
    state: str
    blocking_reasons: tuple[str, ...]
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    quantity: int
    quantity_unit: str
    normalized_acquisition_cost_per_unit: str
    planned_acquisition_capital: str | None
    currency: str
    scope_status: str
    scope_operator_id: str
    scope_verified_at: datetime
    scope_semantics_version: str
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    requirement_schema_version: str
    receipt_schema_version: str
    replayed: bool


class CapitalGateSourceManifestResponse(BaseModel):
    opportunity_id: str
    discovery_reference: str
    capital_readiness_assessment_id: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    conservative_economics_result_id: str
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    schema_version: str


class CapitalGateEvaluatedFactsResponse(BaseModel):
    capital_readiness_state: str
    capital_requirement_state: str
    conservative_economics_status: str
    requirement_currency: str
    deployable_currency: str
    planned_acquisition_capital: str | None
    deployable_capital: str
    conservative_profit_per_unit: str | None
    conservative_margin: str | None
    conservative_acquisition_roi: str | None
    intended_order_quantity: int
    intended_order_quantity_unit: str
    minimum_order_quantity_availability: str
    minimum_order_quantity: int | None
    deployable_capital_semantics_version: str
    schema_version: str


class CapitalGateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    capital_readiness_assessment_id: str = Field(min_length=1)
    capital_requirement_id: str = Field(min_length=1)
    deployable_capital_snapshot_id: str = Field(min_length=1)
    requested_at: datetime


class CapitalGateAssessmentResponse(BaseModel):
    command_id: str
    gate_id: str
    state: str
    blocking_reasons: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    source_manifest: CapitalGateSourceManifestResponse
    evaluated_facts: CapitalGateEvaluatedFactsResponse
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    assessment_schema_version: str
    receipt_schema_version: str
    replayed: bool


class FounderCapitalApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    capital_gate_id: str = Field(min_length=1)
    founder_id: str = Field(min_length=1)
    approved_capital: StrictStr = Field(min_length=1)
    currency: str = Field(min_length=1)
    requested_at: datetime
    approved_at: datetime


class FounderCapitalApprovalResponse(BaseModel):
    command_id: str
    approval_id: str
    opportunity_id: str
    discovery_reference: str
    capital_gate_id: str
    capital_gate_policy_name: str
    capital_gate_policy_version: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    intended_order_quantity_id: str
    capital_gate_evaluated_at: datetime
    approved_capital: str
    currency: str
    founder_id: str
    requested_at: datetime
    approved_at: datetime
    admitted_at: datetime
    committed_at: datetime
    approval_schema_version: str
    receipt_schema_version: str
    replayed: bool


class RealMoneyExecutionIntentRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "contract_version": "2.0.0",
                "command_id": "run-001-execution-intent",
                "founder_capital_approval_id": "approval-id",
                "quote_id": "quote-id",
                "quote_revision": 1,
                "current_deployable_capital_snapshot_id": "snapshot-b-id",
                "execution_quantity": 5,
                "execution_quantity_unit": "unit",
                "proposed_supplier_order_committed_amount": "500",
                "supplier_order_currency": "CNY",
                "supplier_order_checkout_evidence_reference": "05_purchase/checkout-before-click.png",
                "founder_id": "founder-1",
                "current_execution_confirmed": True,
                "confirmed_at": "2026-08-10T10:00:00+09:00",
                "requested_at": "2026-08-10T10:00:00+09:00",
            }
        },
    )

    command_id: str = Field(min_length=1)
    founder_capital_approval_id: str = Field(min_length=1)
    quote_id: str = Field(min_length=1)
    quote_revision: int = Field(ge=1)
    current_deployable_capital_snapshot_id: str = Field(min_length=1)
    execution_quantity: int = Field(ge=1)
    execution_quantity_unit: str = Field(min_length=1)
    contract_version: Literal["1.0.0", "2.0.0"]
    planned_execution_amount: StrictStr | None = Field(default=None, min_length=1)
    currency: str | None = Field(default=None, min_length=1)
    proposed_supplier_order_committed_amount: StrictStr | None = Field(
        default=None, min_length=1,
        description="V2 Founder-confirmed proposed gross supplier-order commitment; distinct from authorized acquisition capital.",
    )
    supplier_order_currency: str | None = Field(
        default=None, min_length=1,
        description="V2 supplier-order currency; must exactly equal the Supplier Quote currency.",
    )
    supplier_order_checkout_evidence_reference: str | None = Field(
        default=None, min_length=1,
        description="V2 opaque evidence reference for the proposed external checkout action.",
    )
    founder_id: str = Field(min_length=1)
    current_execution_confirmed: bool
    confirmed_at: datetime
    requested_at: datetime


class RealMoneyExecutionIntentResponse(BaseModel):
    contract_version: str
    command_id: str
    intent_id: str
    opportunity_id: str
    discovery_reference: str
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    current_deployable_capital_snapshot_id: str
    execution_quantity: int
    execution_quantity_unit: str
    planned_execution_amount: str | None
    currency: str | None
    authorized_acquisition_capital_amount: str | None
    authorized_acquisition_capital_currency: str | None
    proposed_supplier_order_committed_amount: str | None
    supplier_order_currency: str | None
    supplier_order_checkout_evidence_reference: str | None
    founder_id: str
    current_execution_confirmed: bool
    confirmed_at: datetime
    state: str
    blocking_reasons: tuple[str, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    source_manifest_schema_version: str
    intent_schema_version: str
    receipt_schema_version: str
    replayed: bool


class PurchaseExecutionEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)
    observed_at: datetime


class PurchaseExecutionEvidenceResponse(BaseModel):
    reference: str
    observed_at: datetime
    schema_version: str


class PurchaseExecutionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "contract_version": "2.0.0",
                "command_id": "run-001-purchase-execution",
                "real_money_execution_intent_id": "ready-intent-id",
                "quote_id": "quote-id",
                "quote_revision": 1,
                "actual_quantity": 5,
                "actual_quantity_unit": "unit",
                "supplier_order_committed_amount": "500",
                "supplier_order_currency": "CNY",
                "external_order_reference": "external-supplier-order-reference",
                "founder_id": "founder-1",
                "executed_at": "2026-08-10T10:05:00+09:00",
                "evidence_references": [{
                    "reference": "05_purchase/order-confirmation.png",
                    "observed_at": "2026-08-10T10:05:00+09:00",
                }],
                "requested_at": "2026-08-10T10:06:00+09:00",
            }
        },
    )

    command_id: str = Field(min_length=1)
    real_money_execution_intent_id: str = Field(min_length=1)
    quote_id: str = Field(min_length=1)
    quote_revision: int = Field(ge=1)
    actual_quantity: int = Field(ge=1)
    actual_quantity_unit: str = Field(min_length=1)
    contract_version: Literal["1.0.0", "2.0.0"]
    actual_total_committed_amount: StrictStr | None = Field(default=None, min_length=1)
    currency: str | None = Field(default=None, min_length=1)
    supplier_order_committed_amount: StrictStr | None = Field(
        default=None, min_length=1,
        description="V2 factual external supplier-order commitment; must exactly match the READY proposal.",
    )
    supplier_order_currency: str | None = Field(
        default=None, min_length=1,
        description="V2 factual supplier-order currency; no FX conversion is performed here.",
    )
    external_order_reference: str = Field(min_length=1)
    founder_id: str = Field(min_length=1)
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceRequest, ...] = Field(
        min_length=1
    )
    requested_at: datetime


class PurchaseExecutionResponse(BaseModel):
    contract_version: str
    command_id: str
    record_id: str
    opportunity_id: str
    discovery_reference: str
    real_money_execution_intent_id: str
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quote_id: str
    quote_revision: int
    current_deployable_capital_snapshot_id: str
    actual_quantity: int
    actual_quantity_unit: str
    actual_total_committed_amount: str | None
    currency: str | None
    authorized_acquisition_capital_amount: str | None
    authorized_acquisition_capital_currency: str | None
    proposed_supplier_order_committed_amount: str | None
    proposed_supplier_order_currency: str | None
    supplier_order_committed_amount: str | None
    supplier_order_currency: str | None
    external_order_reference: str
    founder_id: str
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceResponse, ...]
    execution_intent_evaluated_at: datetime
    execution_safety_policy_name: str
    execution_safety_policy_version: str
    policy_name: str
    policy_version: str
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    source_manifest_schema_version: str
    record_schema_version: str
    receipt_schema_version: str
    replayed: bool


class ActualAcquisitionEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)
    observed_at: datetime
    operator_id: str = Field(min_length=1)
    collection_method: str = Field(min_length=1)


class ActualAcquisitionFXRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_currency: str = Field(
        min_length=1, description="Currency of the factual settled acquisition amount."
    )
    target_currency: str = Field(
        min_length=1, description="Settlement target currency; must match the request target currency."
    )
    original_amount: StrictStr = Field(
        min_length=1, description="Exact factual source-currency amount as a Decimal string."
    )
    target_amount: StrictStr | None = Field(
        default=None, description="Exact evidenced target amount, when the actual FX evidence supplies it."
    )
    applied_rate: StrictStr | None = Field(
        default=None, description="Exact actual payment/settlement rate, never a planned FX fallback."
    )
    provider: str | None = None
    payment_channel: str | None = None
    external_reference: str = Field(min_length=1)
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceRequest


class ActualAcquisitionFixedCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "unit_purchase",
        "supplier_side_shipping",
        "international_freight",
        "domestic_inbound",
        "duty_customs",
    ] = Field(
        description="Canonical fixed acquisition category; submit all five once in this exact order."
    )
    availability: ActualAcquisitionFactAvailability = Field(
        description=(
            "KNOWN requires factual money/time/evidence; NOT_APPLICABLE requires evidence and no money; "
            "UNKNOWN is unresolved and is never zero."
        )
    )
    amount: StrictStr | None = None
    currency: str | None = None
    settled_at: datetime | None = None
    evidence: ActualAcquisitionEvidenceRequest | None = None
    unresolved_reason: str | None = None
    actual_fx: ActualAcquisitionFXRequest | None = None


class OtherMandatoryAcquisitionCostItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = Field(min_length=1)
    amount: StrictStr = Field(min_length=1)
    currency: str = Field(min_length=1)
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceRequest
    actual_fx: ActualAcquisitionFXRequest | None = None


class OtherMandatoryAcquisitionCostsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: ActualAcquisitionFactAvailability = Field(
        description=(
            "Scope completeness for all other mandatory acquisition costs: KNOWN has scoped items, "
            "NOT_APPLICABLE is evidenced empty scope, UNKNOWN blocks COMPLETE."
        )
    )
    items: tuple[OtherMandatoryAcquisitionCostItemRequest, ...]
    scope_evidence: ActualAcquisitionEvidenceRequest | None = None
    unresolved_reason: str | None = None


class ActualAcquisitionSettlementRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "command_id": "run-001-actual-acquisition-r1",
                "purchase_execution_record_id": "purchase-record-id",
                "predecessor_settlement_id": None,
                "target_currency": "KRW",
                "fixed_cost_facts": [
                    {
                        "category": category,
                        "availability": "known",
                        "amount": "0",
                        "currency": "KRW",
                        "settled_at": "2026-08-10T12:00:00+09:00",
                        "evidence": {
                            "reference": f"06_acquisition/{category}.json",
                            "observed_at": "2026-08-10T12:00:00+09:00",
                            "operator_id": "founder-1",
                            "collection_method": "manual_document_review",
                        },
                    }
                    for category in (
                        "unit_purchase", "supplier_side_shipping",
                        "international_freight", "domestic_inbound", "duty_customs",
                    )
                ],
                "other_mandatory_costs": {
                    "availability": "not_applicable",
                    "items": [],
                    "scope_evidence": {
                        "reference": "06_acquisition/other_scope_na.txt",
                        "observed_at": "2026-08-10T12:00:00+09:00",
                        "operator_id": "founder-1",
                        "collection_method": "manual_document_review",
                    },
                },
                "operator_id": "founder-1",
                "requested_at": "2026-08-10T12:05:00+09:00",
            }
        },
    )

    command_id: str = Field(min_length=1)
    purchase_execution_record_id: str = Field(min_length=1)
    predecessor_settlement_id: str | None = None
    target_currency: str = Field(min_length=1)
    fixed_cost_facts: tuple[ActualAcquisitionFixedCostRequest, ...] = Field(
        min_length=5, max_length=5
    )
    other_mandatory_costs: OtherMandatoryAcquisitionCostsRequest
    operator_id: str = Field(min_length=1)
    requested_at: datetime


class ActualAcquisitionEvidenceResponse(BaseModel):
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str


class ActualAcquisitionFXResponse(BaseModel):
    source_currency: str
    target_currency: str
    original_amount: str
    target_amount: str | None
    applied_rate: str | None
    normalized_target_amount: str
    provider: str | None
    payment_channel: str | None
    external_reference: str
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceResponse
    schema_version: str


class ActualAcquisitionFixedCostResponse(BaseModel):
    category: ActualAcquisitionCostCategory
    availability: ActualAcquisitionFactAvailability
    amount: str | None
    currency: str | None
    settled_at: datetime | None
    evidence: ActualAcquisitionEvidenceResponse | None
    unresolved_reason: str | None
    actual_fx: ActualAcquisitionFXResponse | None


class OtherMandatoryAcquisitionCostItemResponse(BaseModel):
    scope: str
    amount: str
    currency: str
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceResponse
    actual_fx: ActualAcquisitionFXResponse | None


class OtherMandatoryAcquisitionCostsResponse(BaseModel):
    availability: ActualAcquisitionFactAvailability
    items: tuple[OtherMandatoryAcquisitionCostItemResponse, ...]
    scope_evidence: ActualAcquisitionEvidenceResponse | None
    unresolved_reason: str | None


class NormalizedActualAcquisitionCategoryResponse(BaseModel):
    category: ActualAcquisitionCostCategory
    target_currency: str
    target_batch_amount: str | None


class ActualAcquisitionSettlementResponse(BaseModel):
    command_id: str
    settlement_id: str
    revision: int
    predecessor_settlement_id: str | None
    opportunity_id: str
    discovery_reference: str
    purchase_execution_record_id: str
    real_money_execution_intent_id: str
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quote_id: str
    quote_revision: int
    executed_quantity: int
    executed_quantity_unit: str
    external_order_reference: str
    purchase_executed_at: datetime
    target_currency: str
    state: str
    blocking_reasons: tuple[str, ...]
    fixed_cost_facts: tuple[ActualAcquisitionFixedCostResponse, ...]
    other_mandatory_costs: OtherMandatoryAcquisitionCostsResponse
    normalized_categories: tuple[NormalizedActualAcquisitionCategoryResponse, ...]
    acquisition_batch_total: str | None
    acquisition_per_unit: str | None
    operator_id: str
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    source_manifest_schema_version: str
    settlement_schema_version: str
    receipt_schema_version: str
    replayed: bool


class GoodsReceiptEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)
    observed_at: datetime
    operator_id: str = Field(min_length=1)
    collection_method: str = Field(min_length=1)


class GoodsReceiptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    purchase_execution_record_id: str = Field(min_length=1)
    received_quantity: StrictInt = Field(ge=1)
    quantity_unit: str = Field(min_length=1)
    sellable_quantity: StrictInt = Field(ge=0)
    damaged_quantity: StrictInt = Field(ge=0)
    evidence_references: tuple[GoodsReceiptEvidenceRequest, ...] = Field(min_length=1)
    delivery_reference: str | None = None
    operator_id: str = Field(min_length=1)
    received_at: datetime
    inspected_at: datetime
    requested_at: datetime


class GoodsReceiptEvidenceResponse(BaseModel):
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str


class GoodsReceiptResponse(BaseModel):
    command_id: str
    record_id: str
    opportunity_id: str
    discovery_reference: str
    purchase_execution_record_id: str
    real_money_execution_intent_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quote_id: str
    quote_revision: int
    executed_quantity: int
    executed_quantity_unit: str
    external_order_reference: str
    founder_id: str
    purchase_executed_at: datetime
    received_quantity: int
    quantity_unit: str
    sellable_quantity: int
    damaged_quantity: int
    evidence_references: tuple[GoodsReceiptEvidenceResponse, ...]
    delivery_reference: str | None
    operator_id: str
    received_at: datetime
    inspected_at: datetime
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    policy_name: str
    policy_version: str
    source_manifest_schema_version: str
    record_schema_version: str
    receipt_schema_version: str
    replayed: bool


class OwnedInventoryProductKeyResponse(BaseModel):
    opportunity_id: str
    discovery_reference: str
    source_platform: str
    supplier_id: str
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quantity_unit: str


class OwnedInventoryPositionResponse(BaseModel):
    product_key: OwnedInventoryProductKeyResponse
    opportunity_id: str
    discovery_reference: str
    quantity_unit: str
    total_received: int
    total_sellable_received: int
    total_damaged_received: int
    total_outbound_quantity: int
    sellable_on_hand: int
    contributing_purchase_execution_ids: tuple[str, ...]
    contributing_goods_receipt_ids: tuple[str, ...]
    contributing_actual_sale_settlement_ids: tuple[str, ...]
    source_event_count: int
    inbound_source_event_count: int
    outbound_source_event_count: int
    policy_name: str
    policy_version: str
    schema_version: str


class OwnedInventoryResponse(BaseModel):
    opportunity_id: str
    positions: tuple[OwnedInventoryPositionResponse, ...]
    position_count: int


class ActualSaleEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1)
    observed_at: datetime
    operator_id: str = Field(min_length=1)
    collection_method: str = Field(min_length=1)


class ActualSaleMonetaryFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ActualSaleMonetaryCategory = Field(
        description="One canonical sale monetary category; submit all 15 once in canonical order."
    )
    availability: ActualSaleFactAvailability = Field(
        description=(
            "KNOWN requires factual money/time/evidence; NOT_APPLICABLE requires evidence and no money; "
            "UNKNOWN is unresolved and is never zero."
        )
    )
    amount: StrictStr | None = None
    currency: str | None = None
    occurred_at: datetime | None = None
    evidence: ActualSaleEvidenceRequest | None = None
    unresolved_reason: str | None = None


class OtherActualSaleCostItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1)
    amount: StrictStr = Field(min_length=1)
    currency: str = Field(min_length=1)
    occurred_at: datetime
    evidence: ActualSaleEvidenceRequest


class OtherActualSaleCostsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: ActualSaleFactAvailability = Field(
        description="Completeness of the ordered other sale-side cost scope; UNKNOWN blocks COMPLETE."
    )
    items: tuple[OtherActualSaleCostItemRequest, ...]
    scope_evidence: ActualSaleEvidenceRequest | None = None
    unresolved_reason: str | None = None


class ActualSalePayoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: ActualSaleFactAvailability = Field(
        description="Payout factual availability; it does not replace component facts."
    )
    amount: StrictStr | None = None
    currency: str | None = None
    external_reference: str | None = None
    paid_at: datetime | None = None
    evidence: ActualSaleEvidenceRequest | None = None
    unresolved_reason: str | None = None
    reconciliation_state: ActualSalePayoutReconciliationState = Field(
        description=(
            "Payout is an independent reconciliation fact: RECONCILED equals the canonical component net; "
            "NOT_SCOPE_COMPARABLE preserves a payout with different timing/scope; UNRESOLVED blocks COMPLETE."
        )
    )
    reconciliation_explanation: str | None = None
    reconciliation_evidence: ActualSaleEvidenceRequest | None = None


class ActualSaleFinalityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(
        description="True only when refund/return scope for the exact window is factually final."
    )
    observed_at: datetime | None = Field(
        default=None, description="Factual finality observation time; it cannot precede period_end."
    )
    evidence: ActualSaleEvidenceRequest | None = Field(
        default=None, description="Evidence for confirmed return/refund finality."
    )
    unresolved_reason: str | None = Field(
        default=None, description="Honest reason finality is unresolved; unresolved finality blocks COMPLETE."
    )


class ActualSaleSettlementRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "command_id": "run-001-sale-r1",
                "anchor_goods_receipt_id": "goods-receipt-id",
                "predecessor_settlement_id": None,
                "marketplace": "COUPANG",
                "seller_account_reference": "seller-account-reference",
                "marketplace_product_reference": "product-reference",
                "marketplace_option_reference": "option-reference",
                "marketplace_sku_reference": "sku-reference",
                "external_report_reference": "08_coupang_sale/report.csv#cycle-001",
                "transaction_references": ["transaction-reference-1"],
                "period_start": "2026-08-01T00:00:00+09:00",
                "period_end": "2026-08-08T00:00:00+09:00",
                "fulfilled_outbound_quantity": 1,
                "cancelled_quantity": 0,
                "refunded_quantity": 0,
                "returned_quantity": 0,
                "quantity_unit": "unit",
                "settlement_currency": "KRW",
                "fixed_monetary_facts": [
                    {
                        "category": category,
                        "availability": "unknown",
                        "unresolved_reason": "TO CONFIRM IN REAL COUPANG SELLER ACCOUNT",
                    }
                    for category in (
                        "gross_completed_merchandise", "buyer_shipping",
                        "marketplace_funded_discount_support", "seller_funded_discount",
                        "tax_collected", "marketplace_fee", "payment_fee", "fixed_fee",
                        "refund", "cancellation_reversal", "return_related_fee",
                        "advertising", "fulfillment", "storage", "sale_side_inbound_handling",
                    )
                ],
                "other_sale_side_costs": {
                    "availability": "unknown", "items": [],
                    "unresolved_reason": "scope not final",
                },
                "payout": {
                    "availability": "unknown",
                    "unresolved_reason": "payout pending",
                    "reconciliation_state": "unresolved",
                    "reconciliation_explanation": "cycle is not final",
                },
                "finality": {
                    "confirmed": False,
                    "unresolved_reason": "return/refund window is not final",
                },
                "operator_id": "founder-1",
                "requested_at": "2026-08-09T00:00:00+09:00",
            }
        },
    )
    command_id: str = Field(min_length=1)
    anchor_goods_receipt_id: str = Field(min_length=1)
    predecessor_settlement_id: str | None = None
    marketplace: str = Field(min_length=1)
    seller_account_reference: str = Field(min_length=1)
    marketplace_product_reference: str = Field(min_length=1)
    marketplace_option_reference: str | None = None
    marketplace_sku_reference: str | None = None
    external_report_reference: str = Field(min_length=1)
    transaction_references: tuple[str, ...] = ()
    period_start: datetime
    period_end: datetime
    fulfilled_outbound_quantity: StrictInt = Field(ge=0)
    cancelled_quantity: StrictInt = Field(ge=0)
    refunded_quantity: StrictInt = Field(ge=0)
    returned_quantity: StrictInt = Field(ge=0)
    quantity_unit: str = Field(min_length=1)
    settlement_currency: str = Field(min_length=1)
    fixed_monetary_facts: tuple[ActualSaleMonetaryFactRequest, ...] = Field(
        min_length=15, max_length=15
    )
    other_sale_side_costs: OtherActualSaleCostsRequest
    payout: ActualSalePayoutRequest
    finality: ActualSaleFinalityRequest
    operator_id: str = Field(min_length=1)
    requested_at: datetime


class ActualSaleEvidenceResponse(BaseModel):
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str


class ActualSaleMonetaryFactResponse(BaseModel):
    category: ActualSaleMonetaryCategory
    availability: ActualSaleFactAvailability
    amount: str | None
    currency: str | None
    occurred_at: datetime | None
    evidence: ActualSaleEvidenceResponse | None
    unresolved_reason: str | None
    schema_version: str


class OtherActualSaleCostItemResponse(BaseModel):
    scope: str
    amount: str
    currency: str
    occurred_at: datetime
    evidence: ActualSaleEvidenceResponse


class OtherActualSaleCostsResponse(BaseModel):
    availability: ActualSaleFactAvailability
    items: tuple[OtherActualSaleCostItemResponse, ...]
    scope_evidence: ActualSaleEvidenceResponse | None
    unresolved_reason: str | None
    schema_version: str


class ActualSalePayoutResponse(BaseModel):
    availability: ActualSaleFactAvailability
    amount: str | None
    currency: str | None
    external_reference: str | None
    paid_at: datetime | None
    evidence: ActualSaleEvidenceResponse | None
    unresolved_reason: str | None
    reconciliation_state: ActualSalePayoutReconciliationState
    reconciliation_explanation: str | None
    reconciliation_evidence: ActualSaleEvidenceResponse | None
    schema_version: str


class ActualSaleFinalityResponse(BaseModel):
    confirmed: bool
    observed_at: datetime | None
    evidence: ActualSaleEvidenceResponse | None
    unresolved_reason: str | None
    schema_version: str


class ActualSaleSettlementResponse(BaseModel):
    command_id: str
    settlement_id: str
    revision: int
    predecessor_settlement_id: str | None
    product_key: OwnedInventoryProductKeyResponse
    anchor_goods_receipt_id: str
    eligible_goods_receipt_ids: tuple[str, ...]
    contributing_purchase_execution_ids: tuple[str, ...]
    marketplace: str
    seller_account_reference: str
    marketplace_product_reference: str
    marketplace_option_reference: str | None
    marketplace_sku_reference: str | None
    external_report_reference: str
    transaction_references: tuple[str, ...]
    period_start: datetime
    period_end: datetime
    fulfilled_outbound_quantity: int
    cancelled_quantity: int
    refunded_quantity: int
    returned_quantity: int
    quantity_unit: str
    settlement_currency: str
    fixed_monetary_facts: tuple[ActualSaleMonetaryFactResponse, ...]
    other_sale_side_costs: OtherActualSaleCostsResponse
    payout: ActualSalePayoutResponse
    finality: ActualSaleFinalityResponse
    state: str
    blocking_reasons: tuple[str, ...]
    operator_id: str
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    source_manifest_schema_version: str
    settlement_schema_version: str
    receipt_schema_version: str
    requested_at: datetime
    admitted_at: datetime
    committed_at: datetime
    replayed: bool


class ActualOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    actual_acquisition_settlement_id: str = Field(min_length=1)
    actual_sale_settlement_ids: tuple[str, ...] = Field(min_length=1)
    requested_at: datetime


class ActualOutcomeSaleWindowResponse(BaseModel):
    settlement_id: str
    period_start: datetime
    period_end: datetime


class ActualOutcomeAcquisitionAllocationResponse(BaseModel):
    category: str
    batch_amount: str
    per_executed_unit: str
    sold_cogs: str
    remaining_sellable_basis: str
    damaged_loss: str
    unreceived_exposure: str


class ActualOutcomeSaleComponentResponse(BaseModel):
    category: str
    amount: str


class ActualOutcomeMetricResponse(BaseModel):
    available: bool
    value: str | None


class ActualOutcomeResponse(BaseModel):
    command_id: str
    outcome_id: str
    product_key: OwnedInventoryProductKeyResponse
    purchase_execution_record_id: str
    actual_acquisition_settlement_id: str
    goods_receipt_ids: tuple[str, ...]
    actual_sale_settlement_ids: tuple[str, ...]
    sale_windows: tuple[ActualOutcomeSaleWindowResponse, ...]
    state: str
    inventory_resolution: str
    blocking_reasons: tuple[str, ...]
    executed_quantity: int
    received_quantity: int
    sellable_received_quantity: int
    damaged_quantity: int
    sold_quantity: int
    remaining_sellable_quantity: int
    returned_quantity: int
    unreceived_quantity: int
    quantity_unit: str
    currency: str
    acquisition_allocations: tuple[ActualOutcomeAcquisitionAllocationResponse, ...]
    sale_components: tuple[ActualOutcomeSaleComponentResponse, ...]
    other_sale_side_costs: str | None
    acquisition_batch_total: str | None
    actual_cogs: str | None
    remaining_sellable_inventory_cost_basis: str | None
    damaged_acquisition_loss: str | None
    unreceived_acquisition_cost_basis: str | None
    gross_realized_merchandise_revenue: str | None
    recognized_sale_credits: str | None
    recognized_sale_side_costs: str | None
    net_realized_sale_contribution: str | None
    actual_realized_profit: str | None
    actual_margin: ActualOutcomeMetricResponse
    actual_acquisition_roi: ActualOutcomeMetricResponse
    known_payout_total: str | None
    payout_reconciliation_states: tuple[str, ...]
    evaluation_start: datetime
    evaluation_through: datetime
    acquisition_policy_version: str
    acquisition_schema_version: str
    goods_receipt_policy_versions: tuple[str, ...]
    goods_receipt_schema_versions: tuple[str, ...]
    sale_policy_versions: tuple[str, ...]
    sale_schema_versions: tuple[str, ...]
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    source_manifest_schema_version: str
    outcome_schema_version: str
    receipt_schema_version: str
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    replayed: bool
    aliased: bool


class ConservativeActualVarianceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1)
    conservative_economics_result_id: str = Field(min_length=1)
    actual_outcome_id: str = Field(min_length=1)
    requested_at: datetime


class ConservativeActualVarianceMetricResponse(BaseModel):
    metric_name: str
    direction: str
    comparability: str
    predicted_value: str | None
    actual_value: str | None
    variance: str | None
    relative_variance_percent: str | None
    variance_percentage_points: str | None
    favorability: str
    unit: str
    currency: str | None
    reason_codes: tuple[str, ...]
    predicted_scope_total: str | None
    actual_scope_total: str | None
    scope_total_variance: str | None


class ConservativeActualVarianceContributorResponse(BaseModel):
    category: str
    amount: str
    currency: str
    classification: str
    source_references: tuple[str, ...]


class ConservativeActualPredictedContextResponse(BaseModel):
    category: str
    predicted_value: str
    currency: str
    classification: str
    source_reference: str


class ConservativeActualExposureContextResponse(BaseModel):
    remaining_sellable_quantity: int
    remaining_inventory_cost_basis: str
    unreceived_quantity: int
    unreceived_acquisition_basis: str
    damaged_quantity: int
    damaged_acquisition_loss: str
    returned_quantity: int
    inventory_resolution: str
    quantity_unit: str
    currency: str


class ConservativeActualScenarioContextResponse(BaseModel):
    scenario_name: str
    scenario_version: str
    sale_price_factor: str
    assumption_owner: str
    conservative_policy_name: str
    conservative_policy_version: str


class ConservativeActualScopeContextResponse(BaseModel):
    sold_quantity: int
    executed_quantity: int
    inventory_resolution: str
    sale_windows: tuple[ActualOutcomeSaleWindowResponse, ...]
    remaining_sellable_quantity: int
    damaged_quantity: int
    returned_quantity: int
    unreceived_quantity: int
    quantity_unit: str


class ConservativeActualVarianceResponse(BaseModel):
    command_id: str
    variance_id: str
    product_key: OwnedInventoryProductKeyResponse
    conservative_economics_result_id: str
    actual_outcome_id: str
    comparison_state: str
    calibration_eligibility: str
    calibration_reasons: tuple[str, ...]
    core_metrics: tuple[ConservativeActualVarianceMetricResponse, ...]
    acquisition_component_metrics: tuple[ConservativeActualVarianceMetricResponse, ...]
    actual_only_contributors: tuple[ConservativeActualVarianceContributorResponse, ...]
    predicted_only_context: tuple[ConservativeActualPredictedContextResponse, ...]
    exposure_context: ConservativeActualExposureContextResponse
    scenario_context: ConservativeActualScenarioContextResponse
    actual_scope_context: ConservativeActualScopeContextResponse
    source_composition_id: str
    acquisition_normalization_id: str
    landed_cost_composition_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    purchase_execution_record_id: str
    actual_acquisition_settlement_id: str
    actual_sale_settlement_ids: tuple[str, ...]
    currency: str
    conservative_policy_name: str
    conservative_policy_version: str
    conservative_schema_version: str
    actual_policy_name: str
    actual_policy_version: str
    actual_schema_version: str
    source_manifest_schema_version: str
    conservative_calculated_at: datetime
    purchase_executed_at: datetime
    hindsight_eligible: bool
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    variance_schema_version: str
    receipt_schema_version: str
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    replayed: bool
    aliased: bool


class SnapshotChainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    opportunity_id: str = Field(min_length=1)
    product_snapshot_capture_command_id: str = Field(min_length=1)
    price_analysis_command_id: str = Field(min_length=1)
    economics_calculation_command_id: str = Field(min_length=1)
    requested_at: datetime

    def to_application_request(self) -> CompleteSnapshotChainProductionRequest:
        return CompleteSnapshotChainProductionRequest(
            command_id=self.command_id,
            opportunity_id=self.opportunity_id,
            product_snapshot_capture_command_id=(
                self.product_snapshot_capture_command_id
            ),
            price_analysis_command_id=self.price_analysis_command_id,
            economics_calculation_command_id=(
                self.economics_calculation_command_id
            ),
            requested_at=self.requested_at,
        )


class SnapshotChainResponse(BaseModel):
    command_id: str
    binding_id: str
    candidate_opportunity_binding_id: str
    candidate_id: str
    opportunity_id: str
    chain_version: int
    product_snapshot_ids: tuple[str, ...]
    price_snapshot_id: str
    economics_snapshot_id: str
    verified_economics_opportunity_id: str
    market_observation_identity: MarketObservationIdentityRequest
    requested_at: datetime
    bound_at: datetime
    committed_at: datetime
    replayed: bool
    aliased: bool


class ReviewCommandContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    market_observation_identity: MarketObservationIdentityRequest
    signal_name: str = Field(min_length=1)
    signal_direction: ExternalSignalDirection
    artifact_identity: str = Field(min_length=1)
    created_at: datetime


class CreateTrustedReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    created_at: datetime
    command_id: str = Field(min_length=1)
    contexts: tuple[ReviewCommandContextRequest, ...] = Field(min_length=1)
    opportunity_id: str | None = Field(default=None, min_length=1)


class ApproveCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    command_id: str = Field(min_length=1)
    verification_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    verified_at: datetime
    signal_id: str = Field(min_length=1)
    comment: str | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)


class CorrectCandidateRequest(ApproveCandidateRequest):
    corrected_value: Any


class SkipCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    skipped_at: datetime


class CompleteReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    command_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    completed_at: datetime


app = FastAPI(title=PROJECT_NAME)
templates = Jinja2Templates(
    directory=str(TEMPLATE_DIRECTORY)
)


def get_validation_queue_repository():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    try:
        yield repository
    finally:
        repository.close()


def get_sourcing_authority_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteSourcingAuthorityRepository(DEFAULT_DATABASE_PATH)
        )
        admission_clock = lambda: datetime.now(timezone.utc)
        committed_clock = lambda: datetime.now(timezone.utc)
        yield SourcingAuthorityProductionEntry(
            AdmitFounderSourcing(
                repository,
                supplier_id_generator=ProductionSupplierIdentityGenerator(),
                sourcing_product_id_generator=ProductionSourcingProductIdentityGenerator(),
                quote_id_generator=ProductionSupplierQuoteIdentityGenerator(),
                match_verification_id_generator=ProductionProductMatchVerificationIdentityGenerator(),
                admission_id_generator=ProductionFounderSourcingAdmissionIdentityGenerator(),
                admission_clock=admission_clock,
                committed_clock=committed_clock,
            ),
            ReviseFounderSourcingQuote(
                repository,
                admission_clock=admission_clock,
                committed_clock=committed_clock,
            ),
        )
    except (sqlite3.Error, SourcingAuthorityPersistenceError) as error:
        raise HTTPException(
            status_code=503, detail="sourcing authority persistence unavailable"
        ) from error
    finally:
        resources.close()


def get_domestic_selling_opportunity_entry():
    resources = ExitStack()
    try:
        repository = SQLiteDomesticSellingOpportunityAdmissionRepository(
            DEFAULT_DATABASE_PATH
        )
        resources.callback(repository.close)
        yield AdmitDomesticSellingOpportunity(
            repository,
            opportunity_id_generator=(
                ProductionDomesticSellingOpportunityIdentityGenerator()
            ),
            admission_id_generator=(
                ProductionDomesticSellingOpportunityAdmissionIdentityGenerator()
            ),
            admitted_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
    except (sqlite3.Error, DomesticSellingOpportunityPersistenceError) as error:
        raise HTTPException(
            status_code=503,
            detail="domestic selling Opportunity persistence unavailable",
        ) from error
    finally:
        resources.close()


def get_new_to_market_domestic_selling_entry():
    resources = ExitStack()
    try:
        repository = SQLiteNewToMarketDomesticSellingAdmissionRepository(
            DEFAULT_DATABASE_PATH
        )
        resources.callback(repository.close)
        yield AdmitNewToMarketDomesticSellingOpportunity(
            repository,
            opportunity_id_generator=(
                ProductionNewToMarketDomesticOpportunityIdentityGenerator()
            ),
            target_id_generator=(
                ProductionNewToMarketDomesticSellingTargetIdentityGenerator()
            ),
            admission_id_generator=(
                ProductionNewToMarketDomesticSellingAdmissionIdentityGenerator()
            ),
            admitted_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
    except (
        sqlite3.Error,
        NewToMarketDomesticSellingPersistenceError,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="new-to-market domestic selling persistence unavailable",
        ) from error
    finally:
        resources.close()


def get_authoritative_discovery_entry():
    resources = ExitStack()
    try:
        command_repository = resources.enter_context(
            SQLiteDiscoveryCommandRepository(DEFAULT_DATABASE_PATH)
        )
        observation_repository = resources.enter_context(
            SQLiteDiscoveryObservationRepository(DEFAULT_DATABASE_PATH)
        )
        group_repository = resources.enter_context(
            SQLiteDiscoveryGroupRepository(DEFAULT_DATABASE_PATH)
        )
        result_repository = resources.enter_context(
            SQLiteDiscoveryResultRepository(DEFAULT_DATABASE_PATH)
        )
        session = requests.Session()
        resources.callback(session.close)
        currency_converter = CurrencyConverter(
            CachedExchangeRateProvider(
                FrankfurterExchangeRateProvider(session=session)
            )
        )
        entry = PersistedDiscoveryExecutionEntry(
            persist_command=PersistDiscoveryCommand(
                command_repository,
                clock=lambda: datetime.now(timezone.utc),
            ),
            runtime=OrchestratorProductionDiscoveryRuntime(
                currency_converter=currency_converter
            ),
            observation_identity_provider=(
                ProductionObservationIdentityProvider()
            ),
            candidate_discovery_reference_provider=(
                ProductionCandidateDiscoveryReferenceProvider()
            ),
            observation_repository=observation_repository,
            finalized_group_identity_provider=(
                ProductionFinalizedGroupIdentityProvider()
            ),
            group_finalization_clock=lambda: datetime.now(timezone.utc),
            group_repository=group_repository,
            discovery_completion_clock=lambda: datetime.now(timezone.utc),
            result_repository=result_repository,
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="discovery persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_authoritative_discovery_reader():
    resources = ExitStack()
    try:
        group_repository = resources.enter_context(
            SQLiteDiscoveryGroupRepository(DEFAULT_DATABASE_PATH)
        )
        result_repository = resources.enter_context(
            SQLiteDiscoveryResultRepository(DEFAULT_DATABASE_PATH)
        )
        observation_repository = resources.enter_context(
            SQLiteDiscoveryObservationRepository(DEFAULT_DATABASE_PATH)
        )
        reader = PersistedDiscoveryResultReader(
            result_repository=result_repository,
            group_repository=group_repository,
            observation_repository=observation_repository,
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="discovery persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield reader
    finally:
        resources.close()


def get_external_ocr_admission_entry():
    resources = ExitStack()
    try:
        repository = SQLiteExternalSignalLedgerRepository(DEFAULT_DATABASE_PATH)
        resources.callback(repository.close)
        entry = ExternalOCRCandidateAdmission(
            persistence=repository,
            candidate_identity_supplier=ProductionOCRCandidateIdentityGenerator(),
            artifact_admission_clock=lambda: datetime.now(timezone.utc),
            receipt_clock=lambda: datetime.now(timezone.utc),
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="OCR admission persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_candidate_issuance_entry():
    resources = ExitStack()
    try:
        command_repository = resources.enter_context(
            SQLiteDiscoveryCommandRepository(DEFAULT_DATABASE_PATH)
        )
        result_repository = resources.enter_context(
            SQLiteDiscoveryResultRepository(DEFAULT_DATABASE_PATH)
        )
        group_repository = resources.enter_context(
            SQLiteDiscoveryGroupRepository(DEFAULT_DATABASE_PATH)
        )
        observation_repository = resources.enter_context(
            SQLiteDiscoveryObservationRepository(DEFAULT_DATABASE_PATH)
        )
        candidate_repository = resources.enter_context(
            SQLiteCandidateIssuanceRepository(DEFAULT_DATABASE_PATH)
        )
        entry = CandidateIssuanceProductionEntry(
            command_repository=command_repository,
            result_repository=result_repository,
            group_repository=group_repository,
            observation_repository=observation_repository,
            candidate_repository=candidate_repository,
            candidate_id_generator=ProductionCandidateIdentityGenerator(),
            issuance_clock=lambda: datetime.now(timezone.utc),
            receipt_clock=lambda: datetime.now(timezone.utc),
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="candidate persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_candidate_promotion_entry():
    resources = ExitStack()
    try:
        candidate_repository = resources.enter_context(
            SQLiteCandidateIssuanceRepository(DEFAULT_DATABASE_PATH)
        )
        promotion_repository = SQLiteCandidatePromotionRepository(
            DEFAULT_DATABASE_PATH
        )
        resources.callback(promotion_repository.close)
        capture_repository = resources.enter_context(
            SQLiteProductSnapshotCaptureRepository(DEFAULT_DATABASE_PATH)
        )
        entry = CandidatePromotionProductionEntry(
            candidate_repository=candidate_repository,
            promotion_repository=promotion_repository,
            opportunity_id_generator=ProductionOpportunityIdentityGenerator(),
            binding_id_generator=(
                ProductionCandidateOpportunityBindingIdentityGenerator()
            ),
            product_snapshot_capture_repository=capture_repository,
            admission_id_generator=(
                ProductionCandidatePromotionAdmissionIdentityGenerator()
            ),
            clock=lambda: datetime.now(timezone.utc),
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="candidate promotion persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_product_snapshot_capture_entry():
    resources = ExitStack()
    try:
        candidate_repository = resources.enter_context(
            SQLiteCandidateIssuanceRepository(DEFAULT_DATABASE_PATH)
        )
        group_repository = resources.enter_context(
            SQLiteDiscoveryGroupRepository(DEFAULT_DATABASE_PATH)
        )
        capture_repository = resources.enter_context(
            SQLiteProductSnapshotCaptureRepository(DEFAULT_DATABASE_PATH)
        )
        entry = CandidateProductSnapshotCaptureProductionEntry(
            candidate_repository=candidate_repository,
            group_repository=group_repository,
            capture_repository=capture_repository,
            receipt_clock=lambda: datetime.now(timezone.utc),
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="product snapshot persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_candidate_price_analysis_entry():
    resources = ExitStack()
    try:
        candidate_repository = resources.enter_context(
            SQLiteCandidateIssuanceRepository(DEFAULT_DATABASE_PATH)
        )
        capture_repository = resources.enter_context(
            SQLiteProductSnapshotCaptureRepository(DEFAULT_DATABASE_PATH)
        )
        analysis_repository = resources.enter_context(
            SQLitePriceAnalysisRepository(DEFAULT_DATABASE_PATH)
        )
        entry = CandidatePriceAnalysisProductionEntry(
            candidate_repository=candidate_repository,
            capture_repository=capture_repository,
            analysis_repository=analysis_repository,
            snapshot_id_generator=ProductionPriceSnapshotIdentityGenerator(),
            generated_clock=lambda: datetime.now(timezone.utc),
            receipt_clock=lambda: datetime.now(timezone.utc),
            analyzer=analyze_product_prices,
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="price analysis persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_economics_snapshot_entry():
    resources = ExitStack()
    try:
        promotion_repository = SQLiteCandidatePromotionRepository(
            DEFAULT_DATABASE_PATH
        )
        resources.callback(promotion_repository.close)
        price_analysis_repository = resources.enter_context(
            SQLitePriceAnalysisRepository(DEFAULT_DATABASE_PATH)
        )
        economics_repository = resources.enter_context(
            SQLiteEconomicsCalculationOwnerRepository(DEFAULT_DATABASE_PATH)
        )
        entry = EconomicsSnapshotProductionEntry(
            promotion_repository=promotion_repository,
            price_analysis_repository=price_analysis_repository,
            economics_repository=economics_repository,
            snapshot_id_generator=ProductionEconomicsSnapshotIdentityGenerator(),
            generated_clock=lambda: datetime.now(timezone.utc),
            receipt_clock=lambda: datetime.now(timezone.utc),
            calculator=calculate_verified_economics,
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="economics persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_conservative_economics_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteConservativeEconomicsRepository(DEFAULT_DATABASE_PATH)
        )
        entry = ConservativeEconomicsProductionEntry(
            repository=repository,
            result_id_generator=ProductionConservativeEconomicsIdentityGenerator(),
            calculated_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
    except (sqlite3.Error, ConservativeEconomicsPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="conservative economics persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_critical_cost_assessment_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteCriticalCostCompletenessRepository(DEFAULT_DATABASE_PATH)
        )
        owner = PersistCriticalCostCompleteness(
            repository,
            assessment_id_generator=(
                ProductionCriticalCostCompletenessIdentityGenerator()
            ),
            evaluated_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
            policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2,
        )
        entry = CriticalCostCompletenessProductionEntry(repository, owner)
    except (sqlite3.Error, CriticalCostCompletenessPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="critical cost persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_capital_readiness_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteCapitalReadinessRepository(DEFAULT_DATABASE_PATH)
        )
        owner = EvaluateCapitalReadiness(
            repository,
            assessment_id_generator=ProductionCapitalReadinessIdentityGenerator(),
            evaluated_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = CapitalReadinessProductionEntry(repository, owner)
    except (sqlite3.Error, CapitalReadinessPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="capital readiness persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_intended_order_quantity_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteCapitalInvestmentFactsRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = IntendedOrderQuantityProductionEntry(
            repository,
            AdmitIntendedOrderQuantity(
                repository,
                intent_id_generator=ProductionIntendedOrderQuantityIdentityGenerator(),
                admitted_clock=clock,
                committed_clock=clock,
            ),
        )
    except (sqlite3.Error, CapitalInvestmentPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503, detail="Capital investment persistence unavailable"
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_deployable_capital_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteCapitalInvestmentFactsRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = AdmitDeployableCapitalSnapshot(
            repository,
            snapshot_id_generator=ProductionDeployableCapitalSnapshotIdentityGenerator(),
            admitted_clock=clock,
            committed_clock=clock,
        )
    except (sqlite3.Error, CapitalInvestmentPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503, detail="Capital investment persistence unavailable"
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_planned_capital_requirement_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLitePlannedAcquisitionCapitalRequirementRepository(
                DEFAULT_DATABASE_PATH
            )
        )
        clock = ProductionUTCClock()
        entry = PlannedCapitalRequirementProductionEntry(
            repository,
            CalculatePlannedAcquisitionCapitalRequirement(
                repository,
                requirement_id_generator=(
                    ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator()
                ),
                calculated_clock=clock,
                committed_clock=clock,
            ),
        )
    except (
        sqlite3.Error,
        PlannedAcquisitionCapitalRequirementPersistenceError,
    ) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="planned acquisition capital persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_capital_gate_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteCapitalGateRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = CapitalGateProductionEntry(
            repository,
            EvaluateCapitalGate(
                repository,
                gate_id_generator=ProductionCapitalGateIdentityGenerator(),
                evaluated_clock=clock,
                committed_clock=clock,
            ),
        )
    except (sqlite3.Error, CapitalGatePersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503, detail="Capital Gate persistence unavailable"
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_founder_capital_approval_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteFounderCapitalApprovalRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = FounderCapitalApprovalProductionEntry(
            repository,
            ApproveFounderCapital(
                repository,
                approval_id_generator=ProductionFounderCapitalApprovalIdentityGenerator(),
                admitted_clock=clock,
                committed_clock=clock,
            ),
        )
    except (sqlite3.Error, FounderCapitalApprovalPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503, detail="Founder Capital Approval persistence unavailable"
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_real_money_execution_intent_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteRealMoneyExecutionIntentRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = RealMoneyExecutionIntentProductionEntry(
            repository,
            EvaluateRealMoneyExecutionIntent(
                repository,
                execution_intent_id_generator=(
                    ProductionRealMoneyExecutionIntentIdentityGenerator()
                ),
                evaluated_clock=clock,
                committed_clock=clock,
            ),
        )
    except (sqlite3.Error, RealMoneyExecutionIntentPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Real-Money Execution Intent persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_purchase_execution_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLitePurchaseExecutionRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = PurchaseExecutionProductionEntry(
            repository,
            RecordPurchaseExecution(
                repository,
                record_id_generator=(
                    ProductionPurchaseExecutionRecordIdentityGenerator()
                ),
                admitted_clock=clock,
                committed_clock=clock,
            ),
        )
    except (sqlite3.Error, PurchaseExecutionPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Purchase Execution persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_actual_acquisition_settlement_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteActualAcquisitionSettlementRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = ActualAcquisitionSettlementProductionEntry(
            AdmitActualAcquisitionSettlement(
                repository,
                settlement_id_generator=(
                    ProductionActualAcquisitionSettlementIdentityGenerator()
                ),
                admitted_clock=clock,
                committed_clock=clock,
            )
        )
    except (sqlite3.Error, ActualAcquisitionSettlementPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Actual Acquisition Settlement persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_goods_receipt_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteGoodsReceiptRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = GoodsReceiptProductionEntry(
            AdmitGoodsReceipt(
                repository,
                record_id_generator=ProductionGoodsReceiptRecordIdentityGenerator(),
                admitted_clock=clock,
                committed_clock=clock,
            )
        )
    except (sqlite3.Error, GoodsReceiptPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Goods Receipt persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_actual_sale_settlement_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteActualSaleSettlementRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = ActualSaleSettlementProductionEntry(
            AdmitActualSaleSettlement(
                repository,
                settlement_id_generator=ProductionActualSaleSettlementIdentityGenerator(),
                admitted_clock=clock,
                committed_clock=clock,
            )
        )
    except (sqlite3.Error, ActualSaleSettlementPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Actual Sale Settlement persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_actual_outcome_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteActualOutcomeRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = ActualOutcomeProductionEntry(
            CalculateActualOutcome(
                repository,
                outcome_id_generator=ProductionActualOutcomeIdentityGenerator(),
                calculated_clock=clock,
                committed_clock=clock,
            )
        )
    except (
        sqlite3.Error,
        ActualOutcomePersistenceError,
        ActualAcquisitionSettlementPersistenceError,
        ActualSaleSettlementPersistenceError,
        GoodsReceiptPersistenceError,
    ) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Actual Outcome persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_conservative_actual_variance_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteConservativeActualVarianceRepository(DEFAULT_DATABASE_PATH)
        )
        clock = ProductionUTCClock()
        entry = ConservativeActualVarianceProductionEntry(
            CalculateConservativeActualVariance(
                repository,
                variance_id_generator=ProductionConservativeActualVarianceIdentityGenerator(),
                calculated_clock=clock,
                committed_clock=clock,
            )
        )
    except (
        sqlite3.Error,
        ConservativeActualVariancePersistenceError,
        ConservativeEconomicsPersistenceError,
        ActualOutcomePersistenceError,
        EconomicsSourceCompositionPersistenceError,
        AcquisitionCostNormalizationPersistenceError,
        LandedCostCompositionPersistenceError,
        SourcingEconomicsBindingPersistenceError,
        SourcingAuthorityPersistenceError,
        PlannedAcquisitionCapitalRequirementPersistenceError,
    ) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Conservative Actual Variance persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_owned_inventory_query():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteActualSaleSettlementRepository(DEFAULT_DATABASE_PATH)
        )
        query = GetOwnedInventoryPositionsV2(repository)
    except (
        sqlite3.Error,
        GoodsReceiptPersistenceError,
        ActualSaleSettlementPersistenceError,
    ) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="Owned Inventory persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield query
    finally:
        resources.close()


def get_sourcing_economics_binding_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteSourcingEconomicsBindingRepository(DEFAULT_DATABASE_PATH)
        )
        owner = BindSourcingEconomicsSource(
            repository,
            binding_id_generator=ProductionSourcingEconomicsBindingIdentityGenerator(),
            bound_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = SourcingEconomicsBindingProductionEntry(repository, owner)
    except (sqlite3.Error, SourcingEconomicsBindingPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="sourcing economics binding persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_landed_cost_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteLandedCostCompositionRepository(DEFAULT_DATABASE_PATH)
        )
        owner = ComposeLandedCost(
            repository,
            composition_id_generator=ProductionLandedCostCompositionIdentityGenerator(),
            composed_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = LandedCostProductionEntry(repository, owner)
    except (sqlite3.Error, LandedCostCompositionPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="landed cost persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_shipping_allocation_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteShippingAllocationAuthorityRepository(DEFAULT_DATABASE_PATH)
        )
        owner = AdmitShippingAllocationAuthority(
            repository,
            authority_id_generator=(
                ProductionShippingAllocationAuthorityIdentityGenerator()
            ),
            admitted_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = ShippingAllocationProductionEntry(repository, owner)
    except (sqlite3.Error, ShippingAllocationAuthorityPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="shipping allocation persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_fx_observation_owner():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteFXObservationRepository(DEFAULT_DATABASE_PATH)
        )
        owner = AdmitFXObservation(
            repository,
            observation_id_generator=ProductionFXObservationIdentityGenerator(),
            admitted_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
    except (sqlite3.Error, FXObservationPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="FX observation persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield owner
    finally:
        resources.close()


def get_acquisition_normalization_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteAcquisitionCostNormalizationRepository(DEFAULT_DATABASE_PATH)
        )
        owner = NormalizeAcquisitionCosts(
            repository,
            normalization_id_generator=(
                ProductionAcquisitionCostNormalizationIdentityGenerator()
            ),
            normalized_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = AcquisitionNormalizationProductionEntry(repository, owner)
    except (sqlite3.Error, AcquisitionCostNormalizationPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="acquisition normalization persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_economics_source_composition_entry():
    resources = ExitStack()
    try:
        repository = resources.enter_context(
            SQLiteEconomicsSourceCompositionRepository(DEFAULT_DATABASE_PATH)
        )
        owner = ComposeEconomicsSources(
            repository,
            composition_id_generator=(
                ProductionEconomicsSourceCompositionIdentityGenerator()
            ),
            composed_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        entry = EconomicsSourceCompositionProductionEntry(repository, owner)
    except (sqlite3.Error, EconomicsSourceCompositionPersistenceError) as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="economics source composition persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_snapshot_chain_entry():
    resources = ExitStack()
    try:
        promotion_repository = SQLiteCandidatePromotionRepository(
            DEFAULT_DATABASE_PATH
        )
        resources.callback(promotion_repository.close)
        capture_repository = resources.enter_context(
            SQLiteProductSnapshotCaptureRepository(DEFAULT_DATABASE_PATH)
        )
        price_analysis_repository = resources.enter_context(
            SQLitePriceAnalysisRepository(DEFAULT_DATABASE_PATH)
        )
        economics_repository = resources.enter_context(
            SQLiteEconomicsCalculationOwnerRepository(DEFAULT_DATABASE_PATH)
        )
        snapshot_chain_repository = resources.enter_context(
            SQLiteSnapshotChainBindingRepository(DEFAULT_DATABASE_PATH)
        )
        entry = CompleteSnapshotChainProductionEntry(
            source_repository=promotion_repository,
            product_snapshot_capture_repository=capture_repository,
            price_analysis_repository=price_analysis_repository,
            economics_repository=economics_repository,
            snapshot_chain_repository=snapshot_chain_repository,
            binding_id_generator=(
                ProductionSnapshotChainBindingIdentityGenerator()
            ),
            bound_clock=lambda: datetime.now(timezone.utc),
            receipt_clock=lambda: datetime.now(timezone.utc),
        )
    except sqlite3.Error as error:
        resources.close()
        raise HTTPException(
            status_code=503,
            detail="snapshot chain persistence unavailable",
        ) from error
    except BaseException:
        resources.close()
        raise
    try:
        yield entry
    finally:
        resources.close()


def get_opportunity_decision_dashboard_provider():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    market_repository = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    safety_repository = SQLiteProductionSafetyEvaluationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield ProductionOpportunityDecisionDashboardProvider(
            repository,
            production_safety_repository=safety_repository,
            assessment_repository=market_repository,
        )
    finally:
        safety_repository.close()
        market_repository.close()
        repository.close()


def get_decision_composition_finalizer():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    market_repository = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    safety_repository = SQLiteProductionSafetyEvaluationRepository(DEFAULT_DATABASE_PATH)
    review_repository = SQLiteReviewSessionRepository(DEFAULT_DATABASE_PATH)
    try:
        yield FinalizeOpportunityDecisionComposition(
            FinalizeDecisionComposition(
                source_repository=repository,
                assessment_repository=market_repository,
                composition_repository=repository,
                production_safety_repository=safety_repository,
                review_repository=review_repository,
            ),
            clock=lambda: datetime.now(timezone.utc),
        )
    finally:
        review_repository.close()
        safety_repository.close()
        market_repository.close()
        repository.close()


def get_review_session_query_service():
    persistence = SQLiteVerifiedSignalPersistence(DEFAULT_DATABASE_PATH)
    try:
        yield ReviewSessionQueryService(
            persistence.sessions,
            persistence.ledger,
        )
    finally:
        persistence.close()


def get_review_workflow_service():
    persistence = SQLiteVerifiedSignalPersistence(DEFAULT_DATABASE_PATH)
    try:
        yield ReviewWorkflowService(
            persistence.ledger,
            persistence=persistence,
        )
    finally:
        persistence.close()


def get_opportunity_review_ui_query_service():
    persistence = SQLiteVerifiedSignalPersistence(DEFAULT_DATABASE_PATH)
    try:
        yield OpportunityReviewUIQueryService(persistence.opportunities, persistence.sessions, persistence.ledger, persistence.observations)
    finally:
        persistence.close()


def get_decision_readiness_service():
    persistence = SQLiteVerifiedSignalPersistence(DEFAULT_DATABASE_PATH)
    safety = SQLiteProductionSafetyEvaluationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield DecisionReadinessService(persistence.opportunities, persistence.observations, persistence.sessions, safety)
    finally:
        safety.close()
        persistence.close()


def get_production_safety_api_service():
    repository = SQLiteProductionSafetyEvaluationRepository(DEFAULT_DATABASE_PATH)
    try:
        adapter = ProductionSafetyRuntimeAdapter(
            repository.verified_economics_repository,
            supported_analyzer_version="price-analyzer-v1",
            supported_calculation_version="verified-economics-calculator-v1",
        )
        evaluator = EvaluateAndPersistProductionSafety(
            repository, adapter,
            evaluation_id_generator=lambda: uuid4().hex,
            evaluated_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        yield EvaluateProductionSafetyApi(
            evaluator, repository.verified_economics_repository, repository
        )
    finally:
        repository.close()


def get_production_safety_detail_service():
    repository = SQLiteProductionSafetyEvaluationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield GetProductionSafetyOperationalDetail(
            repository, repository.verified_economics_repository
        )
    finally:
        repository.close()


def get_verified_economics_admission_service():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    try:
        yield FinalizeVerifiedEconomicsAdmission(repository)
    finally:
        repository.close()


def get_domestic_market_validation_entry():
    repository = None
    try:
        repository = SQLiteDomesticMarketValidationRepository(DEFAULT_DATABASE_PATH)
        owner = ValidateDomesticMarketForCapital(
            repository,
            assessment_id_generator=ProductionDomesticMarketValidationIdentityGenerator(),
            evaluated_clock=lambda: datetime.now(timezone.utc),
            committed_clock=lambda: datetime.now(timezone.utc),
        )
        yield DomesticMarketValidationProductionEntry(repository, owner)
    except (sqlite3.Error, DomesticMarketValidationPersistenceError) as error:
        raise HTTPException(
            status_code=503,
            detail="domestic market validation persistence unavailable",
        ) from error
    finally:
        if repository is not None:
            repository.close()


def get_competition_admission_service():
    opportunities = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    observations = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield FinalizeCompetitionObservationAdmission(opportunities, observations)
    finally:
        observations.close(); opportunities.close()


def get_demand_admission_service():
    opportunities = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    observations = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    try: yield FinalizeDemandObservationAdmission(opportunities, observations)
    finally: observations.close(); opportunities.close()


def _validation_service(repository: SQLiteValidationQueueRepository) -> OpportunityValidationService:
    return OpportunityValidationService(
        queue_repository=repository,
        lifecycle_repository=repository,
    )


def _action_command(opportunity_id: str, request: ValidationQueueActionRequest) -> ValidationActionCommand:
    return ValidationActionCommand(
        opportunity_id=opportunity_id,
        expected_version=request.expected_version,
        operator_id=request.operator_id,
        reason=request.reason,
        occurred_at=request.occurred_at,
        note=request.note,
    )


def _operation_payload(result) -> dict[str, object]:
    return {
        "opportunity_id": result.lifecycle.opportunity_id,
        "lifecycle_status": result.lifecycle.status.value,
        "lifecycle_version": result.lifecycle.version,
        "updated_at": result.lifecycle.updated_at.isoformat(),
        "founder_decision": (
            {
                "decision_id": result.founder_decision.decision_id,
                "decision": result.founder_decision.decision.value,
                "reason": result.founder_decision.reason,
                "note": result.founder_decision.note,
                "decided_at": result.founder_decision.decided_at.isoformat(),
                "operator_id": result.founder_decision.operator_id,
            }
            if result.founder_decision is not None
            else None
        ),
    }


def _execute_validation_action(operation, command: ValidationActionCommand):
    try:
        return _operation_payload(operation(command))
    except LifecycleNotFoundError as error:
        raise HTTPException(status_code=404, detail="validation opportunity not found") from error
    except DuplicateActiveValidationError as error:
        raise HTTPException(
            status_code=409,
            detail="duplicate non-archived validation exists",
        ) from error
    except (LifecycleVersionConflictError, InvalidLifecycleTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "founder_discovery_profile": _founder_discovery_profile_payload(),
        },
    )


@app.get("/dashboard/decision")
def decision_dashboard_entry(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="decision_dashboard.html",
        context={"opportunity_id": ""},
    )


@app.get("/dashboard/opportunities/{opportunity_id}/decision")
def decision_dashboard_page(request: Request, opportunity_id: str):
    return templates.TemplateResponse(
        request=request,
        name="decision_dashboard.html",
        context={"opportunity_id": opportunity_id},
    )


@app.get("/reviews")
def review_queue_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="review_queue.html",
    )


@app.get("/opportunities")
def opportunity_list_page(request: Request):
    return templates.TemplateResponse(request=request, name="opportunity_list.html", context={})


@app.get("/opportunities/{opportunity_id}")
def opportunity_detail_page(request: Request, opportunity_id: str):
    return templates.TemplateResponse(request=request, name="opportunity_detail.html", context={"opportunity_id": opportunity_id})


@app.get("/reviews/{session_id}")
def review_detail_page(request: Request, session_id: str):
    return templates.TemplateResponse(
        request=request,
        name="review_detail.html",
        context={"session_id": session_id},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "project": PROJECT_NAME,
        "api_version": API_VERSION,
    }


@app.post("/api/v1/opportunities/search")
def search_opportunities(
    request: OpportunitySearchRequest,
) -> dict[str, object]:
    query = request.query.strip()

    if not query:
        raise HTTPException(
            status_code=422,
            detail="query must not be blank",
        )

    try:
        results = find_best_opportunities(
            query=query,
            limit=request.limit,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=502,
            detail="opportunity search failed",
        ) from error

    selected_results = results[:request.top]
    opportunity_list = build_opportunity_list_card(
        results,
        limit=request.top,
    )
    dashboard_cards = build_dashboard_cards(
        selected_results
    )

    return {
        "query": query,
        "opportunities": opportunity_list.to_dict(),
        "dashboard_cards": [
            card.to_dict()
            for card in dashboard_cards
        ],
    }


@app.post(
    "/api/v1/discovery/executions",
    response_model=AuthoritativeDiscoveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def execute_authoritative_discovery(
    request: AuthoritativeDiscoveryRequest,
    response: Response,
    entry: PersistedDiscoveryExecutionEntry = Depends(
        get_authoritative_discovery_entry
    ),
) -> AuthoritativeDiscoveryResponse:
    try:
        command = _validate_referenced_founder_profile(request.to_command())
        result = entry.execute(command)
    except (
        DiscoveryReplayConflict,
        DuplicateDiscoveryExecutionError,
        DuplicateDiscoveryObservationError,
        DiscoveryObservationConflictError,
        DuplicateFinalizedGroupError,
        DiscoveryGroupConflictError,
        DiscoveryGroupMembershipError,
        DiscoveryExecutionIdentityConflictError,
        DiscoveryExecutionNotFoundError,
        DiscoveryExecutionReplayConflict,
        MissingDiscoveryCommand,
        DiscoveryRuntimeCorrelationError,
        DiscoveryCompletionReplayError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ExchangeRateNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DiscoveryPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="discovery persistence unavailable",
        ) from error
    except ExchangeRateProviderError as error:
        raise HTTPException(
            status_code=502,
            detail="discovery currency conversion failed",
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=502,
            detail="authoritative discovery execution failed",
        ) from error

    if result.completion_replayed:
        response.status_code = status.HTTP_200_OK
    execution_result = result.execution_result
    return AuthoritativeDiscoveryResponse(
        command_id=execution_result.command_id,
        discovery_execution_id=execution_result.discovery_execution_id,
        completed_at=execution_result.completed_at,
        is_zero_result=execution_result.is_zero_result,
        completion_replayed=result.completion_replayed,
        finalized_groups=tuple(
            AuthoritativeFinalizedGroupResponse(
                finalized_group_id=group.finalized_group_id,
                discovery_execution_id=group.discovery_execution_id,
                observation_ids=group.observation_ids,
                representative_observation_id=(
                    group.representative_observation_id
                ),
                grouping_policy_version=group.grouping_policy_version,
                finalized_at=group.finalized_at,
            )
            for group in result.finalized_groups
        ),
    )


@app.get(
    "/api/v1/discovery/executions/{discovery_execution_id}",
    response_model=DiscoveryExecutionResultReadResponse,
)
def get_authoritative_discovery_result(
    discovery_execution_id: str,
    reader: PersistedDiscoveryResultReader = Depends(
        get_authoritative_discovery_reader
    ),
) -> DiscoveryExecutionResultReadResponse:
    try:
        result = reader.get_execution_result(discovery_execution_id)
    except DiscoveryExecutionResultNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DiscoveryCompletionReplayError,
        DiscoveryExecutionIdentityConflictError,
        DiscoveryGroupMembershipError,
        MalformedDiscoveryExecutionResult,
        MalformedDiscoveryGroupPersistenceError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DiscoveryPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="discovery persistence unavailable",
        ) from error
    return DiscoveryExecutionResultReadResponse(
        command_id=result.command_id,
        discovery_execution_id=result.discovery_execution_id,
        completed_at=result.completed_at,
        is_zero_result=result.is_zero_result,
        finalized_group_ids=result.finalized_group_ids,
    )


@app.get(
    "/api/v1/discovery/executions/{discovery_execution_id}/finalized-groups",
    response_model=DiscoveryFinalizedGroupsReadResponse,
)
def get_authoritative_discovery_groups(
    discovery_execution_id: str,
    reader: PersistedDiscoveryResultReader = Depends(
        get_authoritative_discovery_reader
    ),
) -> DiscoveryFinalizedGroupsReadResponse:
    try:
        groups = reader.get_finalized_group_read_models(discovery_execution_id)
    except DiscoveryExecutionResultNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DiscoveryCompletionReplayError,
        DiscoveryExecutionIdentityConflictError,
        DiscoveryGroupMembershipError,
        MalformedDiscoveryExecutionResult,
        MalformedDiscoveryGroupPersistenceError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DiscoveryPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="discovery persistence unavailable",
        ) from error
    finalized_groups = []
    for read_model in groups:
        group = read_model.group
        finalized_groups.append(
            FounderFinalizedGroupReadResponse(
                finalized_group_id=group.finalized_group_id,
                discovery_execution_id=group.discovery_execution_id,
                observation_ids=group.observation_ids,
                representative_observation_id=(
                    group.representative_observation_id
                ),
                grouping_policy_version=group.grouping_policy_version,
                finalized_at=group.finalized_at,
                representative_observation=RepresentativeObservationPreviewResponse(
                    title=read_model.representative_observation.title,
                    image_url=read_model.representative_observation.image_url,
                    marketplace=read_model.representative_observation.marketplace,
                    price=read_model.representative_observation.price,
                    currency=read_model.representative_observation.currency,
                    url=read_model.representative_observation.url,
                ),
                candidate_handoff=(
                    None
                    if read_model.candidate_handoff is None
                    else RepresentativeCandidateHandoffResponse(
                        observation_id=(
                            read_model.candidate_handoff.observation_id
                        ),
                        market_observation_identity=(
                            CandidateHandoffMarketIdentityResponse(
                                scope=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.scope
                                ),
                                market=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.market
                                ),
                                marketplace=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.marketplace
                                ),
                                canonical_product_id=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.canonical_product_id
                                ),
                                marketplace_item_id=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.marketplace_item_id
                                ),
                                normalized_query=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.normalized_query
                                ),
                                category=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.category
                                ),
                                variant_identity=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.variant_identity
                                ),
                                condition=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.condition
                                ),
                                window_started_at=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.window_started_at
                                ),
                                window_ended_at=(
                                    read_model.candidate_handoff
                                    .market_observation_identity.window_ended_at
                                ),
                            )
                        ),
                        discovery_reference=(
                            read_model.candidate_handoff.discovery_reference
                        ),
                        policy_name=read_model.candidate_handoff.policy_name,
                        policy_version=read_model.candidate_handoff.policy_version,
                        observed_at=read_model.candidate_handoff.observed_at,
                        collector_source_reference=(
                            read_model.candidate_handoff.collector_source_reference
                        ),
                    )
                ),
                observation_count=read_model.observation_count,
            )
        )
    return DiscoveryFinalizedGroupsReadResponse(
        discovery_execution_id=discovery_execution_id,
        finalized_groups=tuple(finalized_groups),
    )


@app.post(
    "/api/v1/ocr/executions",
    response_model=ExternalOCRAdmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_external_ocr_execution(
    request: ExternalOCRAdmissionRequest,
    response: Response,
    entry: ExternalOCRCandidateAdmission = Depends(
        get_external_ocr_admission_entry
    ),
) -> ExternalOCRAdmissionResponse:
    try:
        result = entry.execute(request.to_command())
    except (
        ArtifactAdmissionConflictError,
        OCRExecutionConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except OCRAdmissionValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (
        OCRAdmissionDependencyError,
        OCRExecutionPersistenceError,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="OCR admission persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return _external_ocr_admission_response(result)


def _external_ocr_admission_response(
    result: ExternalOCRAdmissionResult,
) -> ExternalOCRAdmissionResponse:
    execution = result.execution.result
    receipt = result.receipt
    return ExternalOCRAdmissionResponse(
        execution_replay_key=OCRExecutionReplayKeyResponse(
            provider=receipt.provider,
            request_id=receipt.request_id,
            artifact_id=receipt.artifact_id,
        ),
        artifact_sha256=receipt.artifact_sha256,
        ordered_candidate_ids=receipt.ordered_candidate_ids,
        artifact=OCRArtifactReferenceDTO.from_domain(
            result.artifact_admission.artifact
        ),
        execution=OCRExecutionProvenanceResponse(
            provider=execution.provider,
            provider_version=execution.provider_version,
            request_id=execution.request_id,
            artifact_id=execution.artifact_id,
            executed_at=execution.executed_at,
            result_confidence=execution.confidence,
            fields=tuple(
                OCRFieldResultDTO.from_domain(field)
                for field in execution.fields
            ),
            schema_version=execution.schema_version,
        ),
        candidate_schema_version=receipt.candidate_schema_version,
        committed_at=receipt.committed_at,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/candidates",
    response_model=CandidateIssuanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_opportunity_candidate(
    request: CandidateIssuanceRequest,
    response: Response,
    entry: CandidateIssuanceProductionEntry = Depends(
        get_candidate_issuance_entry
    ),
) -> CandidateIssuanceResponse:
    try:
        result = entry.execute(request.to_command())
    except (
        CandidateDiscoveryCommandNotFoundError,
        CandidateDiscoveryResultNotFoundError,
        CandidateFinalizedGroupNotFoundError,
        CandidateIssuanceNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CandidateDiscoveryReferenceConflictError,
        CandidateExecutionMismatchError,
        CandidateGroupNotInResultError,
        CandidateIssuanceCommandConflictError,
        CandidateIssuanceReplayConflictError,
        CandidateLineageConflictError,
        CandidateMarketIdentityConflictError,
        DuplicateOpportunityCandidateError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except MalformedCandidateIssuanceCommandError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CandidateIdentityGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except CandidatePersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="candidate persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    issuance = result.issuance
    receipt = result.receipt
    identity = issuance.discovery_context.market_observation_identity
    return CandidateIssuanceResponse(
        candidate_id=issuance.candidate_identity.candidate_id,
        discovery_reference=issuance.candidate_identity.discovery_reference,
        issuance_command_id=receipt.issuance_command_id,
        discovery_command_id=issuance.discovery_command_id,
        discovery_execution_id=(
            issuance.discovery_context.discovery_execution_id
        ),
        finalized_group_id=issuance.finalized_group_id,
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        requested_at=issuance.discovery_context.requested_at,
        issued_at=issuance.issued_at,
        receipt_committed_at=receipt.receipt_committed_at,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/candidate-promotions",
    response_model=CandidatePromotionResponse | CandidatePromotionV2Response,
    status_code=status.HTTP_201_CREATED,
)
def promote_opportunity_candidate(
    request: CandidatePromotionRequest | CandidatePromotionV2Request,
    response: Response,
    entry: CandidatePromotionProductionEntry = Depends(
        get_candidate_promotion_entry
    ),
) -> CandidatePromotionResponse | CandidatePromotionV2Response:
    try:
        result = (
            entry.execute_v2(request.to_command())
            if isinstance(request, CandidatePromotionV2Request)
            else entry.execute(request.to_command())
        )
    except (
        CandidateForPromotionNotFoundError,
        CandidatePromotionContextNotFoundError,
        CandidatePromotionV2SourceNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CandidateAlreadyPromotedError,
        CandidatePromotionCommandConflictError,
        CandidatePromotionIdentityConflictError,
        CandidatePromotionMarketIdentityConflictError,
        OpportunityAlreadyBoundToCandidateError,
        CandidatePromotionV2LineageConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        CandidatePromotionCommitError,
        CandidatePromotionHistoryError,
        CandidatePromotionPersistenceError,
        CandidatePromotionReceiptError,
        MalformedCandidatePromotionPersistenceError,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="candidate promotion persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    item = result.item
    binding = result.binding
    receipt = result.receipt
    identity = binding.market_observation_identity
    if isinstance(request, CandidatePromotionV2Request):
        basis = item.admission_basis
        return CandidatePromotionV2Response(
            contract_version="2.0.0",
            promotion_command_id=receipt.promotion_command_id,
            candidate_id=receipt.candidate_id,
            opportunity_id=receipt.opportunity_id,
            binding_id=binding.binding_id,
            admission_id=basis.admission_id,
            discovery_reference=binding.discovery_reference,
            discovery_command_id=binding.discovery_command_id,
            discovery_execution_id=binding.discovery_execution_id,
            finalized_group_id=binding.finalized_group_id,
            product_snapshot_capture_command_id=basis.product_snapshot_capture_command_id,
            product_snapshot_ids=basis.product_snapshot_ids,
            representative_product_snapshot_id=basis.representative_product_snapshot_id,
            market_observation_identity=MarketObservationIdentityRequest(
                scope=identity.scope, market=identity.market,
                marketplace=identity.marketplace,
                canonical_product_id=identity.canonical_product_id,
                marketplace_item_id=identity.marketplace_item_id,
                normalized_query=identity.normalized_query,
                category=identity.category, variant_identity=identity.variant_identity,
                condition=identity.condition,
                window_started_at=identity.window_started_at,
                window_ended_at=identity.window_ended_at,
            ),
            marketplace=item.marketplace, title=item.title, currency=item.currency,
            admission_kind=basis.admission_kind, operator_id=basis.operator_id,
            reason=basis.reason, lifecycle_status=item.lifecycle_status,
            lifecycle_version=item.lifecycle_version,
            requested_at=basis.requested_at, promoted_at=basis.promoted_at,
            committed_at=receipt.committed_at, replayed=result.replayed,
        )
    return CandidatePromotionResponse(
        promotion_command_id=receipt.promotion_command_id,
        candidate_id=receipt.candidate_id,
        opportunity_id=receipt.opportunity_id,
        binding_id=binding.binding_id,
        discovery_reference=binding.discovery_reference,
        discovery_command_id=binding.discovery_command_id,
        discovery_execution_id=binding.discovery_execution_id,
        finalized_group_id=binding.finalized_group_id,
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        marketplace=item.marketplace,
        title=item.title,
        admission_recommendation=item.recommendation,
        admission_score=item.score,
        admission_roi=item.roi,
        currency=item.currency,
        admission_safety_status=item.safety_status,
        lifecycle_status=item.lifecycle_status,
        lifecycle_version=item.lifecycle_version,
        requested_at=item.created_at,
        promoted_at=binding.promoted_at,
        committed_at=receipt.committed_at,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/product-snapshots/capture",
    response_model=ProductSnapshotCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
def capture_candidate_product_snapshots(
    request: ProductSnapshotCaptureRequest,
    response: Response,
    entry: CandidateProductSnapshotCaptureProductionEntry = Depends(
        get_product_snapshot_capture_entry
    ),
) -> ProductSnapshotCaptureResponse:
    try:
        result = entry.execute(request.to_application_request())
    except ProductSnapshotSourceObservationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ProductSnapshotSourceConflictError,
        SnapshotOwnerCommandConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SnapshotOwnerPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="product snapshot persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="product snapshot capture failed",
        ) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    identity = result.snapshots[0].market_observation_identity
    return ProductSnapshotCaptureResponse(
        command_id=result.receipt.command_id,
        candidate_id=result.receipt.candidate_id,
        finalized_group_id=request.finalized_group_id,
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        product_snapshot_ids=result.receipt.product_snapshot_ids,
        source_bindings=tuple(
            ProductSnapshotSourceBindingResponse(
                product_snapshot_id=binding.product_snapshot_id,
                collected_observation_id=binding.collected_observation_id,
                candidate_id=binding.candidate_id,
                capture_command_id=binding.capture_command_id,
                bound_at=binding.bound_at,
            )
            for binding in result.bindings
        ),
        committed_at=result.receipt.committed_at,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/price-analyses",
    response_model=PriceAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_candidate_prices(
    request: PriceAnalysisRequest,
    response: Response,
    entry: CandidatePriceAnalysisProductionEntry = Depends(
        get_candidate_price_analysis_entry
    ),
) -> PriceAnalysisResponse:
    try:
        result = entry.execute(request.to_application_request())
    except PriceAnalysisSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        PriceAnalysisCandidateMismatchError,
        PriceAnalysisCommandConflictError,
        PriceAnalysisGroupMismatchError,
        PriceAnalysisMarketIdentityConflictError,
        PriceAnalysisProductOrderConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PriceAnalysisExecutionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except PriceAnalysisPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="price analysis persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    snapshot = result.snapshot
    receipt = result.receipt
    identity = snapshot.market_observation_identity
    return PriceAnalysisResponse(
        command_id=receipt.command_id,
        candidate_id=receipt.candidate_id,
        finalized_group_id=receipt.finalized_group_id,
        price_snapshot_id=snapshot.snapshot_id,
        product_snapshot_ids=snapshot.product_observation_snapshot_ids,
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        analyzer_version=receipt.analyzer_version,
        fallback_multiplier=receipt.fallback_multiplier,
        requested_at=receipt.requested_at,
        generated_at=snapshot.generated_at,
        committed_at=receipt.committed_at,
        currency=snapshot.currency,
        lowest_price=snapshot.lowest_price,
        average_price=snapshot.average_price,
        median_price=snapshot.median_price,
        highest_price=snapshot.highest_price,
        price_range=snapshot.price_range,
        price_variation_rate=snapshot.price_variation_rate,
        price_stability_level=snapshot.price_stability_level,
        recommended_selling_price=snapshot.recommended_selling_price,
        sample_size=snapshot.sample_size,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/economics",
    response_model=EconomicsSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def calculate_opportunity_economics(
    request: EconomicsSnapshotRequest,
    response: Response,
    entry: EconomicsSnapshotProductionEntry = Depends(
        get_economics_snapshot_entry
    ),
) -> EconomicsSnapshotResponse:
    try:
        result = entry.execute(request.to_application_request())
    except EconomicsCalculationSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsCalculationBindingConflictError,
        EconomicsCalculationCommandConflictError,
        EconomicsCalculationMarketIdentityConflictError,
        EconomicsCalculationPriceSourceConflictError,
        EconomicsCalculationVerifiedSourceConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EconomicsCalculationExecutionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except EconomicsCalculationOwnerPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="economics persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    snapshot = result.snapshot
    receipt = result.receipt
    identity = snapshot.market_observation_identity
    parameters = snapshot.calculation_parameters
    profitability = snapshot.profitability_result
    return EconomicsSnapshotResponse(
        command_id=receipt.command_id,
        opportunity_id=receipt.opportunity_id,
        discovery_reference=snapshot.opportunity_identity.discovery_reference,
        candidate_id=receipt.candidate_id,
        candidate_opportunity_binding_id=(
            receipt.candidate_opportunity_binding_id
        ),
        price_analysis_command_id=receipt.price_analysis_command_id,
        price_intelligence_snapshot_id=(
            receipt.price_intelligence_snapshot_id
        ),
        verified_economics_opportunity_id=(
            receipt.verified_economics_opportunity_id
        ),
        economics_snapshot_id=snapshot.snapshot_id,
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        calculation_parameters=EconomicsCalculationParametersRequest(
            marketplace=parameters.marketplace,
            minimum_net_profit=parameters.minimum_net_profit,
            minimum_roi=parameters.minimum_roi,
            estimated_monthly_sales=parameters.estimated_monthly_sales,
            competitor_count=parameters.competitor_count,
            risk_level=parameters.risk_level,
            context_items=parameters.context_items,
        ),
        calculation_version=receipt.calculation_version,
        requested_at=receipt.requested_at,
        generated_at=snapshot.generated_at,
        committed_at=receipt.committed_at,
        currency=snapshot.revenue.currency,
        revenue=snapshot.revenue.amount,
        marketplace_fee=snapshot.marketplace_fee.amount,
        payment_fee=snapshot.payment_fee.amount,
        tax_cost=snapshot.tax_cost.amount,
        landed_cost=snapshot.landed_cost.amount,
        selling_cost=snapshot.selling_cost.amount,
        total_cost=snapshot.total_cost.amount,
        net_profit=snapshot.net_profit.amount,
        break_even=snapshot.break_even.amount,
        roi=snapshot.roi,
        landed_cost_roi=snapshot.landed_cost_roi,
        margin_rate=snapshot.margin_rate,
        minimum_net_profit=profitability.minimum_net_profit,
        minimum_roi=profitability.minimum_roi,
        passes_net_profit_filter=profitability.passes_net_profit_filter,
        passes_roi_filter=profitability.passes_roi_filter,
        passes_profitability_filter=profitability.passes_profitability_filter,
        replayed=result.replayed,
    )


def _authority_evidence_payload(value) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "source_reference": value.source_reference,
        "observed_at": value.observed_at,
        "artifact_reference": _sourcing_artifact_payload(value.artifact_reference),
    }


def _economics_evidence_payload(value) -> dict[str, object]:
    return {
        "status": value.status.value,
        "source": value.source,
        "observed_at": value.observed_at,
        "reference": value.reference,
    }


def _economics_value_payload(value) -> dict[str, object]:
    numeric_name = "amount" if hasattr(value, "amount") else "rate"
    numeric = getattr(value, numeric_name)
    payload = {
        numeric_name: None if numeric is None else str(numeric),
        "evidence": _economics_evidence_payload(value.evidence),
    }
    if hasattr(value, "currency"):
        payload["currency"] = value.currency
    return payload


@app.post(
    "/api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings",
    response_model=SourcingEconomicsBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def bind_sourcing_economics_source(
    opportunity_id: str,
    request: SourcingEconomicsBindingRequest,
    response: Response,
    entry: SourcingEconomicsBindingProductionEntry = Depends(
        get_sourcing_economics_binding_entry
    ),
) -> SourcingEconomicsBindingResponse:
    try:
        result = entry.execute(request.to_production(opportunity_id))
    except SourcingEconomicsSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsProductionOpportunityConflictError,
        SourcingEconomicsBindingOpportunityMismatchError,
        SourcingEconomicsExactRevisionError,
        SourcingEconomicsBindingReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (SourcingEconomicsBindingPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="sourcing economics binding persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    binding, receipt, source = result.binding, result.receipt, result.binding.source_reference
    return SourcingEconomicsBindingResponse(
        command_id=receipt.command_id,
        binding_id=binding.binding_id,
        opportunity_id=binding.opportunity_identity.opportunity_id,
        discovery_reference=binding.opportunity_identity.discovery_reference,
        admission_id=source.admission_id,
        admission_revision=source.admission_revision,
        quote_id=source.quote_id,
        quote_revision=source.quote_revision,
        requested_at=binding.requested_at,
        bound_at=binding.bound_at,
        committed_at=receipt.committed_at,
        binding_schema_version=binding.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/landed-cost-compositions",
    response_model=LandedCostCompositionResponse,
    status_code=status.HTTP_201_CREATED,
)
def compose_landed_cost(
    opportunity_id: str,
    request: LandedCostCompositionRequest,
    response: Response,
    entry: LandedCostProductionEntry = Depends(get_landed_cost_entry),
) -> LandedCostCompositionResponse:
    try:
        result = entry.execute(
            LandedCostProductionRequest(
                request.command_id,
                opportunity_id,
                request.binding_id,
                request.requested_at,
            )
        )
    except (SourcingEconomicsBindingNotFoundError, LandedCostCompositionSourceNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsProductionOpportunityConflictError,
        LandedCostCompositionOpportunityMismatchError,
        LandedCostCompositionExactSourceError,
        LandedCostCompositionReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (LandedCostCompositionPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="landed cost persistence unavailable") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    value, receipt = result.composition, result.receipt
    return LandedCostCompositionResponse(
        command_id=receipt.command_id,
        composition_id=value.composition_id,
        opportunity_id=value.opportunity_identity.opportunity_id,
        discovery_reference=value.opportunity_identity.discovery_reference,
        binding_id=value.binding_reference.binding_id,
        components=tuple(
            LandedCostComponentResponse(
                kind=item.kind.value,
                availability=item.availability.value,
                amount=None if item.amount is None else str(item.amount),
                currency=item.currency,
                allocation_basis=item.allocation_basis.value,
            )
            for item in value.components
        ),
        minimum_order_quantity=SourcingQuantityResponse(
            availability=value.minimum_order_quantity.availability.value,
            quantity=value.minimum_order_quantity.quantity,
        ),
        quoted_quantity=SourcingQuantityResponse(
            availability=value.quoted_quantity.availability.value,
            quantity=value.quoted_quantity.quantity,
        ),
        evidence_reference=AuthorityEvidenceResponse.model_validate(
            _authority_evidence_payload(value.evidence_reference)
        ),
        requested_at=value.requested_at,
        composed_at=value.composed_at,
        committed_at=receipt.committed_at,
        composition_schema_version=value.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/shipping-allocation-authorities",
    response_model=ShippingAllocationAuthorityResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_shipping_allocation(
    opportunity_id: str,
    request: ShippingAllocationAuthorityRequest,
    response: Response,
    entry: ShippingAllocationProductionEntry = Depends(get_shipping_allocation_entry),
) -> ShippingAllocationAuthorityResponse:
    try:
        result = entry.execute(
            ShippingAllocationProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                composition_id=request.composition_id,
                component_kind=request.component_kind,
                requested_at=request.requested_at,
                effective_allocation_basis=request.effective_allocation_basis,
                per_order_denominator=request.per_order_denominator,
                per_order_denominator_unit=request.per_order_denominator_unit,
                operator_id=request.operator_id,
                verified_at=request.verified_at,
                evidence_reference=(
                    None
                    if request.evidence_reference is None
                    else request.evidence_reference.to_domain()
                ),
            )
        )
    except (ShippingAllocationSourceNotFoundError, ShippingAllocationComponentNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsProductionOpportunityConflictError,
        ShippingAllocationOpportunityMismatchError,
        ShippingAllocationBasisConflictError,
        ShippingAllocationAuthorityReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ShippingAllocationProvenanceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (ShippingAllocationAuthorityPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="shipping allocation persistence unavailable") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    value, receipt = result.authority, result.receipt
    denominator = value.denominator
    return ShippingAllocationAuthorityResponse(
        command_id=receipt.command_id,
        authority_id=value.authority_id,
        composition_id=value.composition_id,
        opportunity_id=value.opportunity_identity.opportunity_id,
        discovery_reference=value.opportunity_identity.discovery_reference,
        component_kind=value.component_kind.value,
        original_allocation_basis=value.original_allocation_basis.value,
        allocation_basis=value.allocation_basis.value,
        basis_authority_source=value.basis_authority_source.value,
        status=value.status.value,
        denominator=(
            None
            if denominator is None
            else ShippingAllocationDenominatorResponse(
                quantity=denominator.quantity,
                source=denominator.source.value,
                source_reference=denominator.source_reference,
                quantity_unit=denominator.quantity_unit,
            )
        ),
        unresolved_code=(None if value.unresolved_code is None else value.unresolved_code.value),
        evidence_reference=AuthorityEvidenceResponse.model_validate(
            _authority_evidence_payload(value.evidence_reference)
        ),
        operator_id=value.operator_id,
        verified_at=value.verified_at,
        requested_at=value.requested_at,
        admitted_at=value.admitted_at,
        committed_at=receipt.committed_at,
        authority_schema_version=value.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/fx-observations",
    response_model=FXObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_fx_observation(
    request: FXObservationAdmissionRequest,
    response: Response,
    owner: AdmitFXObservation = Depends(get_fx_observation_owner),
) -> FXObservationResponse:
    try:
        result = owner.execute(
            AdmitFXObservationCommand(
                command_id=request.command_id,
                base_currency=request.base_currency,
                quote_currency=request.quote_currency,
                rate=Decimal(request.rate),
                observed_at=request.observed_at,
                provider=request.provider,
                source_reference=request.source_reference,
                collection_method=request.collection_method,
            )
        )
    except FXObservationReplayConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (FXObservationPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="FX observation persistence unavailable") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    value, receipt = result.observation, result.receipt
    return FXObservationResponse(
        command_id=receipt.command_id,
        observation_id=value.observation_id,
        base_currency=value.base_currency,
        quote_currency=value.quote_currency,
        rate=str(value.rate),
        observed_at=value.observed_at,
        admitted_at=value.admitted_at,
        provider=value.provenance.provider,
        source_reference=value.provenance.source_reference,
        collection_method=value.provenance.collection_method,
        committed_at=receipt.committed_at,
        observation_schema_version=value.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
    response_model=AcquisitionCostNormalizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def normalize_acquisition_costs(
    opportunity_id: str,
    request: AcquisitionCostNormalizationRequest,
    response: Response,
    entry: AcquisitionNormalizationProductionEntry = Depends(
        get_acquisition_normalization_entry
    ),
) -> AcquisitionCostNormalizationResponse:
    try:
        result = entry.execute(
            AcquisitionNormalizationProductionRequest(
                request.command_id,
                opportunity_id,
                request.composition_id,
                request.allocation_authority_ids,
                request.fx_observation_ids,
                request.target_currency,
                request.requested_at,
            )
        )
    except EconomicsProductionSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsProductionOpportunityConflictError,
        AcquisitionCostNormalizationSourceError,
        AcquisitionCostNormalizationReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AcquisitionCostNormalizationPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (AcquisitionCostNormalizationPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="acquisition normalization persistence unavailable") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    value, receipt = result.normalization, result.receipt
    return AcquisitionCostNormalizationResponse(
        command_id=receipt.command_id,
        normalization_id=value.normalization_id,
        opportunity_id=value.opportunity_identity.opportunity_id,
        discovery_reference=value.opportunity_identity.discovery_reference,
        composition_id=value.composition_id,
        allocation_authority_ids=value.allocation_authority_ids,
        fx_observation_ids=value.fx_observation_ids,
        target_currency=value.target_currency,
        components=tuple(
            NormalizedAcquisitionComponentResponse(
                kind=item.kind.value,
                original_availability=item.original_availability.value,
                original_amount=(None if item.original_amount is None else str(item.original_amount)),
                original_currency=item.original_currency,
                original_allocation_basis=item.original_allocation_basis.value,
                effective_allocation_basis=item.effective_allocation_basis.value,
                allocation_authority_id=item.allocation_authority_id,
                denominator_quantity=item.denominator_quantity,
                denominator_source=(None if item.denominator_source is None else item.denominator_source.value),
                fx_observation_id=item.fx_observation_id,
                fx_direction=item.fx_direction.value,
                target_currency=item.target_currency,
                normalized_per_unit_amount=str(item.normalized_per_unit_amount),
            )
            for item in value.components
        ),
        total_per_unit_acquisition_cost=str(value.total_per_unit_acquisition_cost),
        policy_name=value.policy_name,
        policy_version=value.policy_version,
        policy_precision=value.policy_precision,
        policy_rounding=value.policy_rounding,
        requested_at=value.requested_at,
        normalized_at=value.normalized_at,
        committed_at=receipt.committed_at,
        normalization_schema_version=value.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
    response_model=EconomicsSourceCompositionResponse,
    status_code=status.HTTP_201_CREATED,
)
def compose_economics_sources(
    opportunity_id: str,
    request: EconomicsSourceCompositionRequest,
    response: Response,
    entry: EconomicsSourceCompositionProductionEntry = Depends(
        get_economics_source_composition_entry
    ),
) -> EconomicsSourceCompositionResponse:
    try:
        result = entry.execute(
            EconomicsSourceCompositionProductionRequest(
                request.command_id,
                opportunity_id,
                request.acquisition_normalization_id,
                request.verified_economics_snapshot_at,
                request.verified_economics_schema_version,
                request.requested_at,
            )
        )
    except EconomicsProductionSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        EconomicsProductionOpportunityConflictError,
        EconomicsSourceCompositionSourceError,
        EconomicsSourceCompositionReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EconomicsSourceCompositionPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (EconomicsSourceCompositionPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="economics source composition persistence unavailable") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    value, receipt = result.composition, result.receipt
    return EconomicsSourceCompositionResponse(
        command_id=receipt.command_id,
        composition_id=value.composition_id,
        opportunity_id=value.opportunity_identity.opportunity_id,
        discovery_reference=value.opportunity_identity.discovery_reference,
        acquisition_normalization_id=value.acquisition_normalization_id,
        acquisition_policy_name=value.acquisition_policy_name,
        acquisition_policy_version=value.acquisition_policy_version,
        acquisition_cost_per_unit=str(value.acquisition_cost_per_unit),
        economics_currency=value.economics_currency,
        verified_economics_opportunity_id=value.verified_economics_opportunity_id,
        verified_economics_snapshot_at=value.verified_economics_snapshot_at,
        verified_economics_schema_version=value.verified_economics_schema_version,
        expected_sale_price=_economics_value_payload(value.expected_sale_price),
        marketplace_fee_rate=_economics_value_payload(value.marketplace_fee_rate),
        payment_fee_rate=_economics_value_payload(value.payment_fee_rate),
        fixed_fee=_economics_value_payload(value.fixed_fee),
        tax_rate=_economics_value_payload(value.tax_rate),
        duty_cost=_economics_value_payload(value.duty_cost),
        other_cost=_economics_value_payload(value.other_cost),
        state=value.state.value,
        blocking_reasons=tuple(
            EconomicsSourceBlockingReasonResponse(
                code=item.code.value,
                category=item.category,
                source_reference=item.source_reference,
            )
            for item in value.blocking_reasons
        ),
        policy_name=value.policy_name,
        policy_version=value.policy_version,
        requested_at=value.requested_at,
        composed_at=value.composed_at,
        committed_at=receipt.committed_at,
        composition_schema_version=value.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/conservative-economics",
    response_model=ConservativeEconomicsResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_conservative_economics(
    opportunity_id: str,
    request: ConservativeEconomicsRequest,
    response: Response,
    entry: ConservativeEconomicsProductionEntry = Depends(
        get_conservative_economics_entry
    ),
) -> ConservativeEconomicsResponse:
    try:
        publication = entry.execute(request.to_application_request(opportunity_id))
    except ConservativeEconomicsSourceError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ConservativeEconomicsOpportunityConflictError,
        ConservativeEconomicsReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConservativeEconomicsPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConservativeEconomicsPersistenceError as error:
        raise HTTPException(
            status_code=503,
            detail="conservative economics persistence unavailable",
        ) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="conservative economics persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    result = publication.result
    receipt = publication.receipt
    return ConservativeEconomicsResponse(
        command_id=receipt.command_id,
        result_id=result.result_id,
        opportunity_id=result.opportunity_identity.opportunity_id,
        discovery_reference=result.opportunity_identity.discovery_reference,
        source_composition_id=result.source_composition_id,
        source_composition_schema_version=(
            result.source_composition_schema_version
        ),
        status=result.status.value,
        economics_currency=result.economics_currency,
        authoritative_expected_sale_price=(
            result.authoritative_expected_sale_price
        ),
        expected_sale_price_evidence_status=(
            result.expected_sale_price_evidence_status.value
        ),
        expected_sale_price_evidence_reference=(
            result.expected_sale_price_evidence_reference
        ),
        conservative_sale_price=result.conservative_sale_price,
        acquisition_cost_per_unit=result.acquisition_cost_per_unit,
        marketplace_fee=result.marketplace_fee,
        payment_fee=result.payment_fee,
        fixed_fee=result.fixed_fee,
        accepted_tax_cost=result.accepted_tax_cost,
        accepted_duty_cost=result.accepted_duty_cost,
        accepted_other_cost=result.accepted_other_cost,
        total_unit_cost=result.total_unit_cost,
        conservative_profit_per_unit=result.conservative_profit_per_unit,
        conservative_margin=result.conservative_margin,
        conservative_acquisition_roi=result.conservative_acquisition_roi,
        assumptions=tuple(
            ConservativeEconomicsAssumptionResponse(
                kind=value.kind.value,
                value=value.value,
                owner=value.owner,
            )
            for value in result.assumptions
        ),
        scenario_name=result.scenario_name,
        scenario_version=result.scenario_version,
        blocking_reasons=tuple(
            ConservativeEconomicsBlockingReasonResponse(
                code=value.code.value,
                category=value.category,
                source_reference=value.source_reference,
            )
            for value in result.blocking_reasons
        ),
        policy_name=result.policy_name,
        policy_version=result.policy_version,
        policy_precision=result.policy_precision,
        policy_rounding=result.policy_rounding,
        requested_at=result.requested_at,
        calculated_at=result.calculated_at,
        committed_at=receipt.committed_at,
        result_schema_version=result.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
    response_model=CriticalCostAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_critical_cost_completeness(
    opportunity_id: str,
    request: CriticalCostAssessmentRequest,
    response: Response,
    entry: CriticalCostCompletenessProductionEntry = Depends(
        get_critical_cost_assessment_entry
    ),
) -> CriticalCostAssessmentResponse:
    try:
        result = entry.execute(
            CriticalCostCompletenessProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                composition_id=request.composition_id,
                acquisition_normalization_id=(
                    request.acquisition_normalization_id
                ),
                verified_economics_opportunity_id=(
                    request.verified_economics_opportunity_id
                ),
                verified_economics_snapshot_at=(
                    request.verified_economics_snapshot_at
                ),
                verified_economics_schema_version=(
                    request.verified_economics_schema_version
                ),
                requested_at=request.requested_at,
            )
        )
    except CriticalCostSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CriticalCostSourceMismatchError,
        CriticalCostCompletenessReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CriticalCostCompletenessPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="critical cost persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    assessment, receipt = result.assessment, result.receipt
    source = assessment.source_reference
    reason = lambda value: CriticalCostReasonResponse(
        code=value.code.value,
        severity=value.severity.value,
        category=value.category,
        source_reference=value.source_reference,
    )
    return CriticalCostAssessmentResponse(
        command_id=receipt.command_id,
        assessment_id=receipt.assessment_id,
        opportunity_id=assessment.opportunity_identity.opportunity_id,
        discovery_reference=assessment.opportunity_identity.discovery_reference,
        state=assessment.state.value,
        blocking_reasons=tuple(reason(value) for value in assessment.blocking_reasons),
        warning_reasons=tuple(reason(value) for value in assessment.warning_reasons),
        composition_id=assessment.composition_id,
        acquisition_normalization_id=assessment.acquisition_normalization_id,
        allocation_authority_ids=assessment.allocation_authority_ids,
        fx_observation_ids=assessment.fx_observation_ids,
        binding_id=assessment.binding_reference.binding_id,
        sourcing_admission_id=source.admission_id,
        sourcing_admission_revision=source.admission_revision,
        quote_id=source.quote_id,
        quote_revision=source.quote_revision,
        verified_economics_opportunity_id=(
            assessment.verified_economics_opportunity_id
        ),
        verified_economics_snapshot_at=(
            assessment.verified_economics_snapshot_at
        ),
        verified_economics_schema_version=(
            assessment.verified_economics_schema_version
        ),
        policy_name=assessment.policy_name,
        policy_version=assessment.policy_version,
        requested_at=request.requested_at,
        evaluated_at=assessment.evaluated_at,
        committed_at=receipt.committed_at,
        assessment_schema_version=assessment.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=result.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
    response_model=CapitalReadinessAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_capital_readiness(
    opportunity_id: str,
    request: CapitalReadinessAssessmentRequest,
    response: Response,
    entry: CapitalReadinessProductionEntry = Depends(get_capital_readiness_entry),
) -> CapitalReadinessAssessmentResponse:
    try:
        result = entry.execute(
            CapitalReadinessProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                conservative_economics_result_id=(
                    request.conservative_economics_result_id
                ),
                domestic_market_validation_assessment_id=(
                    request.domestic_market_validation_assessment_id
                ),
                critical_cost_assessment_id=request.critical_cost_assessment_id,
                requested_at=request.requested_at,
            )
        )
    except CapitalReadinessSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CapitalReadinessSourceConflictError,
        CapitalReadinessReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CapitalReadinessPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (CapitalReadinessPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="capital readiness persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    publication = result.publication
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    assessment, receipt = publication.assessment, publication.receipt
    manifest = assessment.source_manifest
    identity = manifest.opportunity_identity
    return CapitalReadinessAssessmentResponse(
        command_id=receipt.command_id,
        assessment_id=assessment.assessment_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        state=assessment.state.value,
        blocking_reasons=tuple(
            reason.code.value for reason in assessment.blocking_reasons
        ),
        source_manifest=CapitalReadinessSourceManifestResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            conservative_economics_result_id=(
                manifest.conservative_economics_result_id
            ),
            economics_source_composition_id=(
                manifest.economics_source_composition_id
            ),
            acquisition_normalization_id=manifest.acquisition_normalization_id,
            landed_cost_composition_id=manifest.landed_cost_composition_id,
            domestic_market_validation_assessment_id=(
                manifest.domestic_market_validation_assessment_id
            ),
            critical_cost_assessment_id=manifest.critical_cost_assessment_id,
            sourcing_binding_id=manifest.sourcing_binding_id,
            sourcing_admission_id=manifest.sourcing_admission_id,
            sourcing_admission_revision=manifest.sourcing_admission_revision,
            quote_id=manifest.quote_id,
            quote_revision=manifest.quote_revision,
            product_match_verification_id=(
                manifest.product_match_verification_id
            ),
            quote_valid_until=manifest.quote_valid_until,
            schema_version=manifest.schema_version,
        ),
        critical_cost_normalization_id=result.critical_cost_normalization_id,
        policy_name=assessment.policy_name,
        policy_version=assessment.policy_version,
        requested_at=assessment.requested_at,
        evaluated_at=assessment.evaluated_at,
        committed_at=receipt.committed_at,
        assessment_schema_version=assessment.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/intended-order-quantities",
    response_model=IntendedOrderQuantityResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_intended_order_quantity(
    opportunity_id: str,
    request: IntendedOrderQuantityRequest,
    response: Response,
    entry: IntendedOrderQuantityProductionEntry = Depends(
        get_intended_order_quantity_entry
    ),
) -> IntendedOrderQuantityResponse:
    try:
        publication = entry.execute(
            IntendedOrderQuantityProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                sourcing_admission_id=request.sourcing_admission_id,
                sourcing_admission_revision=request.sourcing_admission_revision,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                quantity=request.quantity,
                quantity_unit=request.quantity_unit,
                operator_id=request.operator_id,
                declared_at=request.declared_at,
                requested_at=request.requested_at,
            )
        )
    except CapitalInvestmentSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CapitalInvestmentLineageError,
        CapitalInvestmentReplayConflictError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CapitalInvestmentPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503, detail="Capital investment persistence unavailable"
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    intent, receipt = publication.intent, publication.receipt
    identity = intent.opportunity_identity
    return IntendedOrderQuantityResponse(
        command_id=receipt.command_id,
        intent_id=intent.intent_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        sourcing_admission_id=intent.sourcing_admission_id,
        sourcing_admission_revision=intent.sourcing_admission_revision,
        quote_id=intent.quote_id,
        quote_revision=intent.quote_revision,
        quantity=intent.quantity,
        quantity_unit=intent.quantity_unit,
        operator_id=intent.operator_id,
        declared_at=intent.declared_at,
        requested_at=intent.requested_at,
        admitted_at=intent.admitted_at,
        committed_at=receipt.committed_at,
        intent_schema_version=intent.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/deployable-capital-snapshots",
    response_model=DeployableCapitalSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_deployable_capital_snapshot(
    request: DeployableCapitalSnapshotRequest,
    response: Response,
    entry: AdmitDeployableCapitalSnapshot = Depends(get_deployable_capital_entry),
) -> DeployableCapitalSnapshotResponse:
    try:
        publication = entry.execute(
            AdmitDeployableCapitalSnapshotCommand(
                command_id=request.command_id,
                amount=Decimal(request.amount),
                currency=request.currency,
                as_of=request.as_of,
                operator_id=request.operator_id,
                requested_at=request.requested_at,
            )
        )
    except CapitalInvestmentReplayConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CapitalInvestmentPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503, detail="Capital investment persistence unavailable"
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    snapshot, receipt = publication.snapshot, publication.receipt
    return DeployableCapitalSnapshotResponse(
        command_id=receipt.command_id,
        snapshot_id=snapshot.snapshot_id,
        amount=str(snapshot.amount),
        currency=snapshot.currency,
        as_of=snapshot.as_of,
        operator_id=snapshot.operator_id,
        requested_at=snapshot.requested_at,
        admitted_at=snapshot.admitted_at,
        committed_at=receipt.committed_at,
        semantics_version=snapshot.semantics_version,
        snapshot_schema_version=snapshot.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements",
    response_model=PlannedCapitalRequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
def calculate_planned_capital_requirement(
    opportunity_id: str,
    request: PlannedCapitalRequirementRequest,
    response: Response,
    entry: PlannedCapitalRequirementProductionEntry = Depends(
        get_planned_capital_requirement_entry
    ),
) -> PlannedCapitalRequirementResponse:
    try:
        publication = entry.execute(
            PlannedCapitalRequirementProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                intended_order_quantity_id=request.intended_order_quantity_id,
                acquisition_normalization_id=request.acquisition_normalization_id,
                scope_status=request.scope_status,
                operator_id=request.operator_id,
                verified_at=request.verified_at,
                requested_at=request.requested_at,
            )
        )
    except PlannedAcquisitionCapitalRequirementSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        PlannedAcquisitionCapitalRequirementLineageError,
        PlannedAcquisitionCapitalRequirementReplayConflictError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PlannedAcquisitionCapitalRequirementPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (
        PlannedAcquisitionCapitalRequirementPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="planned acquisition capital persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    requirement, receipt = publication.requirement, publication.receipt
    identity = requirement.opportunity_identity
    scope = requirement.scope_verification
    return PlannedCapitalRequirementResponse(
        command_id=receipt.command_id,
        requirement_id=requirement.requirement_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        state=requirement.state.value,
        blocking_reasons=tuple(value.value for value in requirement.blocking_reasons),
        intended_order_quantity_id=requirement.intended_order_quantity_id,
        acquisition_normalization_id=requirement.acquisition_normalization_id,
        sourcing_binding_id=requirement.sourcing_binding_id,
        sourcing_admission_id=requirement.sourcing_admission_id,
        sourcing_admission_revision=requirement.sourcing_admission_revision,
        quote_id=requirement.quote_id,
        quote_revision=requirement.quote_revision,
        quantity=requirement.quantity,
        quantity_unit=requirement.quantity_unit,
        normalized_acquisition_cost_per_unit=str(
            requirement.normalized_acquisition_cost_per_unit
        ),
        planned_acquisition_capital=(
            None
            if requirement.planned_acquisition_capital is None
            else str(requirement.planned_acquisition_capital)
        ),
        currency=requirement.currency,
        scope_status=scope.status.value,
        scope_operator_id=scope.operator_id,
        scope_verified_at=scope.verified_at,
        scope_semantics_version=scope.semantics_version,
        policy_name=requirement.policy_name,
        policy_version=requirement.policy_version,
        policy_precision=requirement.policy_precision,
        policy_rounding=requirement.policy_rounding,
        requested_at=requirement.requested_at,
        calculated_at=requirement.calculated_at,
        committed_at=receipt.committed_at,
        requirement_schema_version=requirement.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/capital-gate-assessments",
    response_model=CapitalGateAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_capital_gate(
    opportunity_id: str,
    request: CapitalGateAssessmentRequest,
    response: Response,
    entry: CapitalGateProductionEntry = Depends(get_capital_gate_entry),
) -> CapitalGateAssessmentResponse:
    try:
        publication = entry.execute(
            CapitalGateProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                capital_readiness_assessment_id=(
                    request.capital_readiness_assessment_id
                ),
                capital_requirement_id=request.capital_requirement_id,
                deployable_capital_snapshot_id=(
                    request.deployable_capital_snapshot_id
                ),
                requested_at=request.requested_at,
            )
        )
    except CapitalGateSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CapitalGateReplayConflictError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CapitalGatePolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (CapitalGatePersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503, detail="Capital Gate persistence unavailable"
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    assessment, receipt = publication.assessment, publication.receipt
    manifest, facts = assessment.source_manifest, assessment.evaluated_facts
    identity = manifest.opportunity_identity
    return CapitalGateAssessmentResponse(
        command_id=receipt.command_id,
        gate_id=assessment.gate_id,
        state=assessment.state.value,
        blocking_reasons=tuple(value.value for value in assessment.blocking_reasons),
        rejection_reasons=tuple(value.value for value in assessment.rejection_reasons),
        source_manifest=CapitalGateSourceManifestResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            capital_readiness_assessment_id=manifest.capital_readiness_assessment_id,
            capital_requirement_id=manifest.capital_requirement_id,
            deployable_capital_snapshot_id=manifest.deployable_capital_snapshot_id,
            conservative_economics_result_id=manifest.conservative_economics_result_id,
            intended_order_quantity_id=manifest.intended_order_quantity_id,
            acquisition_normalization_id=manifest.acquisition_normalization_id,
            sourcing_binding_id=manifest.sourcing_binding_id,
            sourcing_admission_id=manifest.sourcing_admission_id,
            sourcing_admission_revision=manifest.sourcing_admission_revision,
            quote_id=manifest.quote_id,
            quote_revision=manifest.quote_revision,
            schema_version=manifest.schema_version,
        ),
        evaluated_facts=CapitalGateEvaluatedFactsResponse(
            capital_readiness_state=facts.capital_readiness_state.value,
            capital_requirement_state=facts.capital_requirement_state.value,
            conservative_economics_status=facts.conservative_economics_status.value,
            requirement_currency=facts.requirement_currency,
            deployable_currency=facts.deployable_currency,
            planned_acquisition_capital=(
                None
                if facts.planned_acquisition_capital is None
                else str(facts.planned_acquisition_capital)
            ),
            deployable_capital=str(facts.deployable_capital),
            conservative_profit_per_unit=(
                None
                if facts.conservative_profit_per_unit is None
                else str(facts.conservative_profit_per_unit)
            ),
            conservative_margin=(
                None
                if facts.conservative_margin is None
                else str(facts.conservative_margin)
            ),
            conservative_acquisition_roi=(
                None
                if facts.conservative_acquisition_roi is None
                else str(facts.conservative_acquisition_roi)
            ),
            intended_order_quantity=facts.intended_order_quantity,
            intended_order_quantity_unit=facts.intended_order_quantity_unit,
            minimum_order_quantity_availability=(
                facts.minimum_order_quantity.availability.value
            ),
            minimum_order_quantity=facts.minimum_order_quantity.quantity,
            deployable_capital_semantics_version=(
                facts.deployable_capital_semantics_version
            ),
            schema_version=facts.schema_version,
        ),
        policy_name=assessment.policy_name,
        policy_version=assessment.policy_version,
        requested_at=assessment.requested_at,
        evaluated_at=assessment.evaluated_at,
        committed_at=receipt.committed_at,
        assessment_schema_version=assessment.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/founder-capital-approvals",
    response_model=FounderCapitalApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
def approve_founder_capital(
    opportunity_id: str,
    request: FounderCapitalApprovalRequest,
    response: Response,
    entry: FounderCapitalApprovalProductionEntry = Depends(
        get_founder_capital_approval_entry
    ),
) -> FounderCapitalApprovalResponse:
    try:
        publication = entry.execute(
            FounderCapitalApprovalProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                capital_gate_id=request.capital_gate_id,
                founder_id=request.founder_id,
                approved_capital=Decimal(request.approved_capital),
                currency=request.currency,
                requested_at=request.requested_at,
                approved_at=request.approved_at,
            )
        )
    except FounderCapitalApprovalSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        FounderCapitalApprovalGateStateError,
        FounderCapitalApprovalAmountError,
        FounderCapitalApprovalCurrencyError,
        FounderCapitalApprovalReplayConflictError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except FounderCapitalApprovalPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (FounderCapitalApprovalPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503, detail="Founder Capital Approval persistence unavailable"
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    approval, receipt = publication.approval, publication.receipt
    identity = approval.opportunity_identity
    return FounderCapitalApprovalResponse(
        command_id=receipt.command_id,
        approval_id=approval.approval_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        capital_gate_id=approval.capital_gate_id,
        capital_gate_policy_name=approval.capital_gate_policy_name,
        capital_gate_policy_version=approval.capital_gate_policy_version,
        capital_requirement_id=approval.capital_requirement_id,
        deployable_capital_snapshot_id=approval.deployable_capital_snapshot_id,
        intended_order_quantity_id=approval.intended_order_quantity_id,
        capital_gate_evaluated_at=approval.capital_gate_evaluated_at,
        approved_capital=str(approval.approved_capital),
        currency=approval.currency,
        founder_id=approval.founder_id,
        requested_at=approval.requested_at,
        approved_at=approval.approved_at,
        admitted_at=approval.admitted_at,
        committed_at=receipt.committed_at,
        approval_schema_version=approval.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/real-money-execution-intents",
    response_model=RealMoneyExecutionIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_real_money_execution_intent(
    opportunity_id: str,
    request: RealMoneyExecutionIntentRequest,
    response: Response,
    entry: RealMoneyExecutionIntentProductionEntry = Depends(
        get_real_money_execution_intent_entry
    ),
) -> RealMoneyExecutionIntentResponse:
    try:
        publication = entry.execute(
            RealMoneyExecutionIntentProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                founder_capital_approval_id=request.founder_capital_approval_id,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                current_deployable_capital_snapshot_id=(
                    request.current_deployable_capital_snapshot_id
                ),
                execution_quantity=request.execution_quantity,
                execution_quantity_unit=request.execution_quantity_unit,
                planned_execution_amount=(Decimal(request.planned_execution_amount) if request.planned_execution_amount is not None else None),
                currency=request.currency,
                founder_id=request.founder_id,
                current_execution_confirmed=request.current_execution_confirmed,
                confirmed_at=request.confirmed_at,
                requested_at=request.requested_at,
                contract_version=request.contract_version,
                proposed_supplier_order_committed_amount=(Decimal(request.proposed_supplier_order_committed_amount) if request.proposed_supplier_order_committed_amount is not None else None),
                supplier_order_currency=request.supplier_order_currency,
                supplier_order_checkout_evidence_reference=request.supplier_order_checkout_evidence_reference,
            )
        )
    except RealMoneyExecutionIntentSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        RealMoneyExecutionIntentReplayConflictError,
        RealMoneyExecutionIntentReadyConflictError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RealMoneyExecutionIntentPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (RealMoneyExecutionIntentPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Real-Money Execution Intent persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    intent, receipt = publication.intent, publication.receipt
    manifest = intent.source_manifest
    identity = manifest.opportunity_identity
    return RealMoneyExecutionIntentResponse(
        contract_version=manifest.policy_version,
        command_id=receipt.command_id,
        intent_id=intent.intent_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        founder_capital_approval_id=manifest.founder_capital_approval_id,
        capital_gate_id=manifest.capital_gate_id,
        capital_requirement_id=manifest.capital_requirement_id,
        intended_order_quantity_id=manifest.intended_order_quantity_id,
        sourcing_admission_id=manifest.sourcing_admission_id,
        sourcing_admission_revision=manifest.sourcing_admission_revision,
        quote_id=manifest.quote_id,
        quote_revision=manifest.quote_revision,
        current_deployable_capital_snapshot_id=(
            manifest.current_deployable_capital_snapshot_id
        ),
        execution_quantity=manifest.execution_quantity,
        execution_quantity_unit=manifest.execution_quantity_unit,
        planned_execution_amount=(str(manifest.planned_execution_amount) if manifest.planned_execution_amount is not None else None),
        currency=manifest.currency,
        authorized_acquisition_capital_amount=(str(manifest.authorized_acquisition_capital_amount) if manifest.authorized_acquisition_capital_amount is not None else None),
        authorized_acquisition_capital_currency=manifest.authorized_acquisition_capital_currency,
        proposed_supplier_order_committed_amount=(str(manifest.proposed_supplier_order_committed_amount) if manifest.proposed_supplier_order_committed_amount is not None else None),
        supplier_order_currency=manifest.supplier_order_currency,
        supplier_order_checkout_evidence_reference=manifest.supplier_order_checkout_evidence_reference,
        founder_id=manifest.founder_id,
        current_execution_confirmed=manifest.current_execution_confirmed,
        confirmed_at=manifest.confirmed_at,
        state=intent.state.value,
        blocking_reasons=tuple(value.value for value in intent.blocking_reasons),
        policy_name=manifest.policy_name,
        policy_version=manifest.policy_version,
        requested_at=intent.requested_at,
        evaluated_at=intent.evaluated_at,
        committed_at=receipt.committed_at,
        source_manifest_schema_version=manifest.schema_version,
        intent_schema_version=intent.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/purchase-execution-records",
    response_model=PurchaseExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_purchase_execution(
    opportunity_id: str,
    request: PurchaseExecutionRequest,
    response: Response,
    entry: PurchaseExecutionProductionEntry = Depends(get_purchase_execution_entry),
) -> PurchaseExecutionResponse:
    try:
        publication = entry.execute(
            PurchaseExecutionProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                real_money_execution_intent_id=(
                    request.real_money_execution_intent_id
                ),
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                actual_quantity=request.actual_quantity,
                actual_quantity_unit=request.actual_quantity_unit,
                actual_total_committed_amount=(Decimal(request.actual_total_committed_amount) if request.actual_total_committed_amount is not None else None),
                currency=request.currency,
                external_order_reference=request.external_order_reference,
                founder_id=request.founder_id,
                executed_at=request.executed_at,
                evidence_references=tuple(
                    PurchaseExecutionEvidenceReference(
                        reference=value.reference,
                        observed_at=value.observed_at,
                    )
                    for value in request.evidence_references
                ),
                requested_at=request.requested_at,
                contract_version=request.contract_version,
                supplier_order_committed_amount=(Decimal(request.supplier_order_committed_amount) if request.supplier_order_committed_amount is not None else None),
                supplier_order_currency=request.supplier_order_currency,
            )
        )
    except PurchaseExecutionSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        PurchaseExecutionReplayConflictError,
        PurchaseExecutionCardinalityConflictError,
        PurchaseExecutionExactMatchError,
        PurchaseExecutionIntentStateError,
        CapitalProductionOpportunityConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (PurchaseExecutionPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Purchase Execution persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    record, receipt = publication.record, publication.receipt
    manifest = record.source_manifest
    identity = manifest.opportunity_identity
    return PurchaseExecutionResponse(
        contract_version=record.policy_version,
        command_id=receipt.command_id,
        record_id=record.record_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        real_money_execution_intent_id=manifest.real_money_execution_intent_id,
        founder_capital_approval_id=manifest.founder_capital_approval_id,
        capital_gate_id=manifest.capital_gate_id,
        capital_requirement_id=manifest.capital_requirement_id,
        intended_order_quantity_id=manifest.intended_order_quantity_id,
        sourcing_admission_id=manifest.sourcing_admission_id,
        sourcing_admission_revision=manifest.sourcing_admission_revision,
        supplier_id=manifest.supplier_id,
        source_platform=manifest.source_platform,
        external_supplier_reference=manifest.external_supplier_reference,
        sourcing_product_id=manifest.sourcing_product_id,
        external_product_reference=manifest.external_product_reference,
        option_reference=manifest.option_reference,
        sku_reference=manifest.sku_reference,
        quote_id=manifest.quote_id,
        quote_revision=manifest.quote_revision,
        current_deployable_capital_snapshot_id=(
            manifest.current_deployable_capital_snapshot_id
        ),
        actual_quantity=record.actual_quantity,
        actual_quantity_unit=record.actual_quantity_unit,
        actual_total_committed_amount=(str(record.actual_total_committed_amount) if record.actual_total_committed_amount is not None else None),
        currency=record.currency,
        authorized_acquisition_capital_amount=(str(manifest.authorized_acquisition_capital_amount) if manifest.authorized_acquisition_capital_amount is not None else None),
        authorized_acquisition_capital_currency=manifest.authorized_acquisition_capital_currency,
        proposed_supplier_order_committed_amount=(str(manifest.proposed_supplier_order_committed_amount) if manifest.proposed_supplier_order_committed_amount is not None else None),
        proposed_supplier_order_currency=manifest.supplier_order_currency,
        supplier_order_committed_amount=(str(record.supplier_order_committed_amount) if record.supplier_order_committed_amount is not None else None),
        supplier_order_currency=record.supplier_order_currency,
        external_order_reference=record.external_order_reference,
        founder_id=record.founder_id,
        executed_at=record.executed_at,
        evidence_references=tuple(
            PurchaseExecutionEvidenceResponse(
                reference=value.reference,
                observed_at=value.observed_at,
                schema_version=value.schema_version,
            )
            for value in record.evidence_references
        ),
        execution_intent_evaluated_at=manifest.execution_intent_evaluated_at,
        execution_safety_policy_name=manifest.execution_safety_policy_name,
        execution_safety_policy_version=manifest.execution_safety_policy_version,
        policy_name=record.policy_name,
        policy_version=record.policy_version,
        requested_at=record.requested_at,
        admitted_at=record.admitted_at,
        committed_at=receipt.committed_at,
        source_manifest_schema_version=manifest.schema_version,
        record_schema_version=record.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/goods-receipts",
    response_model=GoodsReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_goods_receipt(
    opportunity_id: str,
    request: GoodsReceiptRequest,
    response: Response,
    entry: GoodsReceiptProductionEntry = Depends(get_goods_receipt_entry),
) -> GoodsReceiptResponse:
    try:
        publication = entry.execute(
            GoodsReceiptProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                purchase_execution_record_id=request.purchase_execution_record_id,
                received_quantity=request.received_quantity,
                quantity_unit=request.quantity_unit,
                sellable_quantity=request.sellable_quantity,
                damaged_quantity=request.damaged_quantity,
                evidence_references=tuple(
                    GoodsReceiptEvidenceReference(
                        reference=value.reference,
                        observed_at=value.observed_at,
                        operator_id=value.operator_id,
                        collection_method=value.collection_method,
                    )
                    for value in request.evidence_references
                ),
                delivery_reference=request.delivery_reference,
                operator_id=request.operator_id,
                received_at=request.received_at,
                inspected_at=request.inspected_at,
                requested_at=request.requested_at,
            )
        )
    except GoodsReceiptSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        GoodsReceiptCumulativeQuantityConflictError,
        GoodsReceiptOpportunityConflictError,
        GoodsReceiptReplayConflictError,
        GoodsReceiptSourceLineageError,
        GoodsReceiptUnitConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (GoodsReceiptPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Goods Receipt persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    record, receipt = publication.record, publication.receipt
    manifest = record.source_manifest
    identity = manifest.opportunity_identity
    return GoodsReceiptResponse(
        command_id=receipt.command_id,
        record_id=record.record_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        purchase_execution_record_id=manifest.purchase_execution_record_id,
        real_money_execution_intent_id=manifest.real_money_execution_intent_id,
        sourcing_admission_id=manifest.sourcing_admission_id,
        sourcing_admission_revision=manifest.sourcing_admission_revision,
        supplier_id=manifest.supplier_id,
        source_platform=manifest.source_platform,
        external_supplier_reference=manifest.external_supplier_reference,
        sourcing_product_id=manifest.sourcing_product_id,
        external_product_reference=manifest.external_product_reference,
        option_reference=manifest.option_reference,
        sku_reference=manifest.sku_reference,
        quote_id=manifest.quote_id,
        quote_revision=manifest.quote_revision,
        executed_quantity=manifest.executed_quantity,
        executed_quantity_unit=manifest.executed_quantity_unit,
        external_order_reference=manifest.external_order_reference,
        founder_id=manifest.founder_id,
        purchase_executed_at=manifest.purchase_executed_at,
        received_quantity=record.received_quantity,
        quantity_unit=record.quantity_unit,
        sellable_quantity=record.sellable_quantity,
        damaged_quantity=record.damaged_quantity,
        evidence_references=tuple(
            GoodsReceiptEvidenceResponse(
                reference=value.reference,
                observed_at=value.observed_at,
                operator_id=value.operator_id,
                collection_method=value.collection_method,
                schema_version=value.schema_version,
            )
            for value in record.evidence_references
        ),
        delivery_reference=record.delivery_reference,
        operator_id=record.operator_id,
        received_at=record.received_at,
        inspected_at=record.inspected_at,
        requested_at=record.requested_at,
        admitted_at=record.admitted_at,
        committed_at=receipt.committed_at,
        policy_name=record.policy_name,
        policy_version=record.policy_version,
        source_manifest_schema_version=manifest.schema_version,
        record_schema_version=record.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


def _owned_inventory_position_response(position) -> OwnedInventoryPositionResponse:
    key = position.product_key
    identity = key.opportunity_identity
    return OwnedInventoryPositionResponse(
        product_key=OwnedInventoryProductKeyResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            source_platform=key.source_platform,
            supplier_id=key.supplier_id,
            sourcing_product_id=key.sourcing_product_id,
            external_product_reference=key.external_product_reference,
            option_reference=key.option_reference,
            sku_reference=key.sku_reference,
            quantity_unit=key.quantity_unit,
        ),
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        quantity_unit=position.quantity_unit,
        total_received=position.total_received,
        total_sellable_received=position.total_sellable_received,
        total_damaged_received=position.total_damaged_received,
        total_outbound_quantity=position.total_outbound_quantity,
        sellable_on_hand=position.sellable_on_hand,
        contributing_purchase_execution_ids=(
            position.contributing_purchase_execution_ids
        ),
        contributing_goods_receipt_ids=position.contributing_goods_receipt_ids,
        contributing_actual_sale_settlement_ids=(
            position.contributing_actual_sale_settlement_ids
        ),
        source_event_count=position.inbound_source_event_count,
        inbound_source_event_count=position.inbound_source_event_count,
        outbound_source_event_count=position.outbound_source_event_count,
        policy_name=position.policy_name,
        policy_version=position.policy_version,
        schema_version=position.schema_version,
    )


@app.get(
    "/api/v1/opportunities/{opportunity_id}/owned-inventory",
    response_model=OwnedInventoryResponse,
)
def get_owned_inventory(
    opportunity_id: str,
    query: GetOwnedInventoryPositionsV2 = Depends(get_owned_inventory_query),
) -> OwnedInventoryResponse:
    try:
        positions = query.execute(opportunity_id)
    except OwnedInventoryOpportunityNotFoundError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except OwnedInventorySourceConflictError as error:
        raise HTTPException(
            status_code=409, detail="Owned Inventory source conflict"
        ) from error
    except (
        GoodsReceiptPersistenceError,
        ActualSaleSettlementPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="Owned Inventory persistence unavailable",
        ) from error
    return OwnedInventoryResponse(
        opportunity_id=opportunity_id,
        positions=tuple(
            _owned_inventory_position_response(position) for position in positions
        ),
        position_count=len(positions),
    )


def _actual_acquisition_evidence(
    value: ActualAcquisitionEvidenceRequest,
) -> ActualAcquisitionEvidenceReference:
    return ActualAcquisitionEvidenceReference(
        reference=value.reference,
        observed_at=value.observed_at,
        operator_id=value.operator_id,
        collection_method=value.collection_method,
    )


def _actual_acquisition_fx(
    value: ActualAcquisitionFXRequest | None,
) -> ActualAcquisitionFXSettlement | None:
    if value is None:
        return None
    return ActualAcquisitionFXSettlement(
        source_currency=value.source_currency,
        target_currency=value.target_currency,
        original_amount=Decimal(value.original_amount),
        target_amount=(
            None if value.target_amount is None else Decimal(value.target_amount)
        ),
        applied_rate=(
            None if value.applied_rate is None else Decimal(value.applied_rate)
        ),
        provider=value.provider,
        payment_channel=value.payment_channel,
        external_reference=value.external_reference,
        settled_at=value.settled_at,
        evidence=_actual_acquisition_evidence(value.evidence),
    )


def _actual_acquisition_fact(
    value: ActualAcquisitionFixedCostRequest,
) -> ActualAcquisitionCostFact:
    return ActualAcquisitionCostFact(
        category=ActualAcquisitionCostCategory(value.category),
        availability=ActualAcquisitionFactAvailability(value.availability),
        amount=None if value.amount is None else Decimal(value.amount),
        currency=value.currency,
        settled_at=value.settled_at,
        evidence=(
            None
            if value.evidence is None
            else _actual_acquisition_evidence(value.evidence)
        ),
        unresolved_reason=value.unresolved_reason,
        actual_fx=_actual_acquisition_fx(value.actual_fx),
    )


def _actual_acquisition_other_item(
    value: OtherMandatoryAcquisitionCostItemRequest,
) -> OtherMandatoryAcquisitionCostItem:
    return OtherMandatoryAcquisitionCostItem(
        scope=value.scope,
        amount=Decimal(value.amount),
        currency=value.currency,
        settled_at=value.settled_at,
        evidence=_actual_acquisition_evidence(value.evidence),
        actual_fx=_actual_acquisition_fx(value.actual_fx),
    )


def _actual_evidence_response(value):
    if value is None:
        return None
    return ActualAcquisitionEvidenceResponse(
        reference=value.reference,
        observed_at=value.observed_at,
        operator_id=value.operator_id,
        collection_method=value.collection_method,
        schema_version=value.schema_version,
    )


def _actual_fx_response(value):
    if value is None:
        return None
    return ActualAcquisitionFXResponse(
        source_currency=value.source_currency,
        target_currency=value.target_currency,
        original_amount=str(value.original_amount),
        target_amount=None if value.target_amount is None else str(value.target_amount),
        applied_rate=None if value.applied_rate is None else str(value.applied_rate),
        normalized_target_amount=str(value.normalized_target_amount),
        provider=value.provider,
        payment_channel=value.payment_channel,
        external_reference=value.external_reference,
        settled_at=value.settled_at,
        evidence=_actual_evidence_response(value.evidence),
        schema_version=value.schema_version,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/actual-acquisition-settlements",
    response_model=ActualAcquisitionSettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_actual_acquisition_settlement(
    opportunity_id: str,
    request: ActualAcquisitionSettlementRequest,
    response: Response,
    entry: ActualAcquisitionSettlementProductionEntry = Depends(
        get_actual_acquisition_settlement_entry
    ),
) -> ActualAcquisitionSettlementResponse:
    try:
        other_request = request.other_mandatory_costs
        publication = entry.execute(
            ActualAcquisitionSettlementProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                purchase_execution_record_id=request.purchase_execution_record_id,
                predecessor_settlement_id=request.predecessor_settlement_id,
                target_currency=request.target_currency,
                fixed_cost_facts=tuple(
                    _actual_acquisition_fact(value)
                    for value in request.fixed_cost_facts
                ),
                other_mandatory_costs=OtherMandatoryAcquisitionCosts(
                    availability=ActualAcquisitionFactAvailability(
                        other_request.availability
                    ),
                    items=tuple(
                        _actual_acquisition_other_item(value)
                        for value in other_request.items
                    ),
                    scope_evidence=(
                        None
                        if other_request.scope_evidence is None
                        else _actual_acquisition_evidence(
                            other_request.scope_evidence
                        )
                    ),
                    unresolved_reason=other_request.unresolved_reason,
                ),
                operator_id=request.operator_id,
                requested_at=request.requested_at,
            )
        )
    except ActualAcquisitionSettlementSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ActualAcquisitionSettlementOpportunityConflictError,
        ActualAcquisitionSettlementReplayConflictError,
        ActualAcquisitionSettlementRevisionConflictError,
        ActualAcquisitionSettlementTerminalConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ActualAcquisitionSettlementPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Actual Acquisition Settlement persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK

    settlement, receipt = publication.settlement, publication.receipt
    manifest = settlement.source_manifest
    identity = manifest.opportunity_identity
    return ActualAcquisitionSettlementResponse(
        command_id=receipt.command_id,
        settlement_id=settlement.settlement_id,
        revision=settlement.revision,
        predecessor_settlement_id=settlement.predecessor_settlement_id,
        opportunity_id=identity.opportunity_id,
        discovery_reference=identity.discovery_reference,
        purchase_execution_record_id=manifest.purchase_execution_record_id,
        real_money_execution_intent_id=manifest.real_money_execution_intent_id,
        founder_capital_approval_id=manifest.founder_capital_approval_id,
        capital_gate_id=manifest.capital_gate_id,
        capital_requirement_id=manifest.capital_requirement_id,
        intended_order_quantity_id=manifest.intended_order_quantity_id,
        sourcing_admission_id=manifest.sourcing_admission_id,
        sourcing_admission_revision=manifest.sourcing_admission_revision,
        supplier_id=manifest.supplier_id,
        source_platform=manifest.source_platform,
        external_supplier_reference=manifest.external_supplier_reference,
        sourcing_product_id=manifest.sourcing_product_id,
        external_product_reference=manifest.external_product_reference,
        option_reference=manifest.option_reference,
        sku_reference=manifest.sku_reference,
        quote_id=manifest.quote_id,
        quote_revision=manifest.quote_revision,
        executed_quantity=manifest.executed_quantity,
        executed_quantity_unit=manifest.executed_quantity_unit,
        external_order_reference=manifest.external_order_reference,
        purchase_executed_at=manifest.purchase_executed_at,
        target_currency=settlement.target_currency,
        state=settlement.state.value,
        blocking_reasons=tuple(value.value for value in settlement.blocking_reasons),
        fixed_cost_facts=tuple(
            ActualAcquisitionFixedCostResponse(
                category=value.category.value,
                availability=value.availability.value,
                amount=None if value.amount is None else str(value.amount),
                currency=value.currency,
                settled_at=value.settled_at,
                evidence=_actual_evidence_response(value.evidence),
                unresolved_reason=value.unresolved_reason,
                actual_fx=_actual_fx_response(value.actual_fx),
            )
            for value in settlement.fixed_cost_facts
        ),
        other_mandatory_costs=OtherMandatoryAcquisitionCostsResponse(
            availability=settlement.other_mandatory_costs.availability.value,
            items=tuple(
                OtherMandatoryAcquisitionCostItemResponse(
                    scope=value.scope,
                    amount=str(value.amount),
                    currency=value.currency,
                    settled_at=value.settled_at,
                    evidence=_actual_evidence_response(value.evidence),
                    actual_fx=_actual_fx_response(value.actual_fx),
                )
                for value in settlement.other_mandatory_costs.items
            ),
            scope_evidence=_actual_evidence_response(
                settlement.other_mandatory_costs.scope_evidence
            ),
            unresolved_reason=settlement.other_mandatory_costs.unresolved_reason,
        ),
        normalized_categories=tuple(
            NormalizedActualAcquisitionCategoryResponse(
                category=value.category.value,
                target_currency=value.target_currency,
                target_batch_amount=(
                    None
                    if value.target_batch_amount is None
                    else str(value.target_batch_amount)
                ),
            )
            for value in settlement.normalized_categories
        ),
        acquisition_batch_total=(
            None
            if settlement.acquisition_batch_total is None
            else str(settlement.acquisition_batch_total)
        ),
        acquisition_per_unit=(
            None
            if settlement.acquisition_per_unit is None
            else str(settlement.acquisition_per_unit)
        ),
        operator_id=settlement.operator_id,
        policy_name=settlement.policy_name,
        policy_version=settlement.policy_version,
        policy_precision=settlement.policy_precision,
        policy_rounding=settlement.policy_rounding,
        requested_at=settlement.requested_at,
        admitted_at=settlement.admitted_at,
        committed_at=receipt.committed_at,
        source_manifest_schema_version=manifest.schema_version,
        settlement_schema_version=settlement.schema_version,
        receipt_schema_version=receipt.schema_version,
        replayed=publication.replayed,
    )


def _actual_sale_evidence(value):
    if value is None:
        return None
    return ActualSaleEvidenceReference(
        value.reference, value.observed_at, value.operator_id, value.collection_method
    )


def _actual_sale_fact(value: ActualSaleMonetaryFactRequest):
    return ActualSaleMonetaryFact(
        ActualSaleMonetaryCategory(value.category),
        ActualSaleFactAvailability(value.availability),
        None if value.amount is None else Decimal(value.amount),
        value.currency,
        value.occurred_at,
        _actual_sale_evidence(value.evidence),
        value.unresolved_reason,
    )


def _actual_sale_evidence_response(value):
    if value is None:
        return None
    return ActualSaleEvidenceResponse(
        reference=value.reference,
        observed_at=value.observed_at,
        operator_id=value.operator_id,
        collection_method=value.collection_method,
        schema_version=value.schema_version,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/actual-sale-settlements",
    response_model=ActualSaleSettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_actual_sale_settlement(
    opportunity_id: str,
    request: ActualSaleSettlementRequest,
    response: Response,
    entry: ActualSaleSettlementProductionEntry = Depends(
        get_actual_sale_settlement_entry
    ),
) -> ActualSaleSettlementResponse:
    try:
        other = request.other_sale_side_costs
        payout = request.payout
        finality = request.finality
        publication = entry.execute(
            ActualSaleSettlementProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                anchor_goods_receipt_id=request.anchor_goods_receipt_id,
                predecessor_settlement_id=request.predecessor_settlement_id,
                marketplace=request.marketplace,
                seller_account_reference=request.seller_account_reference,
                marketplace_product_reference=request.marketplace_product_reference,
                marketplace_option_reference=request.marketplace_option_reference,
                marketplace_sku_reference=request.marketplace_sku_reference,
                external_report_reference=request.external_report_reference,
                transaction_references=request.transaction_references,
                period_start=request.period_start,
                period_end=request.period_end,
                fulfilled_outbound_quantity=request.fulfilled_outbound_quantity,
                cancelled_quantity=request.cancelled_quantity,
                refunded_quantity=request.refunded_quantity,
                returned_quantity=request.returned_quantity,
                quantity_unit=request.quantity_unit,
                settlement_currency=request.settlement_currency,
                fixed_monetary_facts=tuple(
                    _actual_sale_fact(value) for value in request.fixed_monetary_facts
                ),
                other_sale_side_costs=OtherActualSaleCosts(
                    ActualSaleFactAvailability(other.availability),
                    tuple(
                        OtherActualSaleCostItem(
                            value.scope,
                            Decimal(value.amount),
                            value.currency,
                            value.occurred_at,
                            _actual_sale_evidence(value.evidence),
                        )
                        for value in other.items
                    ),
                    _actual_sale_evidence(other.scope_evidence),
                    other.unresolved_reason,
                ),
                payout=ActualSalePayoutFact(
                    ActualSaleFactAvailability(payout.availability),
                    None if payout.amount is None else Decimal(payout.amount),
                    payout.currency,
                    payout.external_reference,
                    payout.paid_at,
                    _actual_sale_evidence(payout.evidence),
                    payout.unresolved_reason,
                    ActualSalePayoutReconciliationState(
                        payout.reconciliation_state
                    ),
                    payout.reconciliation_explanation,
                    _actual_sale_evidence(payout.reconciliation_evidence),
                ),
                finality=ActualSaleFinalityFact(
                    finality.confirmed,
                    finality.observed_at,
                    _actual_sale_evidence(finality.evidence),
                    finality.unresolved_reason,
                ),
                operator_id=request.operator_id,
                requested_at=request.requested_at,
            )
        )
    except ActualSaleSettlementSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ActualSaleSettlementOpportunityConflictError,
        ActualSaleSettlementOversellConflictError,
        ActualSaleSettlementProductConflictError,
        ActualSaleSettlementReplayConflictError,
        ActualSaleSettlementReportConflictError,
        ActualSaleSettlementRevisionConflictError,
        ActualSaleSettlementSourceLineageError,
        ActualSaleSettlementTerminalConflictError,
        ActualSaleSettlementWindowConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ActualSaleSettlementPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Actual Sale Settlement persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    settlement, receipt = publication.settlement, publication.receipt
    manifest = settlement.source_manifest
    key = manifest.product_key
    identity = key.opportunity_identity
    facts = tuple(
        ActualSaleMonetaryFactResponse(
            category=value.category.value,
            availability=value.availability.value,
            amount=None if value.amount is None else str(value.amount),
            currency=value.currency,
            occurred_at=value.occurred_at,
            evidence=_actual_sale_evidence_response(value.evidence),
            unresolved_reason=value.unresolved_reason,
            schema_version=value.schema_version,
        )
        for value in settlement.fixed_monetary_facts
    )
    return ActualSaleSettlementResponse(
        command_id=receipt.command_id,
        settlement_id=settlement.settlement_id,
        revision=settlement.revision,
        predecessor_settlement_id=settlement.predecessor_settlement_id,
        product_key=OwnedInventoryProductKeyResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            source_platform=key.source_platform,
            supplier_id=key.supplier_id,
            sourcing_product_id=key.sourcing_product_id,
            external_product_reference=key.external_product_reference,
            option_reference=key.option_reference,
            sku_reference=key.sku_reference,
            quantity_unit=key.quantity_unit,
        ),
        anchor_goods_receipt_id=manifest.anchor_goods_receipt_id,
        eligible_goods_receipt_ids=manifest.eligible_goods_receipt_ids,
        contributing_purchase_execution_ids=manifest.contributing_purchase_execution_ids,
        marketplace=manifest.marketplace,
        seller_account_reference=manifest.seller_account_reference,
        marketplace_product_reference=manifest.marketplace_product_reference,
        marketplace_option_reference=manifest.marketplace_option_reference,
        marketplace_sku_reference=manifest.marketplace_sku_reference,
        external_report_reference=manifest.external_report_reference,
        transaction_references=manifest.transaction_references,
        period_start=settlement.period_start,
        period_end=settlement.period_end,
        fulfilled_outbound_quantity=settlement.fulfilled_outbound_quantity,
        cancelled_quantity=settlement.cancelled_quantity,
        refunded_quantity=settlement.refunded_quantity,
        returned_quantity=settlement.returned_quantity,
        quantity_unit=settlement.quantity_unit,
        settlement_currency=settlement.settlement_currency,
        fixed_monetary_facts=facts,
        other_sale_side_costs=OtherActualSaleCostsResponse(
            availability=settlement.other_sale_side_costs.availability.value,
            items=tuple(
                OtherActualSaleCostItemResponse(
                    scope=value.scope,
                    amount=str(value.amount),
                    currency=value.currency,
                    occurred_at=value.occurred_at,
                    evidence=_actual_sale_evidence_response(value.evidence),
                )
                for value in settlement.other_sale_side_costs.items
            ),
            scope_evidence=_actual_sale_evidence_response(
                settlement.other_sale_side_costs.scope_evidence
            ),
            unresolved_reason=settlement.other_sale_side_costs.unresolved_reason,
            schema_version=settlement.other_sale_side_costs.schema_version,
        ),
        payout=ActualSalePayoutResponse(
            availability=settlement.payout.availability.value,
            amount=None if settlement.payout.amount is None else str(settlement.payout.amount),
            currency=settlement.payout.currency,
            external_reference=settlement.payout.external_reference,
            paid_at=settlement.payout.paid_at,
            evidence=_actual_sale_evidence_response(settlement.payout.evidence),
            unresolved_reason=settlement.payout.unresolved_reason,
            reconciliation_state=settlement.payout.reconciliation_state.value,
            reconciliation_explanation=settlement.payout.reconciliation_explanation,
            reconciliation_evidence=_actual_sale_evidence_response(
                settlement.payout.reconciliation_evidence
            ),
            schema_version=settlement.payout.schema_version,
        ),
        finality=ActualSaleFinalityResponse(
            confirmed=settlement.finality.confirmed,
            observed_at=settlement.finality.observed_at,
            evidence=_actual_sale_evidence_response(settlement.finality.evidence),
            unresolved_reason=settlement.finality.unresolved_reason,
            schema_version=settlement.finality.schema_version,
        ),
        state=settlement.state.value,
        blocking_reasons=tuple(value.value for value in settlement.blocking_reasons),
        operator_id=settlement.operator_id,
        policy_name=settlement.policy_name,
        policy_version=settlement.policy_version,
        policy_precision=settlement.policy_precision,
        policy_rounding=settlement.policy_rounding,
        source_manifest_schema_version=manifest.schema_version,
        settlement_schema_version=settlement.schema_version,
        receipt_schema_version=receipt.schema_version,
        requested_at=settlement.requested_at,
        admitted_at=settlement.admitted_at,
        committed_at=receipt.committed_at,
        replayed=publication.replayed,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/actual-outcomes",
    response_model=ActualOutcomeResponse,
    status_code=status.HTTP_201_CREATED,
)
def calculate_actual_outcome(
    opportunity_id: str,
    request: ActualOutcomeRequest,
    response: Response,
    entry: ActualOutcomeProductionEntry = Depends(get_actual_outcome_entry),
) -> ActualOutcomeResponse:
    try:
        publication = entry.execute(
            ActualOutcomeProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                actual_acquisition_settlement_id=request.actual_acquisition_settlement_id,
                actual_sale_settlement_ids=request.actual_sale_settlement_ids,
                requested_at=request.requested_at,
            )
        )
    except ActualOutcomeSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ActualOutcomeOpportunityConflictError,
        ActualOutcomeReplayConflictError,
        ActualOutcomeSourceConflictError,
        ActualOutcomeSourceIntegrityError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        ActualOutcomePersistenceError,
        ActualAcquisitionSettlementPersistenceError,
        ActualSaleSettlementPersistenceError,
        GoodsReceiptPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="Actual Outcome persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if publication.replayed:
        response.status_code = status.HTTP_200_OK
    outcome, receipt = publication.outcome, publication.receipt
    manifest = outcome.source_manifest
    key = manifest.product_key
    identity = key.opportunity_identity

    def money(value):
        return None if value is None else str(value)

    return ActualOutcomeResponse(
        command_id=receipt.command_id,
        outcome_id=outcome.outcome_id,
        product_key=OwnedInventoryProductKeyResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            source_platform=key.source_platform,
            supplier_id=key.supplier_id,
            sourcing_product_id=key.sourcing_product_id,
            external_product_reference=key.external_product_reference,
            option_reference=key.option_reference,
            sku_reference=key.sku_reference,
            quantity_unit=key.quantity_unit,
        ),
        purchase_execution_record_id=manifest.purchase_execution_record_id,
        actual_acquisition_settlement_id=manifest.actual_acquisition_settlement_id,
        goods_receipt_ids=manifest.goods_receipt_ids,
        actual_sale_settlement_ids=manifest.actual_sale_settlement_ids,
        sale_windows=tuple(
            ActualOutcomeSaleWindowResponse(
                settlement_id=value.settlement_id,
                period_start=value.period_start,
                period_end=value.period_end,
            )
            for value in manifest.sale_windows
        ),
        state=outcome.state.value,
        inventory_resolution=outcome.inventory_resolution.value,
        blocking_reasons=tuple(value.value for value in outcome.blocking_reasons),
        executed_quantity=manifest.executed_quantity,
        received_quantity=manifest.received_quantity,
        sellable_received_quantity=manifest.sellable_received_quantity,
        damaged_quantity=manifest.damaged_quantity,
        sold_quantity=manifest.sold_quantity,
        remaining_sellable_quantity=manifest.remaining_sellable_quantity,
        returned_quantity=manifest.returned_quantity,
        unreceived_quantity=manifest.unreceived_quantity,
        quantity_unit=manifest.quantity_unit,
        currency=manifest.currency,
        acquisition_allocations=tuple(
            ActualOutcomeAcquisitionAllocationResponse(
                category=value.category.value,
                batch_amount=str(value.batch_amount),
                per_executed_unit=str(value.per_executed_unit),
                sold_cogs=str(value.sold_cogs),
                remaining_sellable_basis=str(value.remaining_sellable_basis),
                damaged_loss=str(value.damaged_loss),
                unreceived_exposure=str(value.unreceived_exposure),
            )
            for value in outcome.acquisition_allocations
        ),
        sale_components=tuple(
            ActualOutcomeSaleComponentResponse(
                category=value.category.value,
                amount=str(value.amount),
            )
            for value in outcome.sale_components
        ),
        other_sale_side_costs=money(outcome.other_sale_side_costs),
        acquisition_batch_total=money(outcome.acquisition_batch_total),
        actual_cogs=money(outcome.actual_cogs),
        remaining_sellable_inventory_cost_basis=money(outcome.remaining_sellable_inventory_cost_basis),
        damaged_acquisition_loss=money(outcome.damaged_acquisition_loss),
        unreceived_acquisition_cost_basis=money(outcome.unreceived_acquisition_cost_basis),
        gross_realized_merchandise_revenue=money(outcome.gross_realized_merchandise_revenue),
        recognized_sale_credits=money(outcome.recognized_sale_credits),
        recognized_sale_side_costs=money(outcome.recognized_sale_side_costs),
        net_realized_sale_contribution=money(outcome.net_realized_sale_contribution),
        actual_realized_profit=money(outcome.actual_realized_profit),
        actual_margin=ActualOutcomeMetricResponse(
            available=outcome.actual_margin.available,
            value=money(outcome.actual_margin.value),
        ),
        actual_acquisition_roi=ActualOutcomeMetricResponse(
            available=outcome.actual_acquisition_roi.available,
            value=money(outcome.actual_acquisition_roi.value),
        ),
        known_payout_total=money(outcome.known_payout_total),
        payout_reconciliation_states=outcome.payout_reconciliation_states,
        evaluation_start=manifest.evaluation_start,
        evaluation_through=manifest.evaluation_through,
        acquisition_policy_version=manifest.acquisition_policy_version,
        acquisition_schema_version=manifest.acquisition_schema_version,
        goods_receipt_policy_versions=manifest.goods_receipt_policy_versions,
        goods_receipt_schema_versions=manifest.goods_receipt_schema_versions,
        sale_policy_versions=manifest.sale_policy_versions,
        sale_schema_versions=manifest.sale_schema_versions,
        policy_name=outcome.policy_name,
        policy_version=outcome.policy_version,
        policy_precision=outcome.policy_precision,
        policy_rounding=outcome.policy_rounding,
        source_manifest_schema_version=manifest.schema_version,
        outcome_schema_version=outcome.schema_version,
        receipt_schema_version=receipt.schema_version,
        requested_at=outcome.requested_at,
        calculated_at=outcome.calculated_at,
        committed_at=outcome.committed_at,
        replayed=publication.replayed,
        aliased=publication.aliased,
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/economics-variances",
    response_model=ConservativeActualVarianceResponse,
    status_code=status.HTTP_201_CREATED,
)
def calculate_conservative_actual_variance(
    opportunity_id: str,
    request: ConservativeActualVarianceRequest,
    response: Response,
    entry: ConservativeActualVarianceProductionEntry = Depends(
        get_conservative_actual_variance_entry
    ),
) -> ConservativeActualVarianceResponse:
    try:
        publication = entry.execute(
            ConservativeActualVarianceProductionRequest(
                command_id=request.command_id,
                opportunity_id=opportunity_id,
                conservative_economics_result_id=request.conservative_economics_result_id,
                actual_outcome_id=request.actual_outcome_id,
                requested_at=request.requested_at,
            )
        )
    except ConservativeActualVarianceSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        ConservativeActualVarianceOpportunityConflictError,
        ConservativeActualVariancePolicyError,
        ConservativeActualVarianceReplayConflictError,
        ConservativeActualVarianceSourceConflictError,
        ConservativeActualVarianceSourceIntegrityError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        ConservativeActualVariancePersistenceError,
        ConservativeEconomicsPersistenceError,
        ActualOutcomePersistenceError,
        EconomicsSourceCompositionPersistenceError,
        AcquisitionCostNormalizationPersistenceError,
        LandedCostCompositionPersistenceError,
        SourcingEconomicsBindingPersistenceError,
        SourcingAuthorityPersistenceError,
        PlannedAcquisitionCapitalRequirementPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="Conservative Actual Variance persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if publication.replayed or publication.aliased:
        response.status_code = status.HTTP_200_OK
    variance, receipt = publication.variance, publication.receipt
    manifest = variance.source_manifest
    key = manifest.product_key
    identity = key.opportunity_identity

    def decimal_text(value):
        return None if value is None else str(value)

    def metric_response(value):
        return ConservativeActualVarianceMetricResponse(
            metric_name=value.metric_name,
            direction=value.direction.value,
            comparability=value.comparability.value,
            predicted_value=decimal_text(value.predicted_value),
            actual_value=decimal_text(value.actual_value),
            variance=decimal_text(value.variance),
            relative_variance_percent=decimal_text(value.relative_variance_percent),
            variance_percentage_points=decimal_text(value.variance_percentage_points),
            favorability=value.favorability.value,
            unit=value.unit,
            currency=value.currency,
            reason_codes=value.reason_codes,
            predicted_scope_total=decimal_text(value.predicted_scope_total),
            actual_scope_total=decimal_text(value.actual_scope_total),
            scope_total_variance=decimal_text(value.scope_total_variance),
        )

    return ConservativeActualVarianceResponse(
        command_id=receipt.command_id,
        variance_id=variance.variance_id,
        product_key=OwnedInventoryProductKeyResponse(
            opportunity_id=identity.opportunity_id,
            discovery_reference=identity.discovery_reference,
            source_platform=key.source_platform,
            supplier_id=key.supplier_id,
            sourcing_product_id=key.sourcing_product_id,
            external_product_reference=key.external_product_reference,
            option_reference=key.option_reference,
            sku_reference=key.sku_reference,
            quantity_unit=key.quantity_unit,
        ),
        conservative_economics_result_id=manifest.conservative_result_id,
        actual_outcome_id=manifest.actual_outcome_id,
        comparison_state=variance.comparison_state.value,
        calibration_eligibility=variance.calibration_eligibility.value,
        calibration_reasons=tuple(value.value for value in variance.calibration_reasons),
        core_metrics=tuple(metric_response(value) for value in variance.core_metrics),
        acquisition_component_metrics=tuple(
            metric_response(value) for value in variance.acquisition_component_metrics
        ),
        actual_only_contributors=tuple(
            ConservativeActualVarianceContributorResponse(
                category=value.category,
                amount=str(value.amount),
                currency=value.currency,
                classification=value.classification.value,
                source_references=value.source_references,
            )
            for value in variance.actual_only_contributors
        ),
        predicted_only_context=tuple(
            ConservativeActualPredictedContextResponse(
                category=value.category,
                predicted_value=str(value.predicted_value),
                currency=value.currency,
                classification=value.classification.value,
                source_reference=value.source_reference,
            )
            for value in variance.predicted_only_context
        ),
        exposure_context=ConservativeActualExposureContextResponse(
            remaining_sellable_quantity=variance.exposure_context.remaining_sellable_quantity,
            remaining_inventory_cost_basis=str(variance.exposure_context.remaining_inventory_cost_basis),
            unreceived_quantity=variance.exposure_context.unreceived_quantity,
            unreceived_acquisition_basis=str(variance.exposure_context.unreceived_acquisition_basis),
            damaged_quantity=variance.exposure_context.damaged_quantity,
            damaged_acquisition_loss=str(variance.exposure_context.damaged_acquisition_loss),
            returned_quantity=variance.exposure_context.returned_quantity,
            inventory_resolution=variance.exposure_context.inventory_resolution.value,
            quantity_unit=variance.exposure_context.quantity_unit,
            currency=variance.exposure_context.currency,
        ),
        scenario_context=ConservativeActualScenarioContextResponse(
            scenario_name=variance.scenario_context.scenario_name,
            scenario_version=variance.scenario_context.scenario_version,
            sale_price_factor=str(variance.scenario_context.sale_price_factor),
            assumption_owner=variance.scenario_context.assumption_owner,
            conservative_policy_name=variance.scenario_context.conservative_policy_name,
            conservative_policy_version=variance.scenario_context.conservative_policy_version,
        ),
        actual_scope_context=ConservativeActualScopeContextResponse(
            sold_quantity=variance.actual_scope_context.sold_quantity,
            executed_quantity=variance.actual_scope_context.executed_quantity,
            inventory_resolution=variance.actual_scope_context.inventory_resolution.value,
            sale_windows=tuple(
                ActualOutcomeSaleWindowResponse(
                    settlement_id=value.settlement_id,
                    period_start=value.period_start,
                    period_end=value.period_end,
                )
                for value in variance.actual_scope_context.sale_windows
            ),
            remaining_sellable_quantity=variance.actual_scope_context.remaining_sellable_quantity,
            damaged_quantity=variance.actual_scope_context.damaged_quantity,
            returned_quantity=variance.actual_scope_context.returned_quantity,
            unreceived_quantity=variance.actual_scope_context.unreceived_quantity,
            quantity_unit=variance.actual_scope_context.quantity_unit,
        ),
        source_composition_id=manifest.source_composition_id,
        acquisition_normalization_id=manifest.acquisition_normalization_id,
        landed_cost_composition_id=manifest.landed_cost_composition_id,
        sourcing_binding_id=manifest.sourcing_binding_id,
        sourcing_admission_id=manifest.sourcing_admission_id,
        sourcing_admission_revision=manifest.sourcing_admission_revision,
        quote_id=manifest.quote_id,
        quote_revision=manifest.quote_revision,
        purchase_execution_record_id=manifest.purchase_execution_record_id,
        actual_acquisition_settlement_id=manifest.actual_acquisition_settlement_id,
        actual_sale_settlement_ids=manifest.actual_sale_settlement_ids,
        currency=manifest.currency,
        conservative_policy_name=manifest.conservative_policy_name,
        conservative_policy_version=manifest.conservative_policy_version,
        conservative_schema_version=manifest.conservative_schema_version,
        actual_policy_name=manifest.actual_policy_name,
        actual_policy_version=manifest.actual_policy_version,
        actual_schema_version=manifest.actual_schema_version,
        source_manifest_schema_version=manifest.schema_version,
        conservative_calculated_at=manifest.conservative_calculated_at,
        purchase_executed_at=manifest.purchase_executed_at,
        hindsight_eligible=manifest.conservative_calculated_at < manifest.purchase_executed_at,
        policy_name=variance.policy_name,
        policy_version=variance.policy_version,
        policy_precision=variance.policy_precision,
        policy_rounding=variance.policy_rounding,
        variance_schema_version=variance.schema_version,
        receipt_schema_version=receipt.schema_version,
        requested_at=variance.requested_at,
        calculated_at=variance.calculated_at,
        committed_at=variance.committed_at,
        replayed=publication.replayed,
        aliased=publication.aliased,
    )


@app.post(
    "/api/v1/snapshot-chains",
    response_model=SnapshotChainResponse,
    status_code=status.HTTP_201_CREATED,
)
def bind_opportunity_snapshot_chain(
    request: SnapshotChainRequest,
    response: Response,
    entry: CompleteSnapshotChainProductionEntry = Depends(
        get_snapshot_chain_entry
    ),
) -> SnapshotChainResponse:
    try:
        result = entry.execute(request.to_application_request())
    except (
        SnapshotChainBindingNotFoundError,
        SnapshotChainIncompleteError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        SnapshotChainBindingCommandConflictError,
        SnapshotChainBindingConflictError,
        SnapshotChainCandidateMismatchError,
        SnapshotChainEconomicsSourceConflictError,
        SnapshotChainMarketIdentityConflictError,
        SnapshotChainOpportunityMismatchError,
        SnapshotChainPriceSourceConflictError,
        SnapshotChainProductSourceConflictError,
        SnapshotChainVerifiedSourceConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SnapshotChainBindingPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="snapshot chain persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    binding = result.binding
    receipt = result.receipt
    aliased = binding.binding_command_id != receipt.command_id
    if result.replayed or aliased:
        response.status_code = status.HTTP_200_OK
    identity = binding.market_observation_identity
    return SnapshotChainResponse(
        command_id=receipt.command_id,
        binding_id=binding.binding_id,
        candidate_opportunity_binding_id=(
            binding.candidate_opportunity_binding_id
        ),
        candidate_id=binding.candidate_id,
        opportunity_id=binding.opportunity_id,
        chain_version=binding.chain_version,
        product_snapshot_ids=binding.product_snapshot_ids,
        price_snapshot_id=binding.price_snapshot_id,
        economics_snapshot_id=binding.economics_snapshot_id,
        verified_economics_opportunity_id=(
            binding.verified_economics_opportunity_id
        ),
        market_observation_identity=MarketObservationIdentityRequest(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        requested_at=receipt.requested_at,
        bound_at=binding.bound_at,
        committed_at=receipt.committed_at,
        replayed=result.replayed,
        aliased=aliased,
    )


@app.get("/api/v1/opportunities/{opportunity_id}/decision-dashboard")
def get_opportunity_decision_dashboard(
    opportunity_id: str,
    provider=Depends(get_opportunity_decision_dashboard_provider),
) -> dict[str, object]:
    try:
        response = GetOpportunityDecisionDashboard(provider).execute(opportunity_id)
    except DashboardDecisionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DashboardDecisionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DashboardDecisionUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return response.to_dict()


@app.get("/api/v1/reviews")
def list_review_sessions(
    query_service: ReviewSessionQueryService = Depends(get_review_session_query_service),
) -> dict[str, object]:
    try:
        sessions = query_service.list(ListReviewSessions())
        items = tuple(ReviewSessionResponseDTO.from_session(value) for value in sessions)
        return ReviewSessionListResponseDTO(items, len(items)).to_dict()
    except ReviewPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="review persistence unavailable") from error


@app.get("/api/v1/opportunities")
def list_operational_opportunities(query: OpportunityReviewUIQueryService = Depends(get_opportunity_review_ui_query_service)):
    try: return query.list()
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="opportunity persistence unavailable") from error


@app.get("/api/v1/opportunities/{opportunity_id}/review-detail")
def get_operational_opportunity_detail(opportunity_id: str, query: OpportunityReviewUIQueryService = Depends(get_opportunity_review_ui_query_service)):
    try: result = query.detail(opportunity_id)
    except (sqlite3.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="opportunity persistence unavailable") from error
    if result is None: raise HTTPException(status_code=404, detail="opportunity not found")
    return result


@app.get("/api/v1/opportunities/{opportunity_id}/decision-readiness")
def get_decision_readiness(opportunity_id: str, service: DecisionReadinessService = Depends(get_decision_readiness_service)):
    try: return service.execute(opportunity_id)
    except DecisionReadinessNotFoundError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="decision readiness unavailable") from error


@app.get("/api/v1/opportunities/{opportunity_id}/production-safety-evaluations")
def get_production_safety_operational_detail(
    opportunity_id: str,
    service: GetProductionSafetyOperationalDetail = Depends(get_production_safety_detail_service),
):
    try:
        return service.execute(opportunity_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except ProductionSafetyEvaluationPersistenceError as error:
        raise HTTPException(status_code=503, detail="Production Safety persistence is unavailable") from error


@app.post("/api/v1/opportunities/{opportunity_id}/production-safety-evaluations")
def evaluate_production_safety_operational(
    opportunity_id: str,
    request: ProductionSafetyEvaluationRequest,
    service: EvaluateProductionSafetyApi = Depends(get_production_safety_api_service),
):
    try:
        result = service.execute(EvaluateAndPersistProductionSafetyCommand(
            request.command_id, opportunity_id, request.snapshot_chain_binding_id,
            request.selected_product_snapshot_id, request.requested_at,
        ))
    except LookupError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except (ProductionSafetyChainNotFoundError, ProductionSafetyProductNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ProductionSafetyEvaluationCommandConflictError, ProductionSafetySelectedProductConflictError, ProductionSafetySourceLineageError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProductionSafetyEvaluationPersistenceError as error:
        raise HTTPException(status_code=503, detail="Production Safety persistence is unavailable") from error
    return JSONResponse(status_code=200 if result.replayed else 201, content=result.to_dict())


def _economics_evidence(value: EconomicEvidenceRequest) -> EconomicEvidence:
    return EconomicEvidence(value.status, value.source, value.observed_at, value.reference)


def _money_input(value: MoneyInputRequest) -> MoneyInput:
    return MoneyInput(
        Decimal(value.amount) if value.amount is not None else None,
        value.currency,
        _economics_evidence(value.evidence),
    )


def _rate_input(value: RateInputRequest) -> RateInput:
    return RateInput(
        Decimal(value.rate) if value.rate is not None else None,
        _economics_evidence(value.evidence),
    )


def _verified_economics_payload(snapshot) -> dict[str, object]:
    payload: dict[str, object] = {
        "opportunity_id": snapshot.opportunity_id,
        "snapshot_at": snapshot.snapshot_at.isoformat(),
        "schema_version": snapshot.schema_version,
    }
    for name in ("purchase_cost", "shipping_cost", "marketplace_fee_rate",
                 "payment_fee_rate", "fixed_fee", "tax_rate", "duty_cost",
                 "other_cost", "expected_sale_price"):
        item = getattr(snapshot.inputs, name)
        number = getattr(item, "amount", getattr(item, "rate", None))
        evidence = item.evidence
        payload[name] = {
            "amount" if hasattr(item, "amount") else "rate": str(number) if number is not None else None,
            **({"currency": item.currency} if hasattr(item, "currency") else {}),
            "evidence": {"status": evidence.status.value, "source": evidence.source,
                         "observed_at": evidence.observed_at.isoformat() if evidence.observed_at else None,
                         "reference": evidence.reference},
        }
    return payload


@app.post("/api/v1/opportunities/{opportunity_id}/verified-economics", status_code=201)
def finalize_verified_economics_admission(
    opportunity_id: str,
    request: VerifiedEconomicsAdmissionRequest,
    response: Response,
    service: FinalizeVerifiedEconomicsAdmission = Depends(get_verified_economics_admission_service),
):
    try:
        inputs = VerifiedEconomicsInput(
            purchase_cost=_money_input(request.purchase_cost),
            shipping_cost=_money_input(request.shipping_cost),
            marketplace_fee_rate=_rate_input(request.marketplace_fee_rate),
            payment_fee_rate=_rate_input(request.payment_fee_rate),
            fixed_fee=_money_input(request.fixed_fee),
            tax_rate=_rate_input(request.tax_rate),
            duty_cost=_money_input(request.duty_cost),
            other_cost=_money_input(request.other_cost),
            expected_sale_price=_money_input(request.expected_sale_price),
        )
        result = service.execute(FinalizeVerifiedEconomicsAdmissionCommand(
            opportunity_id, request.command_id, request.operator_id, inputs, request.snapshot_at
        ))
        response.status_code = 200 if result.replayed else 201
        return _verified_economics_payload(result.snapshot)
    except VerifiedEconomicsAdmissionNotFoundError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except VerifiedEconomicsAdmissionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (VerifiedEconomicsAdmissionPersistenceError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="verified economics persistence unavailable") from error


def _competition_payload(result) -> dict[str, object]:
    observation, snapshot = result.observation, result.snapshot
    target_subject = isinstance(
        observation.identity, NewToMarketDomesticSellingTargetIdentity
    )
    subject_payload = (
        {"subject": {
            "kind": "new_to_market_domestic_selling_target",
            "domestic_selling_target_id": observation.identity.domestic_selling_target_id,
            "market": observation.identity.market,
            "schema_version": observation.identity.schema_version,
        }}
        if target_subject
        else {"identity": {"scope": observation.identity.scope.value,
            "market": observation.identity.market, "marketplace": observation.identity.marketplace,
            "canonical_product_id": observation.identity.canonical_product_id,
            "marketplace_item_id": observation.identity.marketplace_item_id,
            "normalized_query": observation.identity.normalized_query,
            "category": observation.identity.category, "variant_identity": observation.identity.variant_identity,
            "condition": observation.identity.condition, "window_started_at": observation.identity.window_started_at.isoformat(),
            "window_ended_at": observation.identity.window_ended_at.isoformat()}}
    )
    return {"observation": {"observation_id": observation.observation_id,
            **subject_payload,
            "observed_at": observation.observed_at.isoformat(),
            "evidence": {name: {"value": str(item.value) if isinstance(item.value, Decimal) else item.value,
                "source": item.source, "reference": item.reference,
                "observed_at": item.observed_at.isoformat() if item.observed_at else None,
                "status": item.status.value, "confidence": str(item.confidence), "unit": item.unit,
                "collection_method": item.collection_method,
                **({"market": item.market, "marketplace": item.marketplace,
                    "keyword": item.keyword, "category": item.category,
                    "marketplace_item_id": item.marketplace_item_id,
                    "canonical_product_id": item.canonical_product_id}
                   if target_subject else {})} for name, item in observation.evidence.items()}},
        "assessment": {"snapshot_id": snapshot.snapshot_id,
            "competition_level": snapshot.assessment.competition_level.value,
            "price_pressure": snapshot.assessment.price_pressure.value,
            "rocket_competition": snapshot.assessment.rocket_competition.value,
            "market_concentration": str(snapshot.assessment.market_concentration),
            "confidence": str(snapshot.confidence), "summary": snapshot.assessment.summary,
            "freshness": snapshot.freshness.value, "availability": snapshot.availability.value,
            "generated_at": snapshot.generated_at.isoformat(), "schema_version": snapshot.schema_version,
            "policy_version": snapshot.policy_version}}


@app.post("/api/v1/opportunities/{opportunity_id}/competition-observations", status_code=201)
def finalize_competition_observation(
    opportunity_id: str, request: CompetitionObservationAdmissionRequest | TargetCompetitionObservationAdmissionRequest, response: Response,
    service: FinalizeCompetitionObservationAdmission = Depends(get_competition_admission_service),
):
    try:
        target_request = isinstance(request, TargetCompetitionObservationAdmissionRequest)
        identity = (
            NewToMarketDomesticSellingTargetIdentity(
                request.subject.domestic_selling_target_id
            )
            if target_request
            else MarketObservationIdentity(**request.identity.model_dump())
        )
        count_metrics = {"competitor_count", "rocket_seller_count", "sponsored_result_count", "organic_result_count"}
        price_metrics = {"lowest_price", "highest_price", "median_price", "price_spread"}
        evidence = {}
        for name, value in request.evidence.items():
            raw = value.value
            if name in count_metrics and raw is not None and (isinstance(raw, bool) or not isinstance(raw, int)):
                raise ValueError(f"{name} must be an integer")
            if name in price_metrics and raw is not None:
                if not isinstance(raw, str): raise ValueError(f"{name} must be a Decimal string")
                raw = Decimal(raw)
            evidence[name] = MarketEvidence(raw, value.source, value.reference, value.observed_at,
                value.status, Decimal(value.confidence),
                value.market if target_request else identity.market,
                value.marketplace if target_request else identity.marketplace,
                value.collection_method, "market-evidence-v1", value.keyword, value.category,
                value.marketplace_item_id, value.canonical_product_id, value.unit)
        observation = CompetitionObservation(request.observation_id, identity, request.observed_at,
            "competition-target-v1" if target_request else "competition-v1", evidence)
        result = service.execute(FinalizeCompetitionObservationAdmissionCommand(
            opportunity_id, request.command_id, request.operator_id, observation, request.submitted_at))
        response.status_code = 200 if result.replayed else 201
        return _competition_payload(result)
    except CompetitionAdmissionNotFoundError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except CompetitionAdmissionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (CompetitionAdmissionUnavailableError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="competition admission unavailable") from error


def _demand_payload(result):
    observation, snapshot, assessment = result.observation, result.snapshot, result.snapshot.assessment
    target_subject = isinstance(
        observation.identity, NewToMarketDomesticSellingTargetIdentity
    )
    subject_payload = ({"subject": {
        "kind": "new_to_market_domestic_selling_target",
        "domestic_selling_target_id": observation.identity.domestic_selling_target_id,
        "market": observation.identity.market,
        "schema_version": observation.identity.schema_version,
    }} if target_subject else {})
    return {"observation": {"observation_id": observation.observation_id,
        **subject_payload,
        "observed_at": observation.observed_at.isoformat(),
        "evidence": {name: {"value": str(item.value) if isinstance(item.value, Decimal) else item.value,
            "source": item.source, "reference": item.reference,
            "observed_at": item.observed_at.isoformat() if item.observed_at else None,
            "status": item.status.value, "confidence": str(item.confidence), "unit": item.unit,
            "collection_method": item.collection_method,
            **({"market": item.market, "marketplace": item.marketplace,
                "keyword": item.keyword, "category": item.category,
                "marketplace_item_id": item.marketplace_item_id,
                "canonical_product_id": item.canonical_product_id}
               if target_subject else {})} for name, item in observation.evidence.items()}},
        "assessment": {"snapshot_id": snapshot.snapshot_id,
            "demand_level": assessment.demand_level.value if assessment.demand_level else None,
            "popularity_level": assessment.popularity_level.value if assessment.popularity_level else None,
            "review_quality": assessment.review_quality.value, "availability": snapshot.availability.value,
            "available_metrics": assessment.available_metrics, "missing_metrics": assessment.missing_metrics,
            "confidence": str(snapshot.confidence), "summary": assessment.summary,
            "freshness": snapshot.freshness.value, "generated_at": snapshot.generated_at.isoformat(),
            "schema_version": snapshot.schema_version, "policy_version": snapshot.policy_version}}


@app.post("/api/v1/opportunities/{opportunity_id}/demand-observations", status_code=201)
def finalize_demand_observation(opportunity_id: str, request: DemandObservationAdmissionRequest | TargetDemandObservationAdmissionRequest,
    response: Response, service: FinalizeDemandObservationAdmission = Depends(get_demand_admission_service)):
    try:
        target_request = isinstance(request, TargetDemandObservationAdmissionRequest)
        identity = (
            NewToMarketDomesticSellingTargetIdentity(
                request.subject.domestic_selling_target_id
            )
            if target_request
            else MarketObservationIdentity(**request.identity.model_dump())
        )
        integer_metrics = {"search_volume", "review_count", "coupang_popularity_rank",
                           "itemscout_popularity_rank", "observed_result_position"}
        decimal_metrics = {"rating", "sales_proxy"}; evidence = {}
        for name, value in request.evidence.items():
            raw = value.value
            if name in integer_metrics and raw is not None and (isinstance(raw, bool) or not isinstance(raw, int)):
                raise ValueError(f"{name} must be an integer")
            if name in decimal_metrics and raw is not None:
                if not isinstance(raw, str): raise ValueError(f"{name} must be a Decimal string")
                raw = Decimal(raw)
            evidence[name] = MarketEvidence(raw, value.source, value.reference, value.observed_at,
                value.status, Decimal(value.confidence),
                value.market if target_request else identity.market,
                value.marketplace if target_request else identity.marketplace,
                value.collection_method, "market-evidence-v1", value.keyword, value.category,
                value.marketplace_item_id, value.canonical_product_id, value.unit)
        observation = DemandObservation(request.observation_id, identity, request.observed_at,
            "demand-target-v1" if target_request else "demand-v1", evidence)
        result = service.execute(FinalizeDemandObservationAdmissionCommand(
            opportunity_id, request.command_id, request.operator_id, observation, request.submitted_at))
        response.status_code = 200 if result.replayed else 201
        return _demand_payload(result)
    except DemandAdmissionNotFoundError as error:
        raise HTTPException(status_code=404, detail="opportunity not found") from error
    except DemandAdmissionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (DemandAdmissionUnavailableError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="demand admission unavailable") from error


def _sourcing_money_payload(value) -> dict[str, object]:
    return {
        "availability": value.availability.value,
        "amount": None if value.amount is None else str(value.amount),
        "currency": value.currency,
    }


def _sourcing_quantity_payload(value) -> dict[str, object]:
    return {"availability": value.availability.value, "quantity": value.quantity}


def _sourcing_artifact_payload(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "artifact_id": value.artifact_id, "artifact_type": value.artifact_type.value,
        "artifact_origin": value.artifact_origin.value, "source_type": value.source_type.value,
        "sha256": value.sha256, "captured_at": value.captured_at.isoformat(),
        "width": value.width, "height": value.height, "mime_type": value.mime_type,
        "file_size": value.file_size, "schema_version": value.schema_version,
    }


def _sourcing_evidence_payload(value) -> dict[str, object]:
    return {
        "kind": value.kind.value, "source_reference": value.source_reference,
        "observed_at": value.observed_at.isoformat(),
        "artifact_reference": _sourcing_artifact_payload(value.artifact_reference),
        "schema_version": value.schema_version,
    }


def _market_identity_payload(value) -> dict[str, object]:
    return {
        "scope": value.scope.value, "market": value.market,
        "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id,
        "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query, "category": value.category,
        "variant_identity": value.variant_identity, "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(),
    }


def _domestic_market_evidence_payload(value) -> dict[str, object]:
    return {
        "metric": value.metric,
        "value": str(value.value) if isinstance(value.value, Decimal) else value.value,
        "source": value.source,
        "reference": value.reference,
        "observed_at": value.observed_at,
        "collection_method": value.collection_method,
        "status": value.status.value,
        "confidence": str(value.confidence),
        "unit": value.unit,
    }


def _domestic_market_source_payload(value) -> dict[str, object]:
    return {
        "observation_id": value.observation_id,
        "assessment_id": value.assessment_id,
        "observation_schema_version": value.observation_schema_version,
        "assessment_schema_version": value.assessment_schema_version,
        "assessment_policy_version": value.assessment_policy_version,
        "availability": value.availability,
        "evidence": tuple(
            _domestic_market_evidence_payload(item) for item in value.evidence
        ),
    }


def _domestic_market_validation_payload(result) -> dict[str, object]:
    assessment = result.assessment
    manifest = assessment.source_manifest
    verification = assessment.verification
    return {
        "command_id": result.receipt.command_id,
        "assessment_id": assessment.assessment_id,
        "source_manifest": {
            "opportunity_id": manifest.opportunity_id,
            "discovery_reference": manifest.discovery_reference,
            "market_identity": _market_identity_payload(manifest.market_identity),
            "competition": _domestic_market_source_payload(manifest.competition),
            "demand": _domestic_market_source_payload(manifest.demand),
            "accepted_external_signal_ids": manifest.accepted_external_signal_ids,
            "schema_version": manifest.schema_version,
        },
        "verification": {
            "operator_id": verification.operator_id,
            "verified_at": verification.verified_at,
            "current_use_confirmed": verification.current_use_confirmed,
            "reviewed_source_ids": verification.reviewed_source_ids,
            "schema_version": verification.schema_version,
        },
        "state": assessment.state.value,
        "blocking_reasons": tuple(
            value.code.value for value in assessment.blocking_reasons
        ),
        "policy_name": assessment.policy_name,
        "policy_version": assessment.policy_version,
        "requested_at": assessment.requested_at,
        "evaluated_at": assessment.evaluated_at,
        "committed_at": result.receipt.committed_at,
        "assessment_schema_version": assessment.schema_version,
        "receipt_schema_version": result.receipt.schema_version,
        "replayed": result.replayed,
    }


@app.post(
    "/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
    response_model=DomesticMarketValidationResponse,
    status_code=201,
)
def validate_domestic_market_for_capital(
    opportunity_id: str,
    request: DomesticMarketValidationRequest,
    response: Response,
    entry: DomesticMarketValidationProductionEntry = Depends(
        get_domestic_market_validation_entry
    ),
) -> DomesticMarketValidationResponse:
    try:
        result = entry.execute(request.to_application_request(opportunity_id))
    except DomesticMarketValidationSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DomesticMarketValidationSourceConflictError,
        DomesticMarketValidationReplayConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (DomesticMarketValidationPolicyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (DomesticMarketValidationPersistenceError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="domestic market validation persistence unavailable",
        ) from error
    response.status_code = 200 if result.replayed else 201
    return DomesticMarketValidationResponse.model_validate(
        _domestic_market_validation_payload(result)
    )


def _domestic_selling_result_payload(result) -> dict[str, object]:
    admission = result.admission
    source = admission.source_opportunity_identity
    domestic = admission.domestic_opportunity_identity
    verification = admission.product_equivalence
    binding = result.market_binding
    return {
        "command_id": result.receipt.command_id,
        "admission_id": admission.admission_id,
        "source_opportunity_identity": {
            "opportunity_id": source.opportunity_id,
            "discovery_reference": source.discovery_reference,
        },
        "domestic_opportunity_identity": {
            "opportunity_id": domestic.opportunity_id,
            "discovery_reference": domestic.discovery_reference,
        },
        "lifecycle": {
            "status": result.lifecycle.status.value,
            "version": result.lifecycle.version,
        },
        "market_binding": {
            "opportunity_id": binding.opportunity_id,
            "discovery_reference": binding.discovery_reference,
            "market_observation_identity": _market_identity_payload(
                binding.market_observation_identity
            ),
            "bound_at": binding.bound_at.isoformat(),
            "schema_version": binding.schema_version,
        },
        "product_equivalence": {
            "operator_id": verification.operator_id,
            "evidence_reference": verification.evidence_reference,
            "confirmed": verification.confirmed,
            "verified_at": verification.verified_at.isoformat(),
            "schema_version": verification.schema_version,
        },
        "source_product_snapshot_id": admission.source_product_snapshot_id,
        "policy_name": admission.policy_name,
        "policy_version": admission.policy_version,
        "requested_at": admission.requested_at.isoformat(),
        "verified_at": verification.verified_at.isoformat(),
        "admitted_at": admission.admitted_at.isoformat(),
        "committed_at": result.receipt.committed_at.isoformat(),
        "admission_schema_version": admission.schema_version,
        "receipt_schema_version": result.receipt.schema_version,
        "replayed": result.replayed,
    }


@app.post(
    "/api/v1/opportunities/{source_opportunity_id}/domestic-selling-admissions",
    status_code=201,
)
def admit_domestic_selling_opportunity(
    source_opportunity_id: str,
    request: DomesticSellingOpportunityAdmissionRequest,
    response: Response,
    entry: AdmitDomesticSellingOpportunity = Depends(
        get_domestic_selling_opportunity_entry
    ),
):
    try:
        result = entry.execute(
            AdmitDomesticSellingOpportunityCommand(
                command_id=request.command_id,
                source_opportunity_id=source_opportunity_id,
                source_product_snapshot_id=request.source_product_snapshot_id,
                target_market_identity=MarketObservationIdentity(
                    **request.target_market_identity.model_dump()
                ),
                operator_id=request.operator_id,
                product_equivalence_confirmed=(
                    request.product_equivalence_confirmed
                ),
                evidence_reference=request.evidence_reference,
                verified_at=request.verified_at,
                requested_at=request.requested_at,
                policy_name=request.policy_name,
                policy_version=request.policy_version,
            )
        )
        response.status_code = 200 if result.replayed else 201
        return _domestic_selling_result_payload(result)
    except DomesticSellingOpportunitySourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DomesticSellingOpportunityReplayConflictError,
        DomesticSellingOpportunityCardinalityConflictError,
        DomesticSellingOpportunityLineageError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        DomesticSellingOpportunityPolicyError,
        DomesticSellingOpportunityVerificationError,
        TypeError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (
        DomesticSellingOpportunityPersistenceError,
        MalformedDomesticSellingOpportunityPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="domestic selling Opportunity persistence unavailable",
        ) from error
    except DomesticSellingOpportunityError as error:
        raise HTTPException(
            status_code=503, detail="domestic selling Opportunity unavailable"
        ) from error


def _new_to_market_result_payload(result) -> dict[str, object]:
    admission = result.admission
    source = admission.source_manifest
    source_opportunity = source.source_opportunity_identity
    domestic = admission.domestic_opportunity_identity
    target = admission.target_identity
    binding = result.target_binding
    search = admission.search_manifest
    return {
        "command_id": result.receipt.command_id,
        "admission_id": admission.admission_id,
        "source_opportunity_identity": {
            "opportunity_id": source_opportunity.opportunity_id,
            "discovery_reference": source_opportunity.discovery_reference,
        },
        "source_lifecycle": {
            "status": source.source_lifecycle_status.value,
            "version": source.source_lifecycle_version,
        },
        "source_market_identity": _market_identity_payload(
            source.source_market_identity
        ),
        "source_candidate_promotion": {
            "candidate_id": source.candidate_id,
            "candidate_opportunity_binding_id": (
                source.candidate_opportunity_binding_id
            ),
            "promotion_command_id": source.promotion_command_id,
            "promotion_admission_id": source.promotion_admission_id,
            "finalized_group_id": source.finalized_group_id,
            "product_snapshot_capture_command_id": (
                source.product_snapshot_capture_command_id
            ),
            "product_snapshot_ids": list(source.product_snapshot_ids),
            "representative_product_snapshot_id": (
                source.representative_product_snapshot_id
            ),
            "schema_version": source.schema_version,
        },
        "source_product_snapshot": {
            "product_snapshot_id": source.selected_product_snapshot_id,
            "source_observation_id": source.selected_source_observation_id,
        },
        "domestic_selling_target": {
            "domestic_selling_target_id": target.domestic_selling_target_id,
            "market": target.market,
            "kind": target.kind.value,
            "schema_version": target.schema_version,
        },
        "domestic_opportunity_identity": {
            "opportunity_id": domestic.opportunity_id,
            "discovery_reference": domestic.discovery_reference,
        },
        "lifecycle": {
            "status": result.lifecycle.status.value,
            "version": result.lifecycle.version,
        },
        "target_binding": {
            "opportunity_id": binding.opportunity_id,
            "discovery_reference": binding.discovery_reference,
            "domestic_selling_target_id": (
                binding.target_identity.domestic_selling_target_id
            ),
            "bound_at": binding.bound_at.isoformat(),
            "schema_version": binding.schema_version,
        },
        "bounded_kr_search": {
            "searched_channels": list(search.searched_channels),
            "scope_kind": search.scope_kind.value,
            "scope_value": search.scope_value,
            "performed_at": search.performed_at.isoformat(),
            "operator_id": search.operator_id,
            "evidence_references": list(search.evidence_references),
            "conclusion": search.conclusion.value,
            "market": search.market,
            "schema_version": search.schema_version,
        },
        "operator_id": admission.operator_id,
        "decision_reason": admission.decision_reason,
        "policy_name": admission.policy_name,
        "policy_version": admission.policy_version,
        "requested_at": admission.requested_at.isoformat(),
        "verified_at": admission.verified_at.isoformat(),
        "admitted_at": admission.admitted_at.isoformat(),
        "committed_at": result.receipt.committed_at.isoformat(),
        "admission_schema_version": admission.schema_version,
        "receipt_schema_version": result.receipt.schema_version,
        "replayed": result.replayed,
    }


@app.post(
    "/api/v1/opportunities/{source_opportunity_id}/new-to-market-domestic-selling-admissions",
    status_code=201,
    response_model=NewToMarketDomesticSellingOpportunityAdmissionResponse,
)
def admit_new_to_market_domestic_selling_opportunity(
    source_opportunity_id: str,
    request: NewToMarketDomesticSellingOpportunityAdmissionRequest,
    response: Response,
    entry: AdmitNewToMarketDomesticSellingOpportunity = Depends(
        get_new_to_market_domestic_selling_entry
    ),
):
    try:
        result = entry.execute(
            AdmitNewToMarketDomesticSellingOpportunityCommand(
                command_id=request.command_id,
                source_opportunity_id=source_opportunity_id,
                source_product_snapshot_id=request.source_product_snapshot_id,
                operator_id=request.operator_id,
                decision_reason=request.decision_reason,
                search_manifest=request.bounded_kr_search.to_domain(),
                verified_at=request.verified_at,
                requested_at=request.requested_at,
                policy_name=request.policy_name,
                policy_version=request.policy_version,
            )
        )
        response.status_code = 200 if result.replayed else 201
        return NewToMarketDomesticSellingOpportunityAdmissionResponse.model_validate(
            _new_to_market_result_payload(result)
        )
    except NewToMarketDomesticSellingSourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        NewToMarketDomesticSellingReplayConflictError,
        NewToMarketDomesticSellingCardinalityConflictError,
        NewToMarketDomesticSellingLineageError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        NewToMarketDomesticSellingPolicyError,
        NewToMarketDomesticSellingVerificationError,
        TypeError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (
        NewToMarketDomesticSellingPersistenceError,
        MalformedNewToMarketDomesticSellingPersistenceError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(
            status_code=503,
            detail="new-to-market domestic selling persistence unavailable",
        ) from error
    except NewToMarketDomesticSellingError as error:
        raise HTTPException(
            status_code=503,
            detail="new-to-market domestic selling Opportunity unavailable",
        ) from error


def _sourcing_result_payload(result) -> dict[str, object]:
    admission = result.admission
    lineage = admission.selling_product_lineage
    supplier = admission.supplier_identity
    product = admission.sourcing_product_identity
    quote = admission.quote_revision
    match = admission.match_verification
    if isinstance(lineage, DomesticSellingProductLineage):
        lineage_payload = {
            "kind": "domestic_selling_admission",
            "domestic_selling_admission_id": lineage.domestic_selling_admission_id,
            "opportunity_id": lineage.opportunity_identity.opportunity_id,
            "discovery_reference": lineage.opportunity_identity.discovery_reference,
            "source_opportunity_id": lineage.source_opportunity_identity.opportunity_id,
            "source_discovery_reference": (
                lineage.source_opportunity_identity.discovery_reference
            ),
            "source_product_observation_snapshot_id": (
                lineage.source_product_observation_snapshot_id
            ),
            "market_observation_identity": _market_identity_payload(
                lineage.market_observation_identity
            ),
            "product_equivalence_evidence_reference": (
                lineage.product_equivalence_evidence_reference
            ),
            "schema_version": lineage.schema_version,
        }
    else:
        lineage_payload = {
            "opportunity_id": lineage.opportunity_identity.opportunity_id,
            "discovery_reference": lineage.opportunity_identity.discovery_reference,
            "candidate_id": lineage.candidate_id,
            "candidate_opportunity_binding_id": lineage.candidate_opportunity_binding_id,
            "product_observation_snapshot_id": lineage.product_observation_snapshot_id,
            "market_observation_identity": _market_identity_payload(
                lineage.market_observation_identity
            ),
        }
    return {
        "admission_id": admission.admission_id, "revision": admission.revision,
        "command_id": result.receipt.command_id, "replayed": result.replayed,
        "selling_product_lineage": lineage_payload,
        "supplier": {
            "supplier_id": supplier.supplier_id, "source_platform": supplier.source_platform,
            "external_supplier_reference": supplier.external_supplier_reference,
            "display_name": supplier.display_name, "schema_version": supplier.schema_version,
        },
        "sourcing_product": {
            "sourcing_product_id": product.sourcing_product_id,
            "supplier_id": product.supplier_id,
            "external_product_reference": product.external_product_reference,
            "option_reference": product.option_reference, "sku_reference": product.sku_reference,
            "source_url": product.source_url, "observed_at": product.observed_at.isoformat(),
            "schema_version": product.schema_version,
        },
        "quote": {
            "quote_id": quote.quote_id, "revision": quote.revision,
            "sourcing_product_id": quote.sourcing_product_id,
            "unit_price": _sourcing_money_payload(quote.unit_price),
            "minimum_order_quantity": _sourcing_quantity_payload(quote.minimum_order_quantity),
            "quoted_quantity": _sourcing_quantity_payload(quote.quoted_quantity),
            "shipping_terms": tuple({"scope": term.scope.value,
                "cost": _sourcing_money_payload(term.cost)} for term in quote.shipping_terms),
            "lead_time_availability": quote.lead_time_availability.value,
            "lead_time_days": quote.lead_time_days,
            "observed_at": quote.observed_at.isoformat(),
            "valid_until": None if quote.valid_until is None else quote.valid_until.isoformat(),
            "evidence": _sourcing_evidence_payload(quote.evidence),
            "schema_version": quote.schema_version,
        },
        "match_verification": {
            "verification_id": match.verification_id,
            "sourcing_product_id": match.sourcing_product_id,
            "status": match.status.value, "verifier_id": match.verifier_id,
            "verified_at": match.verified_at.isoformat(),
            "evidence": _sourcing_evidence_payload(match.evidence),
            "proposal_score": None if match.proposal_score is None else str(match.proposal_score),
            "proposal_version": match.proposal_version,
            "schema_version": match.schema_version,
        },
        "requested_at": admission.requested_at.isoformat(),
        "verified_at": match.verified_at.isoformat(),
        "admitted_at": admission.admitted_at.isoformat(),
        "committed_at": result.receipt.committed_at.isoformat(),
        "admission_schema_version": admission.schema_version,
        "receipt_schema_version": result.receipt.schema_version,
    }


def _execute_sourcing(operation, command, response: Response):
    try:
        result = operation(command)
        response.status_code = 200 if result.replayed else 201
        return _sourcing_result_payload(result)
    except SourcingAdmissionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (SourcingAdmissionReplayConflictError, SourcingQuoteRevisionConflictError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SourcingDomesticSellingLineageError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (InvalidSourcingCommandError, SourcingProductMatchNotVerifiedError,
            TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (SourcingIdentityGenerationError, SourcingAuthorityPersistenceError,
            MalformedSourcingAuthorityPersistenceError,
            UnsupportedSourcingAuthorityVersionError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503, detail="sourcing authority persistence unavailable"
        ) from error
    except SourcingAuthorityError as error:
        raise HTTPException(status_code=503, detail="sourcing authority unavailable") from error


@app.post("/api/v1/sourcing/admissions", status_code=201)
def admit_founder_sourcing(
    request: FounderSourcingAdmissionRequest,
    response: Response,
    entry: SourcingAuthorityProductionEntry = Depends(get_sourcing_authority_entry),
):
    try:
        command = AdmitFounderSourcingCommand(
            command_id=request.command_id,
            selling_product_lineage=request.selling_product_lineage.to_application(),
            supplier_platform=request.supplier_platform,
            external_supplier_reference=request.external_supplier_reference,
            supplier_display_name=request.supplier_display_name,
            external_product_reference=request.external_product_reference,
            option_reference=request.option_reference, sku_reference=request.sku_reference,
            source_url=request.source_url, product_observed_at=request.product_observed_at,
            quoted_unit_price=request.quoted_unit_price.to_domain(),
            minimum_order_quantity=request.minimum_order_quantity.to_domain(),
            quoted_quantity=request.quoted_quantity.to_domain(),
            shipping_terms=tuple(value.to_domain() for value in request.shipping_terms),
            lead_time_availability=request.lead_time_availability,
            lead_time_days=request.lead_time_days,
            quote_observed_at=request.quote_observed_at,
            quote_valid_until=request.quote_valid_until,
            quote_evidence=request.quote_evidence.to_domain(),
            match_status=request.match_status,
            match_evidence=request.match_evidence.to_domain(),
            verified_at=request.verified_at,
            proposal_score=None if request.proposal_score is None else Decimal(request.proposal_score),
            proposal_version=request.proposal_version,
            operator_id=request.operator_id, requested_at=request.requested_at,
        )
    except (InvalidSourcingCommandError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _execute_sourcing(entry.admit, command, response)


@app.post("/api/v1/sourcing/admissions/{admission_id}/quote-revisions", status_code=201)
def revise_founder_sourcing_quote(
    admission_id: str,
    request: SourcingQuoteRevisionRequest,
    response: Response,
    entry: SourcingAuthorityProductionEntry = Depends(get_sourcing_authority_entry),
):
    try:
        command = ReviseFounderSourcingQuoteCommand(
            command_id=request.command_id, admission_id=admission_id,
            expected_revision=request.expected_revision,
            quoted_unit_price=request.quoted_unit_price.to_domain(),
            minimum_order_quantity=request.minimum_order_quantity.to_domain(),
            quoted_quantity=request.quoted_quantity.to_domain(),
            shipping_terms=tuple(value.to_domain() for value in request.shipping_terms),
            lead_time_availability=request.lead_time_availability,
            lead_time_days=request.lead_time_days,
            quote_observed_at=request.quote_observed_at,
            quote_valid_until=request.quote_valid_until,
            quote_evidence=request.quote_evidence.to_domain(),
            operator_id=request.operator_id, requested_at=request.requested_at,
        )
    except (InvalidSourcingCommandError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _execute_sourcing(entry.revise, command, response)


@app.get("/api/v1/reviews/{session_id}")
def get_review_session(
    session_id: str,
    query_service: ReviewSessionQueryService = Depends(get_review_session_query_service),
) -> dict[str, object]:
    try:
        session = query_service.get(GetReviewSession(session_id))
        return ReviewSessionResponseDTO.from_session(session).to_dict()
    except ReviewSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OpportunityReviewBindingNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ReviewPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="review persistence unavailable") from error


@app.get("/api/v1/reviews/{session_id}/detail")
def get_review_session_detail(
    session_id: str,
    query_service: ReviewSessionQueryService = Depends(get_review_session_query_service),
) -> dict[str, object]:
    try:
        detail = query_service.detail(GetReviewSessionDetail(session_id))
        return ReviewSessionDetailResponseDTO(detail).to_dict()
    except ReviewSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ReviewPersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="review persistence unavailable") from error


def _execute_review_transition(operation, command) -> dict[str, object]:
    try:
        result = operation(command)
        session = getattr(result, "session", result)
        return ReviewSessionResponseDTO.from_session(session).to_dict()
    except ReviewSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DuplicateReviewSessionError,
        DuplicateCandidateReviewError,
        PendingCandidatesError,
        ReviewArtifactMismatchError,
        ReviewCandidateMembershipError,
        ReviewCandidateNotFoundError,
        ReviewSessionVersionConflictError,
        ReviewCommandConflictError,
        ReviewOperatorMismatchError,
        InvalidReviewSessionTransitionError,
        OpportunityReviewBindingConflictError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ReviewPersistenceError, OpportunityReviewBindingPersistenceError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="review persistence unavailable",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _review_context(
    session_id: str,
    request: ReviewCommandContextRequest,
) -> ReviewCommandContext:
    identity = request.market_observation_identity
    return ReviewCommandContext(
        session_id=session_id,
        candidate_id=request.candidate_id,
        market_observation_identity=MarketObservationIdentity(
            scope=identity.scope,
            market=identity.market,
            marketplace=identity.marketplace,
            canonical_product_id=identity.canonical_product_id,
            marketplace_item_id=identity.marketplace_item_id,
            normalized_query=identity.normalized_query,
            category=identity.category,
            variant_identity=identity.variant_identity,
            condition=identity.condition,
            window_started_at=identity.window_started_at,
            window_ended_at=identity.window_ended_at,
        ),
        signal_name=request.signal_name,
        signal_direction=request.signal_direction,
        artifact_identity=request.artifact_identity,
        created_at=request.created_at,
    )


@app.post("/api/v1/reviews", status_code=status.HTTP_201_CREATED)
def create_trusted_review_session(
    request: CreateTrustedReviewRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    command = CreateReviewSession(
        session_id=request.session_id,
        artifact_id=request.artifact_id,
        candidate_ids=request.candidate_ids,
        operator_id=request.operator_id,
        created_at=request.created_at,
        command_id=request.command_id,
        contexts=tuple(
            _review_context(request.session_id, context)
            for context in request.contexts
        ),
        opportunity_id=request.opportunity_id,
    )
    return _execute_review_transition(workflow.create_session, command)


@app.post("/api/v1/reviews/{session_id}/start")
def start_review_session(
    session_id: str,
    request: StartReviewRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.start_review,
        StartReviewCommand(
            session_id=session_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            operator_id=request.operator_id,
            started_at=request.started_at,
        ),
    )


@app.post("/api/v1/reviews/{session_id}/cancel")
def cancel_review_session(
    session_id: str,
    request: CancelReviewRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.cancel_review,
        CancelReviewCommand(
            session_id=session_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            operator_id=request.operator_id,
            reason=request.reason,
            cancelled_at=request.cancelled_at,
        ),
    )


@app.post("/api/v1/reviews/{session_id}/approve")
def approve_review_candidate(
    session_id: str,
    request: ApproveCandidateRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.approve_candidate,
        ApproveCandidateCommand(
            session_id=session_id,
            candidate_id=request.candidate_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            verification_id=request.verification_id,
            operator_id=request.operator_id,
            verified_at=request.verified_at,
            signal_id=request.signal_id,
            comment=request.comment,
            confidence=request.confidence,
        ),
    )


@app.post("/api/v1/reviews/{session_id}/correct")
def correct_review_candidate(
    session_id: str,
    request: CorrectCandidateRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.correct_candidate,
        CorrectCandidateCommand(
            session_id=session_id,
            candidate_id=request.candidate_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            verification_id=request.verification_id,
            operator_id=request.operator_id,
            verified_at=request.verified_at,
            signal_id=request.signal_id,
            comment=request.comment,
            confidence=request.confidence,
            corrected_value=request.corrected_value,
        ),
    )


@app.post("/api/v1/reviews/{session_id}/skip")
def skip_review_candidate(
    session_id: str,
    request: SkipCandidateRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.skip_candidate,
        SkipCandidateCommand(
            session_id=session_id,
            candidate_id=request.candidate_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            operator_id=request.operator_id,
            reason=request.reason,
            skipped_at=request.skipped_at,
        ),
    )


@app.post("/api/v1/reviews/{session_id}/complete")
def complete_review_session(
    session_id: str,
    request: CompleteReviewRequest,
    workflow: ReviewWorkflowService = Depends(get_review_workflow_service),
) -> dict[str, object]:
    return _execute_review_transition(
        workflow.complete_review,
        CompleteReviewCommand(
            session_id=session_id,
            expected_revision=request.expected_revision,
            command_id=request.command_id,
            operator_id=request.operator_id,
            completed_at=request.completed_at,
        ),
    )


@app.post(
    "/api/v1/opportunities/{opportunity_id}/decision-compositions",
    status_code=status.HTTP_201_CREATED,
)
def finalize_opportunity_decision_composition(
    opportunity_id: str,
    request: DecisionCompositionFinalizationRequest,
    use_case: FinalizeOpportunityDecisionComposition = Depends(
        get_decision_composition_finalizer
    ),
) -> dict[str, object]:
    try:
        response = use_case.execute(
            FinalizeOpportunityDecisionCompositionCommand(
                opportunity_id=opportunity_id,
                external_signal_ids=request.external_signal_ids,
                generated_at=request.generated_at,
                requested_by=request.requested_by,
            )
        )
    except DecisionCompositionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        DuplicateDecisionCompositionError,
        DecisionCompositionVersionConflictError,
        DecisionCompositionIdentityConflictError,
        UnsupportedDecisionCompositionVersionError,
        MissingDecisionCompositionSourceError,
        MalformedDecisionCompositionError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        DecisionCompositionPersistenceError,
        DecisionCompositionProjectionError,
        DecisionCompositionCommitError,
        sqlite3.Error,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DecisionCompositionProvenanceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return response.to_dict()


@app.post("/api/v1/validation-queue", status_code=status.HTTP_201_CREATED)
def add_to_validation_queue(
    request: ValidationQueueAdmissionRequest,
    repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository),
) -> dict[str, object]:
    service = _validation_service(repository)
    try:
        item = service.add(AddToValidationQueueCommand(**request.model_dump()))
    except DuplicateActiveValidationError as error:
        raise HTTPException(status_code=409, detail="active validation already exists") from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return item.to_dict()


@app.get("/api/v1/validation-queue")
def get_validation_queue(
    lifecycle_status: list[OpportunityLifecycleStatus] | None = Query(default=None),
    limit: int = Query(default=100, ge=1),
    repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository),
) -> dict[str, object]:
    statuses = tuple(lifecycle_status) if lifecycle_status else ValidationQueueQuery().statuses
    items = _validation_service(repository).list(ValidationQueueQuery(statuses=statuses, limit=limit))
    return {"items": [item.to_dict() for item in items], "total_count": len(items)}


@app.get("/api/v1/validation-queue/{opportunity_id}")
def get_validation_queue_item(
    opportunity_id: str,
    repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository),
) -> dict[str, object]:
    item = _validation_service(repository).get(opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="validation opportunity not found")
    return item.to_dict()


@app.post("/api/v1/validation-queue/{opportunity_id}/review")
def start_validation_review(opportunity_id: str, request: ValidationQueueActionRequest, repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository)):
    service = _validation_service(repository)
    return _execute_validation_action(service.start_review, _action_command(opportunity_id, request))


@app.post("/api/v1/validation-queue/{opportunity_id}/approve")
def approve_validation_opportunity(opportunity_id: str, request: ValidationQueueActionRequest, repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository)):
    service = _validation_service(repository)
    return _execute_validation_action(service.approve, _action_command(opportunity_id, request))


@app.post("/api/v1/validation-queue/{opportunity_id}/reject")
def reject_validation_opportunity(opportunity_id: str, request: ValidationQueueActionRequest, repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository)):
    service = _validation_service(repository)
    return _execute_validation_action(service.reject, _action_command(opportunity_id, request))


@app.post("/api/v1/validation-queue/{opportunity_id}/return-to-review")
def return_validation_opportunity_to_review(opportunity_id: str, request: ValidationQueueActionRequest, repository: SQLiteValidationQueueRepository = Depends(get_validation_queue_repository)):
    service = _validation_service(repository)
    return _execute_validation_action(service.return_to_review, _action_command(opportunity_id, request))
    PendingCandidatesError,
    ReviewArtifactMismatchError,
    ReviewCandidateMembershipError,
    ReviewCandidateNotFoundError,
