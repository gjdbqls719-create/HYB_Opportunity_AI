from __future__ import annotations

from pathlib import Path

from datetime import datetime, timezone
from decimal import Decimal
import sqlite3
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
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
    CompetitionObservation,
    ExternalSignalDirection,
    InvalidReviewSessionTransitionError,
    MarketObservationIdentity,
    MarketObservationScope,
    MarketEvidence,
    MarketEvidenceStatus,
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
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.review import (
    SQLiteReviewSessionRepository,
    SQLiteVerifiedSignalPersistence,
)
from storage.price_history import DEFAULT_DATABASE_PATH


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


def get_opportunity_decision_dashboard_provider():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    market_repository = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield ProductionOpportunityDecisionDashboardProvider(
            repository,
            assessment_repository=market_repository,
        )
    finally:
        market_repository.close()
        repository.close()


def get_decision_composition_finalizer():
    repository = SQLiteValidationQueueRepository(DEFAULT_DATABASE_PATH)
    market_repository = SQLiteMarketObservationRepository(DEFAULT_DATABASE_PATH)
    try:
        yield FinalizeOpportunityDecisionComposition(
            FinalizeDecisionComposition(
                source_repository=repository,
                assessment_repository=market_repository,
                composition_repository=repository,
            ),
            clock=lambda: datetime.now(timezone.utc),
        )
    finally:
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
    try:
        yield DecisionReadinessService(persistence.opportunities, persistence.observations, persistence.sessions)
    finally:
        persistence.close()


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
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        MissingDecisionCompositionSourceError,
        MalformedDecisionCompositionError,
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
