from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO
import sys

from engine.orchestrator import OpportunityResult
from presentation.dashboard_list import (
    build_opportunity_list_card,
)
from presentation.dashboard import (
    build_dashboard_card,
    build_dashboard_cards,
)
from presentation.formatter import (
    format_dashboard_card,
    format_dashboard_cards,
    format_opportunity_list_card,
)


def print_dashboard_result(
    result: OpportunityResult,
    *,
    output: TextIO | None = None,
) -> None:
    """
    OpportunityResult 하나를 Dashboard 형식으로 출력한다.
    """
    target = output or sys.stdout
    card = build_dashboard_card(result)

    print(
        format_dashboard_card(card),
        file=target,
    )


def print_dashboard_results(
    results: Iterable[OpportunityResult],
    *,
    output: TextIO | None = None,
) -> None:
    """
    여러 OpportunityResult를 Dashboard 형식으로 출력한다.
    """
    target = output or sys.stdout
    cards = build_dashboard_cards(results)

    print(
        format_dashboard_cards(cards),
        file=target,
    )

def print_opportunity_results(
    results: Iterable[OpportunityResult],
    *,
    output: TextIO | None = None,
) -> None:
    """
    여러 기회를 비교 목록으로 먼저 보여준 뒤 상세 Dashboard를 출력한다.
    """
    target = output or sys.stdout
    result_list = list(results)
    list_card = build_opportunity_list_card(result_list)

    print(
        format_opportunity_list_card(list_card),
        file=target,
    )
    print("", file=target)

    print_dashboard_results(
        result_list,
        output=target,
    )
