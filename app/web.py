from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal
import sqlite3
from typing import Any

import requests

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from engine.orchestrator import find_best_opportunities
from presentation.dashboard import build_dashboard_cards
from presentation.dashboard_list import build_opportunity_list_card
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
    DiscoveryCompletionReplayError,
    DiscoveryRuntimeCorrelationError,
    PersistedDiscoveryExecutionEntry,
    PersistedDiscoveryResultReader,
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
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    CompetitionObservation,
    DemandObservation,
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


class AuthoritativeFinalizedGroupResponse(BaseModel):
    finalized_group_id: str
    discovery_execution_id: str
    observation_ids: tuple[str, ...]
    representative_observation_id: str
    grouping_policy_version: str
    finalized_at: datetime


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
    finalized_groups: tuple[AuthoritativeFinalizedGroupResponse, ...]


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
        reader = PersistedDiscoveryResultReader(
            result_repository=result_repository,
            group_repository=group_repository,
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
        entry = CandidatePromotionProductionEntry(
            candidate_repository=candidate_repository,
            promotion_repository=promotion_repository,
            opportunity_id_generator=ProductionOpportunityIdentityGenerator(),
            binding_id_generator=(
                ProductionCandidateOpportunityBindingIdentityGenerator()
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
        result = entry.execute(request.to_command())
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
        groups = reader.get_finalized_groups(discovery_execution_id)
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
    return DiscoveryFinalizedGroupsReadResponse(
        discovery_execution_id=discovery_execution_id,
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
            for group in groups
        ),
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
    response_model=CandidatePromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_opportunity_candidate(
    request: CandidatePromotionRequest,
    response: Response,
    entry: CandidatePromotionProductionEntry = Depends(
        get_candidate_promotion_entry
    ),
) -> CandidatePromotionResponse:
    try:
        result = entry.execute(request.to_command())
    except (
        CandidateForPromotionNotFoundError,
        CandidatePromotionContextNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        CandidateAlreadyPromotedError,
        CandidatePromotionCommandConflictError,
        CandidatePromotionIdentityConflictError,
        CandidatePromotionMarketIdentityConflictError,
        OpportunityAlreadyBoundToCandidateError,
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
    return {"observation": {"observation_id": observation.observation_id,
            "identity": {"scope": observation.identity.scope.value, "market": observation.identity.market,
                "marketplace": observation.identity.marketplace, "canonical_product_id": observation.identity.canonical_product_id,
                "marketplace_item_id": observation.identity.marketplace_item_id, "normalized_query": observation.identity.normalized_query,
                "category": observation.identity.category, "variant_identity": observation.identity.variant_identity,
                "condition": observation.identity.condition, "window_started_at": observation.identity.window_started_at.isoformat(),
                "window_ended_at": observation.identity.window_ended_at.isoformat()},
            "observed_at": observation.observed_at.isoformat(),
            "evidence": {name: {"value": str(item.value) if isinstance(item.value, Decimal) else item.value,
                "source": item.source, "reference": item.reference,
                "observed_at": item.observed_at.isoformat() if item.observed_at else None,
                "status": item.status.value, "confidence": str(item.confidence), "unit": item.unit,
                "collection_method": item.collection_method} for name, item in observation.evidence.items()}},
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
    opportunity_id: str, request: CompetitionObservationAdmissionRequest, response: Response,
    service: FinalizeCompetitionObservationAdmission = Depends(get_competition_admission_service),
):
    try:
        identity = MarketObservationIdentity(**request.identity.model_dump())
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
                value.status, Decimal(value.confidence), identity.market, identity.marketplace,
                value.collection_method, "market-evidence-v1", value.keyword, value.category,
                value.marketplace_item_id, value.canonical_product_id, value.unit)
        observation = CompetitionObservation(request.observation_id, identity, request.observed_at,
                                             "competition-v1", evidence)
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
    return {"observation": {"observation_id": observation.observation_id,
        "observed_at": observation.observed_at.isoformat(),
        "evidence": {name: {"value": str(item.value) if isinstance(item.value, Decimal) else item.value,
            "source": item.source, "reference": item.reference,
            "observed_at": item.observed_at.isoformat() if item.observed_at else None,
            "status": item.status.value, "confidence": str(item.confidence), "unit": item.unit,
            "collection_method": item.collection_method} for name, item in observation.evidence.items()}},
        "assessment": {"snapshot_id": snapshot.snapshot_id,
            "demand_level": assessment.demand_level.value if assessment.demand_level else None,
            "popularity_level": assessment.popularity_level.value if assessment.popularity_level else None,
            "review_quality": assessment.review_quality.value, "availability": snapshot.availability.value,
            "available_metrics": assessment.available_metrics, "missing_metrics": assessment.missing_metrics,
            "confidence": str(snapshot.confidence), "summary": assessment.summary,
            "freshness": snapshot.freshness.value, "generated_at": snapshot.generated_at.isoformat(),
            "schema_version": snapshot.schema_version, "policy_version": snapshot.policy_version}}


@app.post("/api/v1/opportunities/{opportunity_id}/demand-observations", status_code=201)
def finalize_demand_observation(opportunity_id: str, request: DemandObservationAdmissionRequest,
    response: Response, service: FinalizeDemandObservationAdmission = Depends(get_demand_admission_service)):
    try:
        identity = MarketObservationIdentity(**request.identity.model_dump())
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
                value.status, Decimal(value.confidence), identity.market, identity.marketplace,
                value.collection_method, "market-evidence-v1", value.keyword, value.category,
                value.marketplace_item_id, value.canonical_product_id, value.unit)
        observation = DemandObservation(request.observation_id, identity, request.observed_at, "demand-v1", evidence)
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
