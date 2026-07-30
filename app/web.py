from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from engine.orchestrator import find_best_opportunities
from presentation.dashboard import build_dashboard_cards
from presentation.dashboard_list import build_opportunity_list_card


PROJECT_NAME = "HYB Opportunity AI"
API_VERSION = "v1"


class OpportunitySearchRequest(BaseModel):
    """Opportunity 검색 API의 최소 입력 계약."""

    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1)
    top: int = Field(default=5, ge=1)


app = FastAPI(title=PROJECT_NAME)


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
