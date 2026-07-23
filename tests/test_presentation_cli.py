from io import StringIO
from types import SimpleNamespace

from app.models.product import Product
from engine.orchestrator import OpportunityResult
from presentation.cli import (
    print_dashboard_result,
    print_dashboard_results,
)


def _make_result(
    *,
    title: str = "Sample Product",
) -> OpportunityResult:
    product = Product(
        marketplace="ebay",
        item_id="item-1",
        title=title,
        price=100.0,
        shipping_cost=10.0,
        currency="USD",
    )

    return OpportunityResult(
        product=product,
        analysis={
            "expected_selling_price": 160.0,
            "net_profit": 30.0,
            "roi": 27.27,
            "opportunity_score": 65.0,
        },
        matched_product_count=3,
        price_intelligence=SimpleNamespace(),
        adjusted_opportunity_score=67.0,
        final_opportunity_score=70.0,
    )


def test_print_dashboard_result() -> None:
    output = StringIO()

    print_dashboard_result(
        _make_result(),
        output=output,
    )

    rendered = output.getvalue()

    assert "HYB OPPORTUNITY DASHBOARD" in rendered
    assert "Sample Product" in rendered
    assert "110.00 USD" in rendered
    assert "30.00 USD" in rendered
    assert "70.00" in rendered


def test_print_dashboard_results() -> None:
    output = StringIO()

    print_dashboard_results(
        [
            _make_result(
                title="First Product",
            ),
            _make_result(
                title="Second Product",
            ),
        ],
        output=output,
    )

    rendered = output.getvalue()

    assert rendered.count(
        "HYB OPPORTUNITY DASHBOARD"
    ) == 2

    assert "First Product" in rendered
    assert "Second Product" in rendered


def test_print_dashboard_results_handles_empty_results() -> None:
    output = StringIO()

    print_dashboard_results(
        [],
        output=output,
    )

    assert output.getvalue().strip() == (
        "No dashboard results."
    )