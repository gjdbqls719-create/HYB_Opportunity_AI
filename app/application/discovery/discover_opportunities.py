from __future__ import annotations

from dataclasses import dataclass

from app.application.discovery.ports import OpportunityDiscoveryGateway
from app.application.discovery.session import DiscoverySession
from app.application.discovery.statistics import DiscoveryStatistics
from app.domain.discovery import DiscoveryResult, RankingEngine


@dataclass(slots=True, frozen=True)
class DiscoverOpportunitiesResponse:
    session: DiscoverySession
    results: tuple[DiscoveryResult, ...]
    statistics: DiscoveryStatistics

    def top(self, count: int) -> tuple[DiscoveryResult, ...]:
        if count < 1:
            raise ValueError("count는 1 이상이어야 합니다.")
        return self.results[:count]


class DiscoverOpportunitiesUseCase:
    """Presentation 계층에서 호출하는 Opportunity Discovery 진입점."""

    def __init__(
        self,
        *,
        gateway: OpportunityDiscoveryGateway,
        ranking_engine: RankingEngine | None = None,
        strong_score_threshold: float = 65.0,
    ) -> None:
        if not 0 <= strong_score_threshold <= 100:
            raise ValueError(
                "strong_score_threshold는 0 이상 100 이하여야 합니다."
            )

        self._gateway = gateway
        self._ranking_engine = ranking_engine or RankingEngine()
        self._strong_score_threshold = float(strong_score_threshold)

    def execute(
        self,
        *,
        query: str,
        collection_limit: int = 10,
        result_limit: int | None = None,
    ) -> DiscoverOpportunitiesResponse:
        session = DiscoverySession(
            query=query,
            requested_limit=collection_limit,
        )

        if result_limit is not None and result_limit < 1:
            raise ValueError("result_limit은 1 이상이어야 합니다.")

        try:
            discovered_results = self._gateway.discover(
                query=session.query,
                limit=collection_limit,
            )
            ranked_results = tuple(
                self._ranking_engine.rank(
                    discovered_results,
                    limit=result_limit,
                )
            )
        except Exception as error:
            session.fail(error)
            raise

        session.complete()

        return DiscoverOpportunitiesResponse(
            session=session,
            results=ranked_results,
            statistics=DiscoveryStatistics.from_results(
                discovered_results=discovered_results,
                returned_results=ranked_results,
                strong_score_threshold=self._strong_score_threshold,
            ),
        )
