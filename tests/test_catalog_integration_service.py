from __future__ import annotations

import pytest

from app.models import Product
from app.models.canonical_product import (
    CanonicalProduct,
)
from engine.canonical_id_generator import (
    InMemoryCanonicalIdGenerator,
)
from engine.catalog_integration_service import (
    CatalogIntegrationService,
)
from engine.catalog_manager import (
    CatalogManager,
    CatalogResult,
)
from engine.catalog_repository import (
    InMemoryCatalogRepository,
)
from engine.product_draft_factory import (
    ProductDraftFactory,
)


def make_product(
    *,
    marketplace: str = "ebay",
    item_id: str = "EBAY-001",
    title: str = (
        "Apple iPhone 15 Pro 256GB Black New"
    ),
    price: float = 999.99,
    currency: str = "USD",
    condition: str = "",
    url: str = "https://example.com/item/1",
    brand: str = "",
    model_number: str = "",
    category: str = "",
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=title,
        price=price,
        currency=currency,
        condition=condition,
        url=url,
        brand=brand,
        model_number=model_number,
        category=category,
    )


def make_service(
    *,
    repository: InMemoryCatalogRepository | None = None,
    id_generator: InMemoryCanonicalIdGenerator | None = None,
    draft_factory: ProductDraftFactory | None = None,
) -> CatalogIntegrationService:
    resolved_repository = (
        repository
        if repository is not None
        else InMemoryCatalogRepository()
    )

    resolved_id_generator = (
        id_generator
        if id_generator is not None
        else InMemoryCanonicalIdGenerator()
    )

    catalog_manager = CatalogManager(
        repository=resolved_repository,
        id_generator=resolved_id_generator,
    )

    return CatalogIntegrationService(
        catalog_manager=catalog_manager,
        draft_factory=draft_factory,
    )


def test_service_can_be_created() -> None:
    service = make_service()

    assert isinstance(
        service.catalog_manager,
        CatalogManager,
    )

    assert isinstance(
        service.draft_factory,
        ProductDraftFactory,
    )


def test_service_uses_default_draft_factory() -> None:
    repository = InMemoryCatalogRepository()
    id_generator = InMemoryCanonicalIdGenerator()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=id_generator,
    )

    service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
    )

    assert isinstance(
        service.draft_factory,
        ProductDraftFactory,
    )


def test_service_uses_injected_dependencies() -> None:
    repository = InMemoryCatalogRepository()
    id_generator = InMemoryCanonicalIdGenerator()
    draft_factory = ProductDraftFactory()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=id_generator,
    )

    service = CatalogIntegrationService(
        catalog_manager=catalog_manager,
        draft_factory=draft_factory,
    )

    assert service.catalog_manager is catalog_manager
    assert service.draft_factory is draft_factory


def test_integrate_creates_canonical_product() -> None:
    repository = InMemoryCatalogRepository()

    service = make_service(
        repository=repository,
    )

    product = make_product()

    result = service.integrate(
        product
    )

    assert isinstance(
        result,
        CatalogResult,
    )

    assert isinstance(
        result.product,
        CanonicalProduct,
    )

    assert result.created is True
    assert repository.count() == 1


def test_integrate_assigns_display_id() -> None:
    service = make_service()

    result = service.integrate(
        make_product()
    )

    assert result.product.display_id == "CP-000001"


def test_integrate_maps_product_identity() -> None:
    service = make_service()

    product = make_product(
        title=(
            "Apple iPhone 15 Pro "
            "256GB Black New"
        ),
    )

    result = service.integrate(
        product
    )

    canonical_product = result.product

    assert canonical_product.brand == "apple"
    assert canonical_product.category == "smartphone"
    assert canonical_product.capacity == "256gb"
    assert canonical_product.color == "black"
    assert canonical_product.condition == "new"


def test_integrate_returns_existing_product_for_same_identity() -> None:
    repository = InMemoryCatalogRepository()

    service = make_service(
        repository=repository,
    )

    first_product = make_product(
        item_id="EBAY-001",
        price=999.99,
        url="https://example.com/item/1",
    )

    second_product = make_product(
        item_id="EBAY-002",
        price=949.99,
        url="https://example.com/item/2",
    )

    first_result = service.integrate(
        first_product
    )

    second_result = service.integrate(
        second_product
    )

    assert first_result.created is True
    assert second_result.created is False

    assert (
        second_result.product
        is first_result.product
    )

    assert repository.count() == 1


def test_marketplace_item_id_does_not_define_canonical_identity() -> None:
    repository = InMemoryCatalogRepository()

    service = make_service(
        repository=repository,
    )

    ebay_product = make_product(
        marketplace="ebay",
        item_id="EBAY-001",
        url="https://ebay.example/item/1",
    )

    amazon_product = make_product(
        marketplace="amazon",
        item_id="AMAZON-001",
        url="https://amazon.example/item/1",
    )

    ebay_result = service.integrate(
        ebay_product
    )

    amazon_result = service.integrate(
        amazon_product
    )

    assert ebay_result.created is True
    assert amazon_result.created is False

    assert (
        amazon_result.product
        is ebay_result.product
    )

    assert repository.count() == 1


def test_different_identity_creates_new_product() -> None:
    repository = InMemoryCatalogRepository()

    service = make_service(
        repository=repository,
    )

    iphone_256gb = make_product(
        item_id="EBAY-001",
        title=(
            "Apple iPhone 15 Pro "
            "256GB Black New"
        ),
    )

    iphone_512gb = make_product(
        item_id="EBAY-002",
        title=(
            "Apple iPhone 15 Pro "
            "512GB Black New"
        ),
    )

    first_result = service.integrate(
        iphone_256gb
    )

    second_result = service.integrate(
        iphone_512gb
    )

    assert first_result.created is True
    assert second_result.created is True

    assert (
        first_result.product.id
        != second_result.product.id
    )

    assert (
        first_result.product.display_id
        == "CP-000001"
    )

    assert (
        second_result.product.display_id
        == "CP-000002"
    )

    assert repository.count() == 2


def test_unstructured_product_can_be_integrated() -> None:
    service = make_service()

    product = make_product(
        title="Simple Handmade Wooden Spoon",
        condition="",
    )

    result = service.integrate(
        product
    )

    assert result.created is True

    assert (
        result.product.attributes[
            "normalized_title"
        ]
        == "simple handmade wooden spoon"
    )


def test_integrate_rejects_invalid_product() -> None:
    service = make_service()

    with pytest.raises(
        TypeError,
        match="product는 Product 객체여야 합니다",
    ):
        service.integrate(
            "invalid product"  # type: ignore[arg-type]
        )


def test_constructor_rejects_invalid_catalog_manager() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "catalog_manager는 CatalogManager "
            "객체여야 합니다"
        ),
    ):
        CatalogIntegrationService(
            catalog_manager=object(),  # type: ignore[arg-type]
        )


def test_constructor_rejects_invalid_draft_factory() -> None:
    repository = InMemoryCatalogRepository()
    id_generator = InMemoryCanonicalIdGenerator()

    catalog_manager = CatalogManager(
        repository=repository,
        id_generator=id_generator,
    )

    with pytest.raises(
        TypeError,
        match=(
            "draft_factory는 ProductDraftFactory "
            "객체여야 합니다"
        ),
    ):
        CatalogIntegrationService(
            catalog_manager=catalog_manager,
            draft_factory=object(),  # type: ignore[arg-type]
        )

def test_service_can_use_price_history_repository(tmp_path) -> None:
    from storage.price_history import PriceHistoryRepository

    repository = InMemoryCatalogRepository()
    price_repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )

    service = make_service(repository=repository)
    service = CatalogIntegrationService(
        catalog_manager=service.catalog_manager,
        price_history_repository=price_repository,
    )

    assert service.price_history_repository is price_repository


def test_integrate_saves_canonical_price_snapshot(tmp_path) -> None:
    from storage.price_history import PriceHistoryRepository

    catalog_repository = InMemoryCatalogRepository()
    price_repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )

    base_service = make_service(repository=catalog_repository)
    service = CatalogIntegrationService(
        catalog_manager=base_service.catalog_manager,
        price_history_repository=price_repository,
    )

    product = make_product(
        item_id="EBAY-PRICE-001",
        price=899.99,
    )

    result = service.integrate(product)

    records = price_repository.get_canonical_history(
        canonical_product_id=result.product.display_id
    )

    assert len(records) == 1
    assert records[0].canonical_product_id == result.product.display_id
    assert records[0].marketplace == "ebay"
    assert records[0].item_id == "EBAY-PRICE-001"
    assert records[0].price == 899.99


def test_integrate_appends_snapshot_when_canonical_product_is_reused(
    tmp_path,
) -> None:
    from storage.price_history import PriceHistoryRepository

    catalog_repository = InMemoryCatalogRepository()
    price_repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )

    base_service = make_service(repository=catalog_repository)
    service = CatalogIntegrationService(
        catalog_manager=base_service.catalog_manager,
        price_history_repository=price_repository,
    )

    first_product = make_product(
        item_id="EBAY-PRICE-001",
        price=999.99,
    )
    second_product = make_product(
        item_id="EBAY-PRICE-002",
        price=949.99,
        url="https://example.com/item/2",
    )

    first_result = service.integrate(first_product)
    second_result = service.integrate(second_product)

    assert first_result.product is second_result.product
    assert second_result.created is False

    records = price_repository.get_canonical_history(
        canonical_product_id=first_result.product.display_id
    )

    assert len(records) == 2
    assert {record.item_id for record in records} == {
        "EBAY-PRICE-001",
        "EBAY-PRICE-002",
    }
    assert {record.price for record in records} == {999.99, 949.99}


def test_service_without_price_repository_preserves_previous_behavior() -> None:
    service = make_service()

    result = service.integrate(make_product())

    assert isinstance(result, CatalogResult)
    assert service.price_history_repository is None
