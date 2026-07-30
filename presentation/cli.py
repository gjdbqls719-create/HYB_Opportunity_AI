from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TextIO
import sys

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceResult,
    OpportunityIntelligenceStatus,
)
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


def print_opportunity_intelligence_results(
    opportunities: Sequence[OpportunityResult],
    intelligence_results: Sequence[OpportunityIntelligenceResult],
    *,
    output: TextIO | None = None,
) -> None:
    """기존 CLI 결과 뒤에 신규 Opportunity Intelligence를 추가 출력한다."""
    if len(opportunities) != len(intelligence_results):
        raise ValueError(
            "opportunities와 intelligence_results의 길이가 같아야 합니다."
        )

    target = output or sys.stdout

    for opportunity, intelligence in zip(
        opportunities,
        intelligence_results,
        strict=True,
    ):
        print("", file=target)
        print(
            f"[Opportunity Intelligence] {opportunity.product.title}",
            file=target,
        )
        print(
            f"Status: {intelligence.status.value}",
            file=target,
        )

        if intelligence.status is OpportunityIntelligenceStatus.UNAVAILABLE:
            print(
                "Missing inputs: "
                + ", ".join(intelligence.missing_factors),
                file=target,
            )
            continue

        if intelligence.status is OpportunityIntelligenceStatus.FAILED:
            print(
                f"Error: {intelligence.error_message}",
                file=target,
            )
            continue

        report = intelligence.decision_report
        confidence = intelligence.confidence_assessment
        risk = intelligence.risk_assessment

        if report is None or confidence is None or risk is None:
            raise ValueError(
                "evaluated Intelligence 결과에 필수 평가 정보가 없습니다."
            )

        print(
            f"Decision: {report.decision.value}",
            file=target,
        )
        print(
            f"Grade: {report.grade.value}",
            file=target,
        )
        print(
            f"Score: {report.score}",
            file=target,
        )
        print(
            f"Confidence: {confidence.level.value} ({confidence.score})",
            file=target,
        )
        print(
            f"Risk: {risk.level.value} ({risk.safety_score})",
            file=target,
        )
        print(
            f"Next action: {report.recommended_action}",
            file=target,
        )

        if intelligence.trend_assessment is not None:
            print(
                "Trend: "
                f"{intelligence.trend_assessment.level.value}",
                file=target,
            )

        if intelligence.recommendation is not None:
            print(
                "Final recommendation: "
                f"{intelligence.recommendation.level.value}",
                file=target,
            )
            print(
                "Final next action: "
                f"{intelligence.recommendation.next_action}",
                file=target,
            )
