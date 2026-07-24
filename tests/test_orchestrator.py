from app.models import Product
from engine.ai_memory import HistoricalOpportunity
from engine.orchestrator import (
    find_best_opportunities,
    group_similar_products,
)


def make_product(
    item_id: str,
    title: str,
    price: float,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=title,
        price=price,
        currency="USD",
        condition="New",
        url=f"https://example.com/{item_id}",
    )


def test_group_similar_products() -> None:
    products = [
        make_product(
            "1",
            "Apple iPhone 17 128GB Black",
            800.0,
        ),
        make_product(
            "2",
            "Apple iPhone17 Black 128 GB",
            750.0,
        ),
        make_product(
            "3",
            "Samsung Galaxy Buds Pro White",
            120.0,
        ),
    ]

    groups = group_similar_products(products)

    assert len(groups) == 2

    iphone_group = next(
        group
        for group in groups
        if "iphone" in group.representative.title.lower()
    )

    assert len(iphone_group.products) == 2
    assert iphone_group.representative.item_id == "2"
    assert iphone_group.representative.price == 750.0


def test_find_best_opportunities(
    monkeypatch,
) -> None:
    products = [
        make_product(
            "1",
            "Apple iPhone 17 128GB Black",
            800.0,
        ),
        make_product(
            "2",
            "Apple iPhone17 Black 128 GB",
            750.0,
        ),
        make_product(
            "3",
            "Samsung Galaxy Buds Pro White",
            120.0,
        ),
    ]

    def fake_search_products(
        query: str,
        limit: int,
    ) -> list[Product]:
        assert query == "electronics"
        assert limit == 10
        return products

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        fake_search_products,
    )

    results = find_best_opportunities(
        query="electronics",
        limit=10,
    )

    assert len(results) == 2

    iphone_result = next(
        result
        for result in results
        if "iphone" in result.product.title.lower()
    )

    assert iphone_result.product.item_id == "2"
    assert iphone_result.matched_product_count == 2
    assert iphone_result.analysis[
        "opportunity_score"
    ] >= 0


def test_find_best_opportunities_uses_ai_memory(
    monkeypatch,
) -> None:
    products = [
        make_product(
            "memory-1",
            "Apple iPhone 17 128GB Black",
            500.0,
        ),
    ]

    history = [
        HistoricalOpportunity(
            opportunity_score=10.0,
            roi=5.0,
            net_profit=20.0,
            success_probability=30.0,
        ),
        HistoricalOpportunity(
            opportunity_score=20.0,
            roi=10.0,
            net_profit=40.0,
            success_probability=40.0,
        ),
        HistoricalOpportunity(
            opportunity_score=30.0,
            roi=15.0,
            net_profit=60.0,
            success_probability=50.0,
        ),
    ]

    def fake_search_products(
        query: str,
        limit: int,
    ) -> list[Product]:
        assert query == "iphone"
        assert limit == 10
        return products

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        fake_search_products,
    )

    results = find_best_opportunities(
        query="iphone",
        limit=10,
        ai_memory_history=history,
    )

    assert len(results) == 1

    result = results[0]

    assert result.memory_insight is not None
    assert result.memory_insight.sample_size == 3

    assert result.ai_partner_report is not None
    assert (
        result.ai_partner_report.memory_summary
        == result.memory_insight.summary
    )
    assert (
        result.ai_partner_report.memory_summary
        != ""
    )

    assert (
        result.analysis["ai_memory_summary"]
        == result.memory_insight.summary
    )
    assert (
        result.analysis["ai_memory_rank"]
        == result.memory_insight.rank_label
    )
    assert (
        result.analysis["ai_memory_percentile"]
        == result.memory_insight.overall_percentile
    )


def test_find_best_opportunities_loads_ai_memory_from_repository(
    monkeypatch,
) -> None:
    products = [
        make_product(
            "repository-memory-1",
            "Apple iPhone 17 128GB Black",
            500.0,
        ),
    ]

    repository_history = [
        HistoricalOpportunity(
            opportunity_score=15.0,
            roi=8.0,
            net_profit=30.0,
            success_probability=35.0,
        ),
        HistoricalOpportunity(
            opportunity_score=25.0,
            roi=12.0,
            net_profit=50.0,
            success_probability=45.0,
        ),
    ]

    class FakeOpportunityHistoryRepository:
        def __init__(self) -> None:
            self.load_call_count = 0

        def load_ai_memory_history(
            self,
            *,
            limit: int = 500,
        ) -> list[HistoricalOpportunity]:
            assert limit == 500
            self.load_call_count += 1
            return repository_history

    repository = FakeOpportunityHistoryRepository()

    def fake_search_products(
        query: str,
        limit: int,
    ) -> list[Product]:
        assert query == "iphone"
        assert limit == 10
        return products

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        fake_search_products,
    )

    results = find_best_opportunities(
        query="iphone",
        limit=10,
        opportunity_history_repository=repository,
    )

    assert repository.load_call_count == 1
    assert len(results) == 1

    result = results[0]

    assert result.memory_insight is not None
    assert result.memory_insight.sample_size == 2

    assert result.ai_partner_report is not None
    assert (
        result.ai_partner_report.memory_summary
        == result.memory_insight.summary
    )

    assert (
        result.analysis["ai_memory_summary"]
        == result.memory_insight.summary
    )


def test_empty_query_is_rejected() -> None:
    try:
        find_best_opportunities("   ")
    except ValueError as error:
        assert str(error) == "검색어를 입력해야 합니다."
    else:
        raise AssertionError(
            "빈 검색어는 ValueError를 발생시켜야 합니다."
        )


def test_search_products_continues_when_ebay_fails(
    monkeypatch,
) -> None:
    amazon_product = make_product(
        "amazon-1",
        "Amazon Product",
        50.0,
    )
    warnings: list[tuple[str, str]] = []

    def failing_ebay_search(**kwargs):
        raise RuntimeError(
            "missing eBay credentials"
        )

    def successful_amazon_search(**kwargs):
        return [amazon_product]

    monkeypatch.setattr(
        "engine.orchestrator.search_ebay_products",
        failing_ebay_search,
    )
    monkeypatch.setattr(
        "engine.orchestrator.search_amazon_products",
        successful_amazon_search,
    )

    from engine.orchestrator import search_products

    products = search_products(
        "mouse",
        error_handler=lambda marketplace, error: warnings.append(
            (
                marketplace,
                str(error),
            )
        ),
    )

    assert products == [amazon_product]
    assert warnings == [
        (
            "ebay",
            "missing eBay credentials",
        )
    ]


def test_search_products_raises_when_all_marketplaces_fail(
    monkeypatch,
) -> None:
    def failing_search(**kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(
        "engine.orchestrator.search_ebay_products",
        failing_search,
    )
    monkeypatch.setattr(
        "engine.orchestrator.search_amazon_products",
        failing_search,
    )

    from engine.orchestrator import search_products

    try:
        search_products("mouse")
    except RuntimeError as error:
        message = str(error)

        assert (
            "모든 마켓 검색에 실패했습니다."
            in message
        )
        assert "ebay" in message
        assert "amazon" in message
    else:
        raise AssertionError(
            "모든 마켓 실패 시 "
            "RuntimeError가 필요합니다."
        )

def test_find_best_opportunities_uses_product_shipping_cost(
    monkeypatch,
) -> None:
    product = Product(
        marketplace="ebay",
        item_id="shipping-orchestrator",
        title="Shipping Aware Product",
        price=20.0,
        currency="USD",
        shipping_cost=7.0,
    )

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [product],
    )

    result = find_best_opportunities(
        query="shipping",
        marketplace_fee_rate=0.0,
    )[0]

    assert result.analysis["shipping_cost"] == 7.0
    assert result.analysis["shipping_cost_source"] == "marketplace"
    assert result.analysis["is_free_shipping"] is False
