from __future__ import annotations

from pathlib import Path

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    DuplicateActiveValidationError,
    OpportunityValidationService,
    ValidationActionCommand,
    ValidationQueueQuery,
)
from app.domain.opportunity import InvalidLifecycleTransitionError, OpportunityLifecycleStatus
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
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
