from io import StringIO
from types import SimpleNamespace

from app.cli import render_results
from app.models.product import Product
from engine.orchestrator import OpportunityResult


def _make_result(
    *,
    title: str,
    final_score: float,
) -> OpportunityResult:
    return OpportunityResult(
        product=Product(
            marketplace="ebay",
            item_id=title.lower().replace(
                " ",
                "-",
            ),
            title=title,
            price=100.0,
            shipping_cost=10.0,
            currency="USD",
            condition="New",
        ),
        analysis={
            "expected_selling_price": 160.0,
            "net_profit": 30.0,
            "roi": 27.27,
            "opportunity_score": 65.0,
        },
        matched_product_count=3,
        price_intelligence=SimpleNamespace(),
        adjusted_opportunity_score=67.0,
        final_opportunity_score=final_score,
    )


def test_render_results_uses_dashboard_presentation() -> None:
    output = StringIO()

    render_results(
        "iphone",
        [
            _make_result(
                title="Apple iPhone",
                final_score=72.0,
            )
        ],
        output=output,
    )

    rendered = output.getvalue()

    assert "검색어: iphone" in rendered
    assert "분석 결과: 1개 그룹" in rendered
    assert "HYB OPPORTUNITY DASHBOARD" in rendered
    assert "Apple iPhone" in rendered
    assert "110.00 USD" in rendered
    assert "30.00 USD" in rendered
    assert "72.00" in rendered


def test_render_results_respects_top_limit() -> None:
    output = StringIO()

    render_results(
        "sample",
        [
            _make_result(
                title="First Product",
                final_score=80.0,
            ),
            _make_result(
                title="Second Product",
                final_score=70.0,
            ),
            _make_result(
                title="Third Product",
                final_score=60.0,
            ),
        ],
        top=2,
        output=output,
    )

    rendered = output.getvalue()

    assert "분석 결과: 3개 그룹" in rendered
    assert "표시 결과: 2개" in rendered

    assert "First Product" in rendered
    assert "Second Product" in rendered
    assert "Third Product" not in rendered

    assert rendered.count(
        "HYB OPPORTUNITY DASHBOARD"
    ) == 2


def test_render_results_handles_empty_results() -> None:
    output = StringIO()

    render_results(
        "missing-product",
        [],
        output=output,
    )

    rendered = output.getvalue()

    assert "분석 결과: 0개 그룹" in rendered
    assert "표시 결과: 0개" in rendered
    assert "No dashboard results." in rendered