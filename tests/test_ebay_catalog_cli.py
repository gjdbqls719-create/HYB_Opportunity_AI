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
from presentation.ebay_catalog_cli import (
    build_argument_parser,
    build_default_pipeline,
    format_pipeline_result,
    run_pipeline_repeatedly,
)


def make_product(
    *,
    item_id: str = "EBAY-001",
    title: str = (
        "Apple iPhone 15 Pro 256GB Black New"
    ),
    price: Decimal = Decimal("999.99"),
    url: str = "https://example.com/item/1",
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=title,
        price=price,
        currency="USD",
        condition="New",
        url=url,
    )


def make_pipeline(
    *,
    products: list[Product] | None = None,
) -> EbayCatalogPipeline:
    repository = InMemoryCatalogRepository()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
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

    return EbayCatalogPipeline(
        integration_service=integration_service,
        product_searcher=fake_product_searcher,
    )


def test_build_default_pipeline() -> None:
    pipeline = build_default_pipeline()

    assert isinstance(
        pipeline,
        EbayCatalogPipeline,
    )

    assert isinstance(
        pipeline.integration_service,
        CatalogIntegrationService,
    )

    assert (
        pipeline.integration_service
        .catalog_manager
        .repository
        .count()
        == 0
    )

    assert (
        pipeline.integration_service
        .price_history_repository
        is not None
    )


def test_format_pipeline_result() -> None:
    pipeline = make_pipeline(
        products=[
            make_product(),
        ]
    )

    result = pipeline.run(
        query="iphone",
    )

    output = format_pipeline_result(
        result,
        run_number=1,
    )

    assert "eBay Catalog Pipeline 실행 #1" in output
    assert "검색어          : iphone" in output
    assert "검색 결과       : 1개" in output
    assert "신규 생성       : 1개" in output
    assert "기존 재사용     : 0개" in output
    assert "Catalog 총 개수 : 1개" in output
    assert "CP-000001" in output
    assert "[신규]" in output


def test_format_pipeline_result_for_empty_search() -> None:
    pipeline = make_pipeline(
        products=[],
    )

    result = pipeline.run(
        query="not-found",
    )

    output = format_pipeline_result(
        result,
        run_number=1,
    )

    assert "검색 결과       : 0개" in output
    assert "검색된 상품이 없습니다." in output


def test_repeated_run_reuses_canonical_product(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pipeline = make_pipeline(
        products=[
            make_product(),
        ]
    )

    results = run_pipeline_repeatedly(
        pipeline=pipeline,
        query="iphone",
        limit=10,
        marketplace_id="EBAY_US",
        repeat=2,
    )

    assert len(results) == 2

    first_result = results[0]
    second_result = results[1]

    assert first_result.created_count == 1
    assert first_result.reused_count == 0
    assert first_result.catalog_total == 1

    assert second_result.created_count == 0
    assert second_result.reused_count == 1
    assert second_result.catalog_total == 1

    assert (
        first_result.results[0].product
        is second_result.results[0].product
    )

    captured = capsys.readouterr()

    assert "실행 #1" in captured.out
    assert "실행 #2" in captured.out
    assert "[신규]" in captured.out
    assert "[재사용]" in captured.out


def test_repeated_run_returns_tuple(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pipeline = make_pipeline(
        products=[
            make_product(),
        ]
    )

    results = run_pipeline_repeatedly(
        pipeline=pipeline,
        query="iphone",
        limit=10,
        marketplace_id="EBAY_US",
        repeat=1,
    )

    assert isinstance(results, tuple)

    assert isinstance(
        results[0],
        EbayCatalogPipelineResult,
    )

    capsys.readouterr()


def test_argument_parser_defaults() -> None:
    parser = build_argument_parser()

    arguments = parser.parse_args([])

    assert arguments.query == "iphone"
    assert arguments.limit == 10
    assert arguments.marketplace_id == "EBAY_US"
    assert arguments.repeat == 2


def test_argument_parser_custom_values() -> None:
    parser = build_argument_parser()

    arguments = parser.parse_args(
        [
            "laptop",
            "--limit",
            "25",
            "--marketplace-id",
            "EBAY_US",
            "--repeat",
            "3",
        ]
    )

    assert arguments.query == "laptop"
    assert arguments.limit == 25
    assert arguments.marketplace_id == "EBAY_US"
    assert arguments.repeat == 3


def test_format_rejects_invalid_result() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "result는 EbayCatalogPipelineResult "
            "객체여야 합니다"
        ),
    ):
        format_pipeline_result(
            object(),  # type: ignore[arg-type]
            run_number=1,
        )


def test_format_rejects_invalid_run_number() -> None:
    pipeline = make_pipeline(
        products=[],
    )

    result = pipeline.run(
        query="iphone",
    )

    with pytest.raises(
        ValueError,
        match="run_number는 1 이상이어야 합니다",
    ):
        format_pipeline_result(
            result,
            run_number=0,
        )


@pytest.mark.parametrize(
    "repeat",
    [
        0,
        -1,
    ],
)
def test_repeated_run_rejects_invalid_repeat(
    repeat: int,
) -> None:
    pipeline = make_pipeline()

    with pytest.raises(
        ValueError,
        match="repeat는 1 이상이어야 합니다",
    ):
        run_pipeline_repeatedly(
            pipeline=pipeline,
            query="iphone",
            limit=10,
            marketplace_id="EBAY_US",
            repeat=repeat,
        )


def test_repeated_run_rejects_empty_query() -> None:
    pipeline = make_pipeline()

    with pytest.raises(
        ValueError,
        match="검색어를 입력해야 합니다",
    ):
        run_pipeline_repeatedly(
            pipeline=pipeline,
            query="   ",
            limit=10,
            marketplace_id="EBAY_US",
            repeat=1,
        )