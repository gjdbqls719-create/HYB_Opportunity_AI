from __future__ import annotations

from collections.abc import Iterable

from app.domain.discovery.models import DiscoveryResult


class RankingEngine:
    """Discovery 결과를 사업 우선순위에 따라 정렬한다."""

    def rank(
        self,
        results: Iterable[DiscoveryResult],
        *,
        limit: int | None = None,
    ) -> list[DiscoveryResult]:
        if limit is not None and limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")

        ordered = sorted(
            results,
            key=lambda result: (
                -result.opportunity_score,
                -result.matched_product_count,
                result.product.total_cost,
                result.product.title.casefold(),
                result.identity_key,
            ),
        )

        if limit is not None:
            ordered = ordered[:limit]

        return [
            result.with_rank(index)
            for index, result in enumerate(ordered, start=1)
        ]
