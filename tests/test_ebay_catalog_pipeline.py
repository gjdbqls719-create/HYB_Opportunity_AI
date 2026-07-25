from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Product
from engine.canonical_id_generator import (
    InMemoryCanonicalIdGenerator,
)
from engine.catalog_integration_service import (
    CatalogIntegrationService,
)
from engine.catalog_manager import CatalogManager
from engine.catalog_repository import (
    InMemoryCatalogRepository,
)
from market_data.ebay_catalog_pipeline import (
    EbayCatalogPipeline,
    EbayCatalogPipelineResult,
)
from marketplaces.ebay import DEFAULT_MARKETPLACE_ID


def make_product(
    *,
    marketplace: str = "ebay",
    item_id: str = "EBAY-001",
    title: str = (
        "Apple iPhone 15 Pro 256GB Black New"
    ),
    price: Decimal = Decimal("999.99"),
    currency: str = "USD",
    condition: str = "New",
    url: str = "https://example.com/item/1",
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=title,
        price=price,
        currency=currency,
        condition=condition,
        url=url,
    )


def make_pipeline(
    *,
    products: list[Product] | None = None,
) -> tuple[
    EbayCatalogPipeline,
    InMemoryCatalogRepository,
]:
    repository = InMemoryCatalogRepository()

    id_generator = InMemoryCanonicalIdGenerator()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=id_generator,
    )

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    search_results = (
        []
        if products is None
        else products
    )

    def fake_product_searcher(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[Product]:
        return search_results[:limit]

    pipeline = EbayCatalogPipeline(
        integration_service=integration_service,
        product_searcher=fake_product_searcher,
    )

    return pipeline, repository


def test_pipeline_can_be_created() -> None:
    pipeline, _ = make_pipeline()

    assert isinstance(
        pipeline.integration_service,
        CatalogIntegrationService,
    )

    assert callable(
        pipeline.product_searcher
    )


def test_pipeline_integrates_searched_products() -> None:
    products = [
        make_product(
            item_id="EBAY-001",
            title=(
                "Apple iPhone 15 Pro "
                "256GB Black New"
            ),
        ),
        make_product(
            item_id="EBAY-002",
            title=(
                "Apple iPhone 15 Pro "
                "512GB Black New"
            ),
        ),
    ]

    pipeline, repository = make_pipeline(
        products=products,
    )

    result = pipeline.run(
        query="iphone",
        limit=10,
    )

    assert isinstance(
        result,
        EbayCatalogPipelineResult,
    )

    assert result.searched_count == 2
    assert result.created_count == 2
    assert result.reused_count == 0
    assert result.catalog_total == 2
    assert repository.count() == 2
    assert len(result.results) == 2


def test_pipeline_reuses_same_canonical_identity() -> None:
    products = [
        make_product(
            item_id="EBAY-001",
            price=Decimal("999.99"),
            url="https://example.com/item/1",
        ),
        make_product(
            item_id="EBAY-002",
            price=Decimal("949.99"),
            url="https://example.com/item/2",
        ),
    ]

    pipeline, repository = make_pipeline(
        products=products,
    )

    result = pipeline.run(
        query="iphone",
    )

    assert result.searched_count == 2
    assert result.created_count == 1
    assert result.reused_count == 1
    assert result.catalog_total == 1
    assert repository.count() == 1

    assert (
        result.results[0].product
        is result.results[1].product
    )


def test_pipeline_returns_empty_result_when_no_products_found() -> None:
    pipeline, repository = make_pipeline(
        products=[],
    )

    result = pipeline.run(
        query="not-found-product",
    )

    assert result.searched_count == 0
    assert result.created_count == 0
    assert result.reused_count == 0
    assert result.catalog_total == 0
    assert result.results == ()
    assert repository.count() == 0


def test_pipeline_passes_search_arguments() -> None:
    repository = InMemoryCatalogRepository()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
    )

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    received_arguments: dict[str, object] = {}

    def fake_product_searcher(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[Product]:
        received_arguments["query"] = query
        received_arguments["limit"] = limit
        received_arguments[
            "marketplace_id"
        ] = marketplace_id

        return []

    pipeline = EbayCatalogPipeline(
        integration_service=integration_service,
        product_searcher=fake_product_searcher,
    )

    pipeline.run(
        query="  laptop  ",
        limit=25,
        marketplace_id="EBAY_US",
    )

    assert received_arguments == {
        "query": "laptop",
        "limit": 25,
        "marketplace_id": "EBAY_US",
    }


def test_pipeline_uses_default_marketplace_id() -> None:
    repository = InMemoryCatalogRepository()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
    )

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    received_marketplace_id = ""

    def fake_product_searcher(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[Product]:
        nonlocal received_marketplace_id

        received_marketplace_id = marketplace_id

        return []

    pipeline = EbayCatalogPipeline(
        integration_service=integration_service,
        product_searcher=fake_product_searcher,
    )

    pipeline.run(
        query="iphone",
    )

    assert (
        received_marketplace_id
        == DEFAULT_MARKETPLACE_ID
    )


def test_pipeline_respects_limit() -> None:
    products = [
        make_product(
            item_id=f"EBAY-{index}",
            title=f"Test Product Model {index}",
            url=f"https://example.com/item/{index}",
        )
        for index in range(1, 6)
    ]

    pipeline, _ = make_pipeline(
        products=products,
    )

    result = pipeline.run(
        query="test product",
        limit=2,
    )

    assert result.searched_count == 2
    assert len(result.results) == 2


def test_pipeline_rejects_empty_query() -> None:
    pipeline, _ = make_pipeline()

    with pytest.raises(
        ValueError,
        match="검색어를 입력해야 합니다",
    ):
        pipeline.run(
            query="   ",
        )


@pytest.mark.parametrize(
    "limit",
    [
        0,
        201,
        -1,
    ],
)
def test_pipeline_rejects_invalid_limit(
    limit: int,
) -> None:
    pipeline, _ = make_pipeline()

    with pytest.raises(
        ValueError,
        match="limit은 1 이상 200 이하여야 합니다",
    ):
        pipeline.run(
            query="iphone",
            limit=limit,
        )


def test_pipeline_rejects_invalid_product_result() -> None:
    repository = InMemoryCatalogRepository()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
    )

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    def invalid_product_searcher(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[Product]:
        return [
            "invalid product",  # type: ignore[list-item]
        ]

    pipeline = EbayCatalogPipeline(
        integration_service=integration_service,
        product_searcher=invalid_product_searcher,
    )

    with pytest.raises(
        TypeError,
        match=(
            "Product 객체만 포함되어야 합니다"
        ),
    ):
        pipeline.run(
            query="iphone",
        )


def test_constructor_rejects_invalid_service() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "integration_service는 "
            "CatalogIntegrationService 객체여야 합니다"
        ),
    ):
        EbayCatalogPipeline(
            integration_service=object(),  # type: ignore[arg-type]
        )


def test_constructor_rejects_invalid_searcher() -> None:
    repository = InMemoryCatalogRepository()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
    )

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    with pytest.raises(
        TypeError,
        match=(
            "product_searcher는 호출 가능한 "
            "객체여야 합니다"
        ),
    ):
        EbayCatalogPipeline(
            integration_service=integration_service,
            product_searcher=object(),  # type: ignore[arg-type]
        )