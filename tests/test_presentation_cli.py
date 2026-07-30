from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceInput,
    OpportunityIntelligenceResult,
    OpportunityIntelligenceService,
    OpportunityIntelligenceStatus,
)
from app.domain.opportunity import OpportunityFactors
from app.models.product import Product
from engine.orchestrator import OpportunityResult
from presentation.cli import (
    print_dashboard_result,
    print_dashboard_results,
    print_opportunity_intelligence_results,
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


class _CompleteInputAdapter:
    def adapt(self, discovery_result):
        return OpportunityIntelligenceInput(
            factors=OpportunityFactors(
                price_score=Decimal("90"),
                trend_score=Decimal("80"),
                demand_score=Decimal("70"),
                competition_score=Decimal("60"),
                risk_score=Decimal("50"),
            ),
            confidence=Decimal("82"),
        )


def _evaluated_intelligence_result() -> OpportunityIntelligenceResult:
    from app.domain.discovery import DiscoveryResult

    opportunity = _make_result()
    return OpportunityIntelligenceService(
        input_adapter=_CompleteInputAdapter()
    ).evaluate(
        DiscoveryResult(
            product=opportunity.product,
            opportunity_score=opportunity.final_opportunity_score,
        )
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


def test_print_opportunity_intelligence_evaluated_result() -> None:
    output = StringIO()

    print_opportunity_intelligence_results(
        [_make_result()],
        [_evaluated_intelligence_result()],
        output=output,
    )

    rendered = output.getvalue()

    assert "[Opportunity Intelligence] Sample Product" in rendered
    assert "Status: evaluated" in rendered
    assert "Decision: watch" in rendered
    assert "Confidence: HIGH (82)" in rendered
    assert "Risk: MEDIUM (50)" in rendered
    assert "Final recommendation:" not in rendered


def test_print_opportunity_intelligence_reports_non_evaluated_statuses() -> None:
    output = StringIO()
    opportunities = [_make_result(title="Missing"), _make_result(title="Failed")]

    print_opportunity_intelligence_results(
        opportunities,
        [
            OpportunityIntelligenceResult(
                status=OpportunityIntelligenceStatus.UNAVAILABLE,
                missing_factors=("price_score",),
            ),
            OpportunityIntelligenceResult(
                status=OpportunityIntelligenceStatus.FAILED,
                error_message="invalid input",
            ),
        ],
        output=output,
    )

    rendered = output.getvalue()

    assert "Missing inputs: price_score" in rendered
    assert "Error: invalid input" in rendered
