from __future__ import annotations

from presentation.models import DashboardCard


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
            ]
        )

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