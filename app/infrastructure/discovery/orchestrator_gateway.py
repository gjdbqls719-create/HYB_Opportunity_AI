from __future__ import annotations

from collections.abc import Callable

from app.domain.discovery import DiscoveryResult
from engine.orchestrator import OpportunityResult, find_best_opportunities


OpportunityFinder = Callable[..., list[OpportunityResult]]


def opportunity_result_to_discovery_result(
    opportunity: OpportunityResult,
) -> DiscoveryResult:
    """기존 Orchestrator 결과를 표준 Discovery 결과로 변환한다."""
    recommendation = opportunity.ai_recommendation

    return DiscoveryResult(
        product=opportunity.product,
        opportunity_score=opportunity.final_opportunity_score,
        matched_product_count=opportunity.matched_product_count,
        recommendation_grade=(
            recommendation.grade if recommendation is not None else None
        ),
        recommendation_action=(
            recommendation.action if recommendation is not None else None
        ),
        recommendation_summary=(
            recommendation.summary if recommendation is not None else None
        ),
        finalized_group_id=getattr(
            opportunity,
            "finalized_group_id",
            None,
        ),
        metadata={
            "analysis": dict(opportunity.analysis),
            "confidence_score": (
                opportunity.confidence.confidence_score
                if opportunity.confidence is not None
                else None
            ),
            "trend_score_adjustment": getattr(
                opportunity,
                "trend_score_adjustment",
                None,
            ),
            "success_probability": (
                recommendation.success_probability
                if recommendation is not None
                else None
            ),
        },
    )


class OrchestratorOpportunityDiscoveryGateway:
    """기존 엔진 오케스트레이터를 Discovery Application Port에 연결한다."""

    def __init__(
        self,
        *,
        finder: OpportunityFinder = find_best_opportunities,
    ) -> None:
        self._finder = finder

    def discover(
        self,
        *,
        query: str,
        limit: int,
    ) -> list[DiscoveryResult]:
        opportunities = self._finder(
            query=query,
            limit=limit,
        )

        return [
            opportunity_result_to_discovery_result(opportunity)
            for opportunity in opportunities
        ]
