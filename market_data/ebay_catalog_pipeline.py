from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.models import Product
from engine.catalog_integration_service import (
    CatalogIntegrationService,
)
from engine.catalog_manager import CatalogResult
from marketplaces.ebay import (
    DEFAULT_MARKETPLACE_ID,
    search_products,
)


ProductSearcher = Callable[
    [str, int, str],
    list[Product],
]


@dataclass(frozen=True, slots=True)
class EbayCatalogPipelineResult:
    """
    eBay 검색 상품의 Catalog 통합 결과.

    query:
        실제 검색에 사용된 검색어.

    marketplace_id:
        eBay Marketplace ID.

    searched_count:
        eBay에서 검색된 Product 개수.

    created_count:
        새로 생성된 CanonicalProduct 개수.

    reused_count:
        기존 CanonicalProduct가 재사용된 개수.

    catalog_total:
        통합 완료 후 Catalog에 저장된 전체 상품 개수.

    results:
        각 Product의 Catalog 통합 결과.
    """

    query: str
    marketplace_id: str

    searched_count: int
    created_count: int
    reused_count: int
    catalog_total: int

    results: tuple[CatalogResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise TypeError(
                "query는 문자열이어야 합니다."
            )

        if not self.query.strip():
            raise ValueError(
                "query는 비어 있을 수 없습니다."
            )

        if not isinstance(self.marketplace_id, str):
            raise TypeError(
                "marketplace_id는 문자열이어야 합니다."
            )

        if not self.marketplace_id.strip():
            raise ValueError(
                "marketplace_id는 비어 있을 수 없습니다."
            )

        count_fields = (
            "searched_count",
            "created_count",
            "reused_count",
            "catalog_total",
        )

        for field_name in count_fields:
            value = getattr(self, field_name)

            if not isinstance(value, int):
                raise TypeError(
                    f"{field_name}는 정수여야 합니다."
                )

            if value < 0:
                raise ValueError(
                    f"{field_name}는 음수일 수 없습니다."
                )

        if (
            self.created_count
            + self.reused_count
            != self.searched_count
        ):
            raise ValueError(
                "created_count와 reused_count의 합은 "
                "searched_count와 같아야 합니다."
            )

        if len(self.results) != self.searched_count:
            raise ValueError(
                "results 개수는 searched_count와 "
                "같아야 합니다."
            )


class EbayCatalogPipeline:
    """
    eBay 상품 검색부터 Canonical Catalog 통합까지 담당한다.

    처리 흐름:

        eBay Browse API
            ↓
        marketplaces.ebay.search_products()
            ↓
        list[Product]
            ↓
        CatalogIntegrationService.integrate()
            ↓
        tuple[CatalogResult, ...]
            ↓
        EbayCatalogPipelineResult

    주요 책임:

    - eBay 상품 검색 실행
    - 검색된 Product 전체를 Catalog에 통합
    - 신규 생성 및 기존 재사용 개수 집계
    - Catalog 통합 결과 반환

    다음 책임은 수행하지 않는다:

    - eBay 인증 토큰 직접 발급
    - eBay 응답 데이터 직접 파싱
    - Product 속성 직접 추출
    - CanonicalProduct 동일성 직접 판단
    - Repository 직접 저장
    """

    def __init__(
        self,
        *,
        integration_service: CatalogIntegrationService,
        product_searcher: ProductSearcher | None = None,
    ) -> None:
        if not isinstance(
            integration_service,
            CatalogIntegrationService,
        ):
            raise TypeError(
                "integration_service는 "
                "CatalogIntegrationService 객체여야 합니다."
            )

        resolved_searcher = (
            search_products
            if product_searcher is None
            else product_searcher
        )

        if not callable(resolved_searcher):
            raise TypeError(
                "product_searcher는 호출 가능한 객체여야 합니다."
            )

        self._integration_service = integration_service
        self._product_searcher = resolved_searcher

    @property
    def integration_service(
        self,
    ) -> CatalogIntegrationService:
        """
        Pipeline이 사용하는 CatalogIntegrationService를 반환한다.
        """
        return self._integration_service

    @property
    def product_searcher(
        self,
    ) -> ProductSearcher:
        """
        Pipeline이 사용하는 eBay 상품 검색 함수를 반환한다.
        """
        return self._product_searcher

    def run(
        self,
        query: str,
        limit: int = 10,
        marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    ) -> EbayCatalogPipelineResult:
        """
        eBay 상품을 검색하고 Canonical Catalog에 통합한다.
        """
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

        products = self._product_searcher(
            cleaned_query,
            limit,
            cleaned_marketplace_id,
        )

        if not isinstance(products, list):
            raise TypeError(
                "product_searcher는 Product 목록을 "
                "반환해야 합니다."
            )

        integration_results: list[CatalogResult] = []

        for product in products:
            if not isinstance(product, Product):
                raise TypeError(
                    "product_searcher의 결과에는 "
                    "Product 객체만 포함되어야 합니다."
                )

            result = (
                self._integration_service.integrate(
                    product
                )
            )

            integration_results.append(result)

        results = tuple(integration_results)

        created_count = sum(
            1
            for result in results
            if result.created
        )

        reused_count = (
            len(results)
            - created_count
        )

        catalog_total = (
            self._integration_service
            .catalog_manager
            .repository
            .count()
        )

        return EbayCatalogPipelineResult(
            query=cleaned_query,
            marketplace_id=cleaned_marketplace_id,
            searched_count=len(products),
            created_count=created_count,
            reused_count=reused_count,
            catalog_total=catalog_total,
            results=results,
        )