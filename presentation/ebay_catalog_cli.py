from __future__ import annotations

import argparse
from collections.abc import Sequence

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
from storage.price_history import PriceHistoryRepository


DEFAULT_QUERY = "iphone"
DEFAULT_LIMIT = 10
DEFAULT_REPEAT = 2


def build_default_pipeline() -> EbayCatalogPipeline:
    """
    실제 eBay Browse API와 연결되는 기본 Pipeline을 생성한다.

    현재 CatalogRepository는 메모리 기반이므로 프로그램이 종료되면
    CanonicalProduct는 사라지지만, 가격 스냅샷은 SQLite에 영구 저장된다.
    """
    repository = InMemoryCatalogRepository()

    id_generator = InMemoryCanonicalIdGenerator()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=id_generator,
    )

    price_history_repository = PriceHistoryRepository()

    integration_service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
        price_history_repository=price_history_repository,
    )

    return EbayCatalogPipeline(
        integration_service=integration_service,
    )


def format_pipeline_result(
    result: EbayCatalogPipelineResult,
    *,
    run_number: int,
) -> str:
    """
    eBay Catalog Pipeline 실행 결과를 콘솔 출력용 문자열로 만든다.
    """
    if not isinstance(
        result,
        EbayCatalogPipelineResult,
    ):
        raise TypeError(
            "result는 EbayCatalogPipelineResult 객체여야 합니다."
        )

    if not isinstance(run_number, int):
        raise TypeError(
            "run_number는 정수여야 합니다."
        )

    if run_number < 1:
        raise ValueError(
            "run_number는 1 이상이어야 합니다."
        )

    lines = [
        "",
        "=" * 60,
        f"eBay Catalog Pipeline 실행 #{run_number}",
        "=" * 60,
        f"검색어          : {result.query}",
        f"Marketplace ID : {result.marketplace_id}",
        f"검색 결과       : {result.searched_count}개",
        f"신규 생성       : {result.created_count}개",
        f"기존 재사용     : {result.reused_count}개",
        f"Catalog 총 개수 : {result.catalog_total}개",
    ]

    if not result.results:
        lines.extend(
            [
                "",
                "검색된 상품이 없습니다.",
            ]
        )

        return "\n".join(lines)

    lines.extend(
        [
            "",
            "통합 결과:",
        ]
    )

    for index, catalog_result in enumerate(
        result.results,
        start=1,
    ):
        canonical_product = catalog_result.product

        status = (
            "신규"
            if catalog_result.created
            else "재사용"
        )

        identity_parts = [
            canonical_product.brand,
            canonical_product.model,
            canonical_product.category,
            canonical_product.capacity,
            canonical_product.color,
            canonical_product.size,
            canonical_product.edition,
            canonical_product.condition,
        ]

        identity = " | ".join(
            part
            for part in identity_parts
            if part
        )

        if not identity:
            normalized_title = (
                canonical_product.attributes.get(
                    "normalized_title"
                )
            )

            identity = (
                normalized_title
                if normalized_title
                else "식별 정보 없음"
            )

        lines.append(
            f"{index:>2}. "
            f"[{status}] "
            f"{canonical_product.display_id} "
            f"- {identity}"
        )

    return "\n".join(lines)


def run_pipeline_repeatedly(
    *,
    pipeline: EbayCatalogPipeline,
    query: str,
    limit: int,
    marketplace_id: str,
    repeat: int,
) -> tuple[EbayCatalogPipelineResult, ...]:
    """
    하나의 Pipeline과 Catalog를 유지한 채 동일 검색을 반복 실행한다.

    첫 실행에서 생성된 CanonicalProduct가 이후 실행에서 재사용되는지
    확인하기 위한 개발용 실행 함수다.
    """
    if not isinstance(
        pipeline,
        EbayCatalogPipeline,
    ):
        raise TypeError(
            "pipeline은 EbayCatalogPipeline 객체여야 합니다."
        )

    if not isinstance(query, str):
        raise TypeError(
            "query는 문자열이어야 합니다."
        )

    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError(
            "검색어를 입력해야 합니다."
        )

    if not isinstance(limit, int):
        raise TypeError(
            "limit은 정수여야 합니다."
        )

    if not 1 <= limit <= 200:
        raise ValueError(
            "limit은 1 이상 200 이하여야 합니다."
        )

    if not isinstance(marketplace_id, str):
        raise TypeError(
            "marketplace_id는 문자열이어야 합니다."
        )

    cleaned_marketplace_id = marketplace_id.strip()

    if not cleaned_marketplace_id:
        raise ValueError(
            "marketplace_id는 비어 있을 수 없습니다."
        )

    if not isinstance(repeat, int):
        raise TypeError(
            "repeat는 정수여야 합니다."
        )

    if repeat < 1:
        raise ValueError(
            "repeat는 1 이상이어야 합니다."
        )

    results: list[EbayCatalogPipelineResult] = []

    for run_number in range(1, repeat + 1):
        result = pipeline.run(
            query=cleaned_query,
            limit=limit,
            marketplace_id=cleaned_marketplace_id,
        )

        results.append(result)

        print(
            format_pipeline_result(
                result,
                run_number=run_number,
            )
        )

    return tuple(results)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    CLI 인자 Parser를 생성한다.
    """
    parser = argparse.ArgumentParser(
        description=(
            "eBay Browse API 상품을 검색하고 "
            "Canonical Catalog에 통합합니다."
        )
    )

    parser.add_argument(
        "query",
        nargs="?",
        default=DEFAULT_QUERY,
        help=(
            "eBay 검색어 "
            f"(기본값: {DEFAULT_QUERY})"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "검색할 상품 개수 "
            f"(기본값: {DEFAULT_LIMIT}, 최대: 200)"
        ),
    )

    parser.add_argument(
        "--marketplace-id",
        default=DEFAULT_MARKETPLACE_ID,
        help=(
            "eBay Marketplace ID "
            f"(기본값: {DEFAULT_MARKETPLACE_ID})"
        ),
    )

    parser.add_argument(
        "--repeat",
        type=int,
        default=DEFAULT_REPEAT,
        help=(
            "동일 검색 반복 횟수 "
            f"(기본값: {DEFAULT_REPEAT})"
        ),
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """
    eBay Catalog Pipeline CLI 진입점.
    """
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

    pipeline = build_default_pipeline()

    try:
        run_pipeline_repeatedly(
            pipeline=pipeline,
            query=arguments.query,
            limit=arguments.limit,
            marketplace_id=arguments.marketplace_id,
            repeat=arguments.repeat,
        )
    except Exception as error:
        print()
        print("=" * 60)
        print("eBay Catalog Pipeline 실행 실패")
        print("=" * 60)
        print(f"{type(error).__name__}: {error}")

        return 1

    print()
    print("=" * 60)
    print("eBay → Canonical Catalog 통합 완료")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())