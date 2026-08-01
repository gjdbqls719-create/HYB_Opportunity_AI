from __future__ import annotations

from presentation.models import (
    DashboardCard,
    OpportunityListCard,
    OpportunityListItem,
)


DEFAULT_WIDTH = 60


def format_dashboard_card(
    card: DashboardCard,
    *,
    width: int = DEFAULT_WIDTH,
) -> str:
    """
    DashboardCard 하나를 사람이 읽기 쉬운 문자열로 변환한다.

    특정 터미널 라이브러리나 웹 프레임워크에 의존하지 않으므로
    CLI, 로그, 텍스트 보고서에서 공통으로 사용할 수 있다.
    """
    safe_width = max(width, 40)
    separator = "=" * safe_width
    section_separator = "-" * safe_width

    currency = card.product.currency or ""
    recommendation = card.recommendation
    ai_partner = card.ai_partner
    memory = card.memory

    lines = [
        separator,
        "HYB OPPORTUNITY DASHBOARD",
        separator,
        *_format_hero_summary(
            card,
            currency=currency,
            separator=section_separator,
        ),
        section_separator,
        "OPPORTUNITY DETAILS",
        _format_row(
            "Product",
            card.product.title,
        ),
        _format_row(
            "Marketplace",
            card.product.marketplace.upper(),
        ),
        _format_row(
            "Item ID",
            card.product.item_id or "-",
        ),
        _format_row(
            "Condition",
            card.product.condition or "-",
        ),
        _format_money_row(
            "Product Price",
            card.product.price,
            currency,
        ),
        _format_money_row(
            "Shipping",
            card.product.shipping_cost,
            currency,
        ),
        _format_money_row(
            "Purchase Cost",
            card.product.total_cost,
            currency,
        ),
        _format_money_row(
            "Expected Sale",
            card.metrics.expected_selling_price,
            currency,
        ),
        _format_money_row(
            "Landed Cost",
            card.metrics.landed_cost,
            currency,
        ),
        _format_money_row(
            "Selling Cost",
            card.metrics.selling_cost,
            currency,
        ),
        _format_money_row(
            "Total Cost",
            card.metrics.total_cost,
            currency,
        ),
        _format_money_row(
            "Net Profit",
            card.metrics.net_profit,
            currency,
        ),
        _format_percentage_row(
            "Margin",
            card.metrics.margin_rate,
        ),
        _format_percentage_row(
            "ROI",
            card.metrics.roi,
        ),
        _format_percentage_row(
            "Landed ROI",
            card.metrics.landed_cost_roi,
        ),
        _format_number_row(
            "Base Score",
            card.metrics.opportunity_score,
        ),
        _format_number_row(
            "Adjusted Score",
            card.metrics.adjusted_opportunity_score,
        ),
        _format_number_row(
            "Final Score",
            card.metrics.final_opportunity_score,
        ),
        _format_row(
            "Matched Products",
            str(card.metrics.matched_product_count),
        ),
        _format_row(
            "Confidence",
            card.confidence_level or "-",
        ),
        _format_row(
            "Price Trend",
            card.trend_direction or "-",
        ),
        _format_row(
            "Decision",
            card.decision or "-",
        ),
    ]

    if card.decision_timeline:
        lines.extend(
            [
                section_separator,
                "DECISION TIMELINE",
            ]
        )

        for index, step in enumerate(
            card.decision_timeline,
            start=1,
        ):
            lines.append(
                f"{index}. {step.title}"
            )
            lines.append(
                _format_multiline_value(
                    "Result",
                    step.summary,
                )
            )

            if index < len(
                card.decision_timeline
            ):
                lines.append("   |")
                lines.append("   v")

    if recommendation is not None:
        lines.extend(
            [
                section_separator,
                "AI RECOMMENDATION",
                _format_row(
                    "Grade",
                    recommendation.grade or "-",
                ),
                _format_row(
                    "Action",
                    recommendation.action or "-",
                ),
                _format_number_row(
                    "AI Score",
                    recommendation.score,
                ),
                _format_percentage_row(
                    "Success Chance",
                    recommendation.success_probability,
                ),
                _format_multiline_value(
                    "Summary",
                    recommendation.summary,
                ),
                _format_row(
                    "Safety Status",
                    recommendation.safety_status or "NOT_EVALUATED",
                ),
            ]
        )

        if recommendation.safety_reasons:
            lines.append("Safety Reasons")
            for reason in recommendation.safety_reasons:
                lines.append(f"  - {reason}")

        if recommendation.reasons:
            lines.append("Reasons")

            for reason in recommendation.reasons:
                lines.append(f"  - {reason}")

        if recommendation.warnings:
            lines.append("Warnings")

            for warning in recommendation.warnings:
                lines.append(f"  - {warning}")

    if ai_partner is not None:
        lines.extend(
            [
                section_separator,
                "AI PARTNER",
                _format_multiline_value(
                    "Title",
                    ai_partner.title,
                ),
                _format_multiline_value(
                    "Summary",
                    ai_partner.summary,
                ),
                _format_multiline_value(
                    "Recommendation",
                    ai_partner.recommendation,
                ),
                _format_multiline_value(
                    "Next Action",
                    ai_partner.next_action,
                ),
            ]
        )

        if ai_partner.memory_summary:
            lines.append(
                _format_multiline_value(
                    "Memory",
                    ai_partner.memory_summary,
                )
            )

    if memory is not None:
        lines.extend(
            [
                section_separator,
                "AI MEMORY",
                _format_row(
                    "Sample Size",
                    str(memory.sample_size),
                ),
                _format_row(
                    "Rank",
                    memory.rank_label or "-",
                ),
                _format_percentage_row(
                    "Percentile",
                    memory.overall_percentile,
                ),
                _format_multiline_value(
                    "Summary",
                    memory.summary,
                ),
            ]
        )

    if card.product.url:
        lines.extend(
            [
                section_separator,
                _format_multiline_value(
                    "Product URL",
                    card.product.url,
                ),
            ]
        )

    lines.append(separator)

    return "\n".join(lines)


def format_opportunity_list_card(
    card: OpportunityListCard,
    *,
    width: int = DEFAULT_WIDTH,
) -> str:
    """
    OpportunityListCard를 빠른 비교용 CLI 문자열로 변환한다.

    목록은 ViewModel에 저장된 순서를 그대로 표시하며 점수 계산이나
    재정렬을 수행하지 않는다.
    """
    if not card.items:
        return "No opportunity results."

    safe_width = max(width, 40)
    separator = "=" * safe_width
    item_separator = "-" * safe_width

    lines = [
        separator,
        f"TOP OPPORTUNITIES ({len(card.items)} of {card.total_count})",
        separator,
    ]

    for index, item in enumerate(card.items):
        lines.extend(_format_opportunity_list_item(item))

        if index < len(card.items) - 1:
            lines.append(item_separator)

    lines.append(separator)
    return "\n".join(lines)


def _format_opportunity_list_item(
    item: OpportunityListItem,
) -> list[str]:
    decision = item.decision.strip().upper() or "UNDECIDED"
    icon = _decision_icon(decision)
    marketplace = item.marketplace.strip().upper() or "-"

    return [
        f"#{item.rank} {icon} {decision}",
        item.title.strip() or "-",
        _format_row("Marketplace", marketplace),
        _format_number_row("HYB Score", item.score),
        _format_money_row("Net Profit", item.net_profit, item.currency),
        _format_percentage_row("ROI", item.roi),
        _format_row(
            "Confidence",
            item.confidence_level.strip() or "-",
        ),
    ]


def _decision_icon(decision: str) -> str:
    normalized = decision.strip().upper()

    if normalized in {"BUY", "STRONG BUY"}:
        return "🟢"

    if normalized in {"WATCH", "HOLD", "REVIEW", "검토"}:
        return "🟡"

    if normalized in {"SKIP", "AVOID", "SELL"}:
        return "🔴"

    return "⚪"


def format_dashboard_cards(
    cards: list[DashboardCard],
    *,
    width: int = DEFAULT_WIDTH,
) -> str:
    """
    여러 DashboardCard를 하나의 텍스트 보고서로 변환한다.
    """
    if not cards:
        return "No dashboard results."

    formatted_cards = [
        format_dashboard_card(
            card,
            width=width,
        )
        for card in cards
    ]

    return "\n\n".join(formatted_cards)


def _format_row(
    label: str,
    value: str,
) -> str:
    cleaned_value = value.strip() if value else "-"

    return f"{label:<14}: {cleaned_value}"


def _format_money_row(
    label: str,
    value: float,
    currency: str,
) -> str:
    formatted_value = f"{value:,.2f}"

    if currency:
        formatted_value = (
            f"{formatted_value} {currency}"
        )

    return _format_row(
        label,
        formatted_value,
    )


def _format_percentage_row(
    label: str,
    value: float,
) -> str:
    return _format_row(
        label,
        f"{value:,.2f}%",
    )


def _format_number_row(
    label: str,
    value: float,
) -> str:
    return _format_row(
        label,
        f"{value:,.2f}",
    )


def _format_multiline_value(
    label: str,
    value: str,
) -> str:
    cleaned_value = value.strip() if value else "-"

    if "\n" not in cleaned_value:
        return _format_row(
            label,
            cleaned_value,
        )

    value_lines = cleaned_value.splitlines()
    output_lines = [
        _format_row(
            label,
            value_lines[0],
        )
    ]

    indentation = " " * 16

    for line in value_lines[1:]:
        output_lines.append(
            f"{indentation}{line}"
        )

    return "\n".join(output_lines)

def _format_hero_summary(
    card: DashboardCard,
    *,
    currency: str,
    separator: str,
) -> list[str]:
    """
    Dashboard의 핵심 판단을 첫 화면에 요약한다.

    엔진 결과를 재계산하지 않고 DashboardCard에 이미
    포함된 판단, 점수, 수익성, 근거, 다음 행동만 표시한다.
    """
    decision = _resolve_hero_decision(card)
    next_action = _resolve_next_action(card)
    reasons = _collect_hero_reasons(card)

    lines = [
        "HERO SUMMARY",
        _format_row("Decision", decision),
        _format_number_row(
            "HYB Score",
            card.metrics.final_opportunity_score,
        ),
        _format_money_row(
            "Net Profit",
            card.metrics.net_profit,
            currency,
        ),
        _format_percentage_row(
            "ROI",
            card.metrics.roi,
        ),
        _format_row(
            "Confidence",
            card.confidence_level or "-",
        ),
    ]

    if card.recommendation is not None:
        lines.append(
            _format_percentage_row(
                "Success Chance",
                card.recommendation.success_probability,
            )
        )

    if reasons:
        lines.extend(
            [
                separator,
                "WHY THIS DECISION",
            ]
        )

        for reason in reasons:
            lines.append(f"  - {reason}")

    lines.extend(
        [
            separator,
            "NEXT ACTION",
            _format_multiline_value(
                "Action",
                next_action,
            ),
        ]
    )

    return lines


def _resolve_hero_decision(
    card: DashboardCard,
) -> str:
    recommendation = card.recommendation

    candidates = [
        (
            recommendation.grade
            if recommendation is not None
            else ""
        ),
        card.decision,
        (
            recommendation.action
            if recommendation is not None
            else ""
        ),
    ]

    for candidate in candidates:
        cleaned = candidate.strip()

        if cleaned:
            return cleaned.upper()

    return "UNDECIDED"


def _resolve_next_action(
    card: DashboardCard,
) -> str:
    if card.ai_partner is not None:
        next_action = card.ai_partner.next_action.strip()

        if next_action:
            return next_action

    if card.recommendation is not None:
        action = card.recommendation.action.strip()

        if action:
            return action

    return "추가 데이터를 확인한 뒤 다시 분석하세요."


def _collect_hero_reasons(
    card: DashboardCard,
    *,
    limit: int = 4,
) -> tuple[str, ...]:
    candidates: list[str] = []

    if card.recommendation is not None:
        candidates.extend(card.recommendation.reasons)

        if card.recommendation.summary:
            candidates.append(
                card.recommendation.summary
            )

    for step in card.decision_timeline:
        if step.stage in {
            "confidence",
            "recommendation",
            "ai_partner",
        }:
            continue

        candidates.append(step.summary)

    unique_reasons: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        cleaned = candidate.strip()

        if not cleaned:
            continue

        normalized = cleaned.casefold()

        if normalized in seen:
            continue

        seen.add(normalized)
        unique_reasons.append(cleaned)

        if len(unique_reasons) >= limit:
            break

    return tuple(unique_reasons)
