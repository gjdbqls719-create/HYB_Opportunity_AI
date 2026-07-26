from __future__ import annotations

from dataclasses import dataclass

from app.domain.discovery import DiscoveryResult


@dataclass(slots=True, frozen=True)
class DiscoveryStatistics:
    """Application 실행에서 외부에 공개할 운영 통계."""

    discovered_count: int
    returned_count: int
    strong_opportunity_count: int

    @classmethod
    def from_results(
        cls,
        *,
        discovered_results: list[DiscoveryResult],
        returned_results: tuple[DiscoveryResult, ...],
        strong_score_threshold: float,
    ) -> DiscoveryStatistics:
        return cls(
            discovered_count=len(discovered_results),
            returned_count=len(returned_results),
            strong_opportunity_count=sum(
                result.opportunity_score >= strong_score_threshold
                for result in returned_results
            ),
        )
