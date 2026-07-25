from __future__ import annotations

from datetime import datetime

from app.models import Product
from engine.catalog_manager import CatalogManager, CatalogResult
from engine.product_draft_factory import ProductDraftFactory
from storage.price_history import PriceHistoryRepository


class CatalogIntegrationService:
    """
    Marketplace 공통 Product를 Canonical Catalog에 통합한다.

    처리 흐름:

        Product
            ↓
        ProductDraftFactory
            ↓
        CanonicalProductDraft
            ↓
        CatalogManager.find_or_create()
            ↓
        CatalogResult
            ↓
        PriceHistoryRepository.save_product_price() (선택)

    주요 책임:

    - Product를 CanonicalProductDraft로 변환
    - CatalogManager를 통해 기존 상품 검색 또는 신규 상품 생성
    - 가격 이력 Repository가 주입된 경우 Canonical Product에 연결된
      Append-only 가격 스냅샷 저장
    - 통합 결과를 CatalogResult로 반환

    가격 이력 Repository는 선택 의존성이다. 주입하지 않으면 기존과
    동일하게 Catalog 통합만 수행하므로 기존 호출부와 호환된다.
    """

    def __init__(
        self,
        *,
        catalog_manager: CatalogManager,
        draft_factory: ProductDraftFactory | None = None,
        price_history_repository: PriceHistoryRepository | None = None,
    ) -> None:
        if not isinstance(catalog_manager, CatalogManager):
            raise TypeError("catalog_manager는 CatalogManager 객체여야 합니다.")

        if draft_factory is None:
            draft_factory = ProductDraftFactory()

        if not isinstance(draft_factory, ProductDraftFactory):
            raise TypeError("draft_factory는 ProductDraftFactory 객체여야 합니다.")

        if (
            price_history_repository is not None
            and not isinstance(price_history_repository, PriceHistoryRepository)
        ):
            raise TypeError(
                "price_history_repository는 PriceHistoryRepository "
                "객체 또는 None이어야 합니다."
            )

        self._catalog_manager = catalog_manager
        self._draft_factory = draft_factory
        self._price_history_repository = price_history_repository

    @property
    def catalog_manager(self) -> CatalogManager:
        """서비스가 사용하는 CatalogManager를 반환한다."""
        return self._catalog_manager

    @property
    def draft_factory(self) -> ProductDraftFactory:
        """서비스가 사용하는 ProductDraftFactory를 반환한다."""
        return self._draft_factory

    @property
    def price_history_repository(self) -> PriceHistoryRepository | None:
        """서비스가 사용하는 가격 이력 Repository를 반환한다."""
        return self._price_history_repository

    def integrate(
        self,
        product: Product,
        *,
        observed_at: datetime | None = None,
    ) -> CatalogResult:
        """
        Product를 Canonical Catalog에 통합하고 가격 스냅샷을 저장한다.

        동일한 CanonicalProduct가 이미 존재하면:

            CatalogResult.created == False

        새로운 CanonicalProduct가 생성되면:

            CatalogResult.created == True

        PriceHistoryRepository가 주입되어 있으면 신규/재사용 여부와
        관계없이 매 관측마다 새 가격 스냅샷을 추가한다.
        """
        if not isinstance(product, Product):
            raise TypeError("product는 Product 객체여야 합니다.")

        if observed_at is not None and not isinstance(observed_at, datetime):
            raise TypeError("observed_at은 datetime 또는 None이어야 합니다.")

        draft = self._draft_factory.from_product(product)
        result = self._catalog_manager.find_or_create(draft)

        if self._price_history_repository is not None:
            self._price_history_repository.save_product_price(
                product,
                canonical_product_id=result.product.display_id,
                observed_at=observed_at,
            )

        return result
