from presentation.models import (
    DashboardAIPartner,
    DashboardCard,
    DashboardMemory,
    DashboardMetrics,
    DashboardProduct,
    DashboardRecommendation,
)


def test_dashboard_card_converts_to_dict() -> None:
    product = DashboardProduct(
        marketplace="ebay",
        item_id="item-1",
        title="Apple iPhone 17 128GB",
        price=500.0,
        shipping_cost=20.0,
        total_cost=520.0,
        currency="USD",
        condition="New",
        url="https://example.com/item-1",
        image_url="https://example.com/item-1.jpg",
        seller="sample-seller",
        in_stock=True,
    )

    metrics = DashboardMetrics(
        expected_selling_price=750.0,
        net_profit=130.0,
        roi=25.0,
        opportunity_score=70.0,
        adjusted_opportunity_score=68.0,
        final_opportunity_score=72.0,
        matched_product_count=4,
    )

    recommendation = DashboardRecommendation(
        grade="BUY",
        action="Buy",
        score=82.0,
        success_probability=75.0,
        summary="구매를 검토할 가치가 있습니다.",
        reasons=(
            "예상 수익성이 양호합니다.",
            "과거 기록 대비 점수가 높습니다.",
        ),
        warnings=(
            "배송비를 최종 확인해야 합니다.",
        ),
    )

    ai_partner = DashboardAIPartner(
        title="HYB AI Partner Report - BUY",
        summary="수익성과 시장 안정성이 양호합니다.",
        recommendation="소량 테스트 매입을 권장합니다.",
        next_action="판매 수수료와 배송비를 확인하세요.",
        memory_summary="과거 기록 대비 상위권입니다.",
    )

    memory = DashboardMemory(
        sample_size=10,
        rank_label="A",
        overall_percentile=85.0,
        summary="최근 분석 기록 중 상위 15%입니다.",
    )

    card = DashboardCard(
        product=product,
        metrics=metrics,
        recommendation=recommendation,
        ai_partner=ai_partner,
        memory=memory,
        confidence_level="HIGH",
        trend_direction="UP",
        decision="BUY",
    )

    data = card.to_dict()

    assert data["product"]["title"] == (
        "Apple iPhone 17 128GB"
    )
    assert data["product"]["total_cost"] == 520.0

    assert data["metrics"]["net_profit"] == 130.0
    assert (
        data["metrics"]["final_opportunity_score"]
        == 72.0
    )

    assert data["recommendation"] is not None
    assert data["recommendation"]["grade"] == "BUY"
    assert data["recommendation"]["reasons"] == [
        "예상 수익성이 양호합니다.",
        "과거 기록 대비 점수가 높습니다.",
    ]

    assert data["ai_partner"] is not None
    assert (
        data["ai_partner"]["next_action"]
        == "판매 수수료와 배송비를 확인하세요."
    )

    assert data["memory"] is not None
    assert data["memory"]["sample_size"] == 10
    assert (
        data["memory"]["overall_percentile"]
        == 85.0
    )

    assert data["confidence_level"] == "HIGH"
    assert data["trend_direction"] == "UP"
    assert data["decision"] == "BUY"


def test_dashboard_card_supports_optional_ai_data() -> None:
    card = DashboardCard(
        product=DashboardProduct(
            marketplace="amazon",
            item_id="item-2",
            title="Sample Product",
            price=30.0,
            shipping_cost=0.0,
            total_cost=30.0,
            currency="USD",
            condition="New",
            url="",
            image_url="",
            seller="",
            in_stock=True,
        ),
        metrics=DashboardMetrics(
            expected_selling_price=40.0,
            net_profit=5.0,
            roi=16.7,
            opportunity_score=40.0,
            adjusted_opportunity_score=40.0,
            final_opportunity_score=40.0,
            matched_product_count=1,
        ),
        recommendation=None,
        ai_partner=None,
        memory=None,
        confidence_level="",
        trend_direction="",
        decision="",
    )

    data = card.to_dict()

    assert data["recommendation"] is None
    assert data["ai_partner"] is None
    assert data["memory"] is None