from presentation.formatter import format_opportunity_list_card
from presentation.models import OpportunityListCard, OpportunityListItem


def _make_item(
    *,
    rank: int,
    title: str,
    decision: str,
    score: float,
) -> OpportunityListItem:
    return OpportunityListItem(
        rank=rank,
        marketplace="ebay",
        item_id=f"item-{rank}",
        title=title,
        decision=decision,
        score=score,
        net_profit=130.0 - rank,
        roi=25.0 - rank,
        confidence_level="HIGH",
        currency="USD",
        url="",
    )


def test_format_opportunity_list_card_contains_comparison_metrics() -> None:
    card = OpportunityListCard(
        items=(
            _make_item(
                rank=1,
                title="Apple iPhone 17",
                decision="Buy",
                score=91.0,
            ),
            _make_item(
                rank=2,
                title="Sony Headphones",
                decision="Watch",
                score=78.0,
            ),
        ),
        total_count=4,
    )

    output = format_opportunity_list_card(card)

    assert "TOP OPPORTUNITIES (2 of 4)" in output
    assert "#1 🟢 BUY" in output
    assert "Apple iPhone 17" in output
    assert "HYB Score     : 91.00" in output
    assert "Net Profit    : 129.00 USD" in output
    assert "ROI           : 24.00%" in output
    assert "Confidence    : HIGH" in output
    assert "#2 🟡 WATCH" in output
    assert "Sony Headphones" in output


def test_format_opportunity_list_card_handles_empty_card() -> None:
    output = format_opportunity_list_card(
        OpportunityListCard(
            items=(),
            total_count=0,
        )
    )

    assert output == "No opportunity results."
