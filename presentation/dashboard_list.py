from __future__ import annotations

from collections.abc import Iterable

from engine.orchestrator import OpportunityResult
from presentation.dashboard import build_dashboard_card
from presentation.models import (
    OpportunityListCard,
    OpportunityListItem,
)


def build_opportunity_list_card(
    results: Iterable[OpportunityResult],
    *,
    limit: int | None = None,
) -> OpportunityListCard:
    """
    여러 OpportunityResult를 목록용 ViewModel로 변환한다.

    입력 순서를 그대로 유지하며 별도의 점수 계산이나 재정렬은
    수행하지 않는다. limit이 주어지면 앞에서부터 해당 개수만
    표시하지만 total_count에는 전체 입력 개수를 보관한다.
    """
    result_list = list(results)
    selected_results = _apply_limit(
        result_list,
        limit=limit,
    )

    items = tuple(
        _build_opportunity_list_item(
            result,
            rank=index,
        )
        for index, result in enumerate(
            selected_results,
            start=1,
        )
    )

    return OpportunityListCard(
        items=items,
        total_count=len(result_list),
    )


def _build_opportunity_list_item(
    result: OpportunityResult,
    *,
    rank: int,
) -> OpportunityListItem:
    card = build_dashboard_card(result)

    return OpportunityListItem(
        rank=rank,
        marketplace=card.product.marketplace,
        item_id=card.product.item_id,
        title=card.product.title,
        decision=card.decision,
        score=card.metrics.final_opportunity_score,
        net_profit=card.metrics.net_profit,
        roi=card.metrics.roi,
        confidence_level=card.confidence_level,
        currency=card.product.currency,
        url=card.product.url,
    )


def _apply_limit(
    results: list[OpportunityResult],
    *,
    limit: int | None,
) -> list[OpportunityResult]:
    if limit is None:
        return results

    if limit < 0:
        raise ValueError("limit must be zero or greater")

    return results[:limit]
