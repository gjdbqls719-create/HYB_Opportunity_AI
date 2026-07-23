from presentation.formatter import (
    format_dashboard_card,
    format_dashboard_cards,
)
from presentation.models import (
    DashboardAIPartner,
    DashboardCard,
    DashboardMemory,
    DashboardMetrics,
    DashboardProduct,
    DashboardRecommendation,
)


def _make_dashboard_card() -> DashboardCard:
    return DashboardCard(
        product=DashboardProduct(
            marketplace="ebay",
            item_id="iphone-1",
            title="Apple iPhone 17 128GB",
            price=500.0,
            shipping_cost=20.0,
            total_cost=520.0,
            currency="USD",
            condition="New",
            url="https://example.com/iphone-1",
            image_url="",
            seller="sample-seller",
            in_stock=True,
        ),
        metrics=DashboardMetrics(
            expected_selling_price=750.0,
            net_profit=130.0,
            roi=25.0,
            opportunity_score=70.0,
            adjusted_opportunity_score=68.0,
            final_opportunity_score=72.0,
            matched_product_count=4,
        ),
        recommendation=DashboardRecommendation(
            grade="BUY",
            action="Buy",
            score=82.0,
            success_probability=75.0,
            summary="구매를 검토할 가치가 있습니다.",
            reasons=(
                "예상 수익성이 양호합니다.",
            ),
            warnings=(
                "배송비를 최종 확인해야 합니다.",
            ),
        ),
        ai_partner=DashboardAIPartner(
            title="HYB AI Partner Report - BUY",
            summary="수익성과 시장 조건이 양호합니다.",
            recommendation="소량 테스트 매입을 권장합니다.",
            next_action="수수료와 배송비를 확인하세요.",
            memory_summary="과거 기록 대비 상위권입니다.",
        ),
        memory=DashboardMemory(
            sample_size=20,
            rank_label="상위권",
            overall_percentile=85.0,
            summary="최근 분석 기록 중 상위 15%입니다.",
        ),
        confidence_level="HIGH",
        trend_direction="UP",
        decision="Buy",
    )


def test_format_dashboard_card_contains_core_metrics() -> None:
    output = format_dashboard_card(
        _make_dashboard_card()
    )

    assert "HYB OPPORTUNITY DASHBOARD" in output
    assert "Apple iPhone 17 128GB" in output
    assert "520.00 USD" in output
    assert "750.00 USD" in output
    assert "130.00 USD" in output
    assert "25.00%" in output
    assert "72.00" in output
    assert "Buy" in output


def test_format_dashboard_card_contains_ai_sections() -> None:
    output = format_dashboard_card(
        _make_dashboard_card()
    )

    assert "AI RECOMMENDATION" in output
    assert "AI PARTNER" in output
    assert "AI MEMORY" in output

    assert "BUY" in output
    assert "소량 테스트 매입을 권장합니다." in output
    assert "과거 기록 대비 상위권입니다." in output
    assert "85.00%" in output


def test_format_dashboard_card_supports_missing_ai_data() -> None:
    original = _make_dashboard_card()

    card = DashboardCard(
        product=original.product,
        metrics=original.metrics,
        recommendation=None,
        ai_partner=None,
        memory=None,
        confidence_level="",
        trend_direction="",
        decision="",
    )

    output = format_dashboard_card(card)

    assert "HYB OPPORTUNITY DASHBOARD" in output
    assert "AI RECOMMENDATION" not in output
    assert "AI PARTNER" not in output
    assert "AI MEMORY" not in output
    assert "Confidence    : -" in output
    assert "Price Trend   : -" in output
    assert "Decision      : -" in output


def test_format_dashboard_cards_handles_empty_list() -> None:
    output = format_dashboard_cards([])

    assert output == "No dashboard results."