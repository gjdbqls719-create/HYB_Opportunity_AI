from datetime import datetime, timezone
from io import StringIO
from types import SimpleNamespace

from app.cli import (
    _evaluate_opportunity_intelligence,
    render_results,
)
from app.models.product import Product
from engine.confidence import ConfidenceResult
from engine.orchestrator import OpportunityResult
from storage.price_history import PriceHistoryRepository


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
            "estimated_monthly_sales": 200,
            "competitor_count": 20,
            "risk_level": "medium",
        },
        matched_product_count=3,
        price_intelligence=SimpleNamespace(),
        confidence=ConfidenceResult(
            sample_size=3,
            confidence_score=80,
            confidence_multiplier=0.9,
            confidence_level="높음",
            used_fallback_price=False,
            reason="충분한 표본",
        ),
        adjusted_opportunity_score=67.0,
        final_opportunity_score=final_score,
    )


def test_render_results_uses_dashboard_presentation() -> None:
    output = StringIO()
    results = [
        _make_result(
            title="Apple iPhone",
            final_score=72.0,
        )
    ]

    render_results(
        "iphone",
        results,
        intelligence_results=(
            _evaluate_opportunity_intelligence(results)
        ),
        output=output,
    )

    rendered = output.getvalue()

    assert "검색어: iphone" in rendered
    assert "분석 결과: 1개 그룹" in rendered
    assert "TOP OPPORTUNITIES (1 of 1)" in rendered
    assert "#1 ⚪ UNDECIDED" in rendered
    assert "HYB OPPORTUNITY DASHBOARD" in rendered
    assert "Apple iPhone" in rendered
    assert "110.00 USD" in rendered
    assert "30.00 USD" in rendered
    assert "72.00" in rendered
    assert "[Opportunity Intelligence] Apple iPhone" in rendered
    assert "Status: evaluated" in rendered
    assert "Confidence: HIGH (80)" in rendered
    assert "Risk: MEDIUM (50)" in rendered


def test_render_results_respects_top_limit() -> None:
    output = StringIO()
    results = [
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
    ]

    render_results(
        "sample",
        results,
        top=2,
        intelligence_results=(
            _evaluate_opportunity_intelligence(results[:2])
        ),
        output=output,
    )

    rendered = output.getvalue()

    assert "분석 결과: 3개 그룹" in rendered
    assert "표시 결과: 2개" in rendered

    assert "TOP OPPORTUNITIES (2 of 2)" in rendered
    assert "#1 ⚪ UNDECIDED" in rendered
    assert "#2 ⚪ UNDECIDED" in rendered

    assert "First Product" in rendered
    assert "Second Product" in rendered
    assert "Third Product" not in rendered

    assert rendered.count(
        "HYB OPPORTUNITY DASHBOARD"
    ) == 2
    assert rendered.count(
        "[Opportunity Intelligence]"
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


def test_price_history_enables_trend_and_final_recommendation(
    tmp_path,
) -> None:
    output = StringIO()
    result = _make_result(
        title="History Product",
        final_score=80.0,
    )
    repository = PriceHistoryRepository(
        tmp_path / "history.db"
    )
    repository.save_product_price(
        Product(
            marketplace=result.product.marketplace,
            item_id=result.product.item_id,
            title=result.product.title,
            price=120.0,
            currency=result.product.currency,
        ),
        observed_at=datetime(
            2026,
            7,
            29,
            tzinfo=timezone.utc,
        ),
    )
    repository.save_product_price(
        result.product,
        observed_at=datetime(
            2026,
            7,
            30,
            tzinfo=timezone.utc,
        ),
    )

    intelligence_results = (
        _evaluate_opportunity_intelligence(
            [result],
            price_history_repository=repository,
        )
    )
    render_results(
        "history",
        [result],
        intelligence_results=intelligence_results,
        output=output,
    )

    rendered = output.getvalue()

    assert intelligence_results[0].trend_assessment is not None
    assert intelligence_results[0].recommendation is not None
    assert "Trend:" in rendered
    assert "Final recommendation:" in rendered
