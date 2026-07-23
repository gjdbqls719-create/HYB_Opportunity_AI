from types import SimpleNamespace

from app.models.product import Product
from engine.orchestrator import OpportunityResult
from presentation.dashboard import (
    build_dashboard_card,
    build_dashboard_cards,
)


def _make_opportunity_result() -> OpportunityResult:
    product = Product(
        marketplace="ebay",
        item_id="iphone-1",
        title="Apple iPhone 17 128GB",
        price=500.0,
        shipping_cost=20.0,
        currency="USD",
        condition="New",
        url="https://example.com/iphone-1",
        image_url="https://example.com/iphone-1.jpg",
        seller="sample-seller",
        in_stock=True,
    )

    recommendation = SimpleNamespace(
        grade="BUY",
        action="Buy",
        score=82.0,
        success_probability=75.0,
        summary="구매를 검토할 가치가 있습니다.",
        reasons=(
            "예상 수익성이 양호합니다.",
            "시장 가격보다 매입가가 낮습니다.",
        ),
        warnings=(
            "배송비를 최종 확인해야 합니다.",
        ),
    )

    ai_partner_report = SimpleNamespace(
        title="HYB AI Partner Report - BUY",
        summary="수익성과 시장 조건이 양호합니다.",
        recommendation="소량 테스트 매입을 권장합니다.",
        next_action="수수료와 배송비를 확인하세요.",
        memory_summary="과거 기록 대비 상위권입니다.",
    )

    memory_insight = SimpleNamespace(
        sample_size=20,
        rank_label="상위권",
        overall_percentile=85.0,
        summary="최근 분석 기록 중 상위 15%입니다.",
    )

    confidence = SimpleNamespace(
        level="HIGH",
    )

    price_trend = SimpleNamespace(
        direction="UP",
    )

    decision_report = SimpleNamespace(
        decision="BUY",
    )

    return OpportunityResult(
        product=product,
        analysis={
            "expected_selling_price": 750.0,
            "net_profit": 130.0,
            "roi": 25.0,
            "opportunity_score": 70.0,
        },
        matched_product_count=4,
        price_intelligence=SimpleNamespace(),
        confidence=confidence,
        adjusted_opportunity_score=68.0,
        price_trend=price_trend,
        trend_score=SimpleNamespace(),
        trend_score_adjustment=4.0,
        final_opportunity_score=72.0,
        ai_recommendation=recommendation,
        decision_report=decision_report,
        ai_partner_report=ai_partner_report,
        memory_insight=memory_insight,
    )


def test_build_dashboard_card() -> None:
    result = _make_opportunity_result()

    card = build_dashboard_card(result)

    assert card.product.title == (
        "Apple iPhone 17 128GB"
    )
    assert card.product.total_cost == 520.0
    assert card.product.marketplace == "ebay"

    assert (
        card.metrics.expected_selling_price
        == 750.0
    )
    assert card.metrics.net_profit == 130.0
    assert card.metrics.roi == 25.0
    assert (
        card.metrics.opportunity_score
        == 70.0
    )
    assert (
        card.metrics.adjusted_opportunity_score
        == 68.0
    )
    assert (
        card.metrics.final_opportunity_score
        == 72.0
    )
    assert card.metrics.matched_product_count == 4

    assert card.recommendation is not None
    assert card.recommendation.grade == "BUY"
    assert card.recommendation.action == "Buy"
    assert card.recommendation.score == 82.0
    assert (
        card.recommendation.success_probability
        == 75.0
    )

    assert card.ai_partner is not None
    assert (
        card.ai_partner.next_action
        == "수수료와 배송비를 확인하세요."
    )

    assert card.memory is not None
    assert card.memory.sample_size == 20
    assert (
        card.memory.overall_percentile
        == 85.0
    )

    assert card.confidence_level == "HIGH"
    assert card.trend_direction == "UP"
    assert card.decision == "Buy"


def test_build_dashboard_card_without_optional_results() -> None:
    result = _make_opportunity_result()

    result.ai_recommendation = None
    result.ai_partner_report = None
    result.memory_insight = None
    result.confidence = None
    result.price_trend = None
    result.trend_score = None
    result.decision_report = None

    card = build_dashboard_card(result)

    assert card.recommendation is None
    assert card.ai_partner is None
    assert card.memory is None
    assert card.confidence_level == ""
    assert card.trend_direction == ""
    assert card.decision == ""


def test_build_dashboard_cards_preserves_order() -> None:
    first_result = _make_opportunity_result()
    second_result = _make_opportunity_result()

    second_result.product = Product(
        marketplace="amazon",
        item_id="product-2",
        title="Second Product",
        price=100.0,
        currency="USD",
    )

    cards = build_dashboard_cards(
        [
            first_result,
            second_result,
        ]
    )

    assert len(cards) == 2
    assert cards[0].product.title == (
        "Apple iPhone 17 128GB"
    )
    assert cards[1].product.title == (
        "Second Product"
    )


def test_build_dashboard_card_converts_to_dict() -> None:
    result = _make_opportunity_result()

    data = build_dashboard_card(
        result
    ).to_dict()

    assert data["product"]["title"] == (
        "Apple iPhone 17 128GB"
    )
    assert data["metrics"]["net_profit"] == 130.0

    assert data["recommendation"] is not None
    assert data["recommendation"]["grade"] == "BUY"

    assert data["ai_partner"] is not None
    assert (
        data["ai_partner"]["memory_summary"]
        == "과거 기록 대비 상위권입니다."
    )

    assert data["memory"] is not None
    assert (
        data["memory"]["rank_label"]
        == "상위권"
    )