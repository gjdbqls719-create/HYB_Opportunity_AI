from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from app.models.canonical_product import CanonicalProduct
from engine.canonical_id_generator import (
    InMemoryCanonicalIdGenerator,
)
from engine.catalog_manager import (
    CanonicalProductDraft,
    CatalogManager,
    CatalogResult,
)
from engine.catalog_repository import (
    InMemoryCatalogRepository,
)


def make_manager() -> CatalogManager:
    return CatalogManager(
        repository=InMemoryCatalogRepository(),
        id_generator=InMemoryCanonicalIdGenerator(),
    )


def make_iphone_draft() -> CanonicalProductDraft:
    return CanonicalProductDraft(
        brand="Apple",
        model="iPhone 15 Pro",
        category="smartphone",
        capacity="256GB",
        color="Black",
        edition="Pro",
        condition="New",
        attributes={
            "ram": "8GB",
        },
    )


def test_draft_can_be_created() -> None:
    draft = make_iphone_draft()

    assert draft.brand == "Apple"
    assert draft.model == "iPhone 15 Pro"
    assert draft.capacity == "256GB"
    assert draft.attributes["ram"] == "8GB"


def test_draft_text_fields_are_trimmed() -> None:
    draft = CanonicalProductDraft(
        brand="  Apple  ",
        model="  iPhone 15  ",
    )

    assert draft.brand == "Apple"
    assert draft.model == "iPhone 15"


def test_blank_draft_fields_become_none() -> None:
    draft = CanonicalProductDraft(
        brand="   ",
        model="iPhone 15",
    )

    assert draft.brand is None
    assert draft.model == "iPhone 15"


def test_empty_draft_is_rejected() -> None:
    with pytest.raises(ValueError):
        CanonicalProductDraft()


def test_draft_with_attributes_only_is_allowed() -> None:
    draft = CanonicalProductDraft(
        attributes={
            "sku_family": "iphone-15",
        }
    )

    assert draft.attributes[
        "sku_family"
    ] == "iphone-15"


def test_draft_attributes_are_read_only() -> None:
    draft = CanonicalProductDraft(
        model="iPhone 15",
        attributes={
            "ram": "8GB",
        },
    )

    with pytest.raises(TypeError):
        draft.attributes["ram"] = "16GB"  # type: ignore[index]


def test_draft_attributes_are_copied() -> None:
    source = {
        "ram": "8GB",
    }

    draft = CanonicalProductDraft(
        model="iPhone 15",
        attributes=source,
    )

    source["ram"] = "16GB"

    assert draft.attributes["ram"] == "8GB"


def test_draft_is_immutable() -> None:
    draft = make_iphone_draft()

    with pytest.raises(FrozenInstanceError):
        draft.brand = "Samsung"  # type: ignore[misc]


def test_manager_exposes_dependencies() -> None:
    repository = InMemoryCatalogRepository()
    generator = InMemoryCanonicalIdGenerator()

    manager = CatalogManager(
        repository=repository,
        id_generator=generator,
    )

    assert manager.repository is repository
    assert manager.id_generator is generator


def test_create_stores_new_product() -> None:
    manager = make_manager()
    draft = make_iphone_draft()

    product = manager.create(draft)

    assert isinstance(
        product,
        CanonicalProduct,
    )
    assert product.display_id == "CP-000001"
    assert product.brand == "Apple"
    assert product.model == "iPhone 15 Pro"
    assert manager.repository.count() == 1


def test_create_always_creates_new_product() -> None:
    manager = make_manager()
    draft = make_iphone_draft()

    first = manager.create(draft)
    second = manager.create(draft)

    assert first.id != second.id
    assert first.display_id == "CP-000001"
    assert second.display_id == "CP-000002"
    assert manager.repository.count() == 2


def test_find_returns_existing_product() -> None:
    manager = make_manager()
    draft = make_iphone_draft()

    created = manager.create(draft)
    found = manager.find(draft)

    assert found is created


def test_find_returns_none_when_missing() -> None:
    manager = make_manager()

    result = manager.find(
        CanonicalProductDraft(
            brand="Samsung",
            model="Galaxy S24",
        )
    )

    assert result is None


def test_find_ignores_case_and_whitespace() -> None:
    manager = make_manager()

    created = manager.create(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
            capacity="256GB",
        )
    )

    found = manager.find(
        CanonicalProductDraft(
            brand="  apple ",
            model=" IPHONE 15 PRO ",
            capacity=" 256gb ",
        )
    )

    assert found is created


def test_find_uses_product_synonyms() -> None:
    manager = make_manager()

    created = manager.create(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
        )
    )

    found = manager.find(
        CanonicalProductDraft(
            brand="애플",
            model="아이폰 15 프로",
        )
    )

    assert found is created


def test_different_capacity_is_not_same_product() -> None:
    manager = make_manager()

    manager.create(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
            capacity="128GB",
        )
    )

    result = manager.find(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
            capacity="256GB",
        )
    )

    assert result is None


def test_different_color_is_not_same_product() -> None:
    manager = make_manager()

    manager.create(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
            color="Black",
        )
    )

    result = manager.find(
        CanonicalProductDraft(
            brand="Apple",
            model="iPhone 15 Pro",
            color="White",
        )
    )

    assert result is None


def test_different_attributes_are_not_same_product() -> None:
    manager = make_manager()

    manager.create(
        CanonicalProductDraft(
            model="MacBook Pro",
            attributes={
                "ram": "16GB",
            },
        )
    )

    result = manager.find(
        CanonicalProductDraft(
            model="MacBook Pro",
            attributes={
                "ram": "32GB",
            },
        )
    )

    assert result is None


def test_attribute_order_does_not_affect_identity() -> None:
    manager = make_manager()

    created = manager.create(
        CanonicalProductDraft(
            model="MacBook Pro",
            attributes={
                "ram": "16GB",
                "storage": "512GB",
            },
        )
    )

    found = manager.find(
        CanonicalProductDraft(
            model="MacBook Pro",
            attributes={
                "storage": "512GB",
                "ram": "16GB",
            },
        )
    )

    assert found is created


def test_find_or_create_creates_when_missing() -> None:
    manager = make_manager()

    result = manager.find_or_create(
        make_iphone_draft()
    )

    assert isinstance(
        result,
        CatalogResult,
    )
    assert result.created is True
    assert result.product.display_id == "CP-000001"
    assert manager.repository.count() == 1


def test_find_or_create_returns_existing_product() -> None:
    manager = make_manager()
    draft = make_iphone_draft()

    first = manager.find_or_create(draft)
    second = manager.find_or_create(draft)

    assert first.created is True
    assert second.created is False
    assert second.product is first.product
    assert manager.repository.count() == 1


def test_manager_synchronizes_generator_with_repository() -> None:
    repository = InMemoryCatalogRepository()

    repository.create(
        CanonicalProduct(
            display_id="CP-000010",
            brand="Apple",
            model="iPhone 14",
        )
    )

    manager = CatalogManager(
        repository=repository,
        id_generator=InMemoryCanonicalIdGenerator(),
    )

    result = manager.create(
        CanonicalProductDraft(
            brand="Samsung",
            model="Galaxy S24",
        )
    )

    assert result.display_id == "CP-000011"


@pytest.mark.parametrize(
    "invalid_draft",
    [
        None,
        "draft",
        123,
        {},
    ],
)
def test_manager_methods_reject_invalid_draft(
    invalid_draft: object,
) -> None:
    manager = make_manager()

    with pytest.raises(TypeError):
        manager.find(
            invalid_draft  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        manager.create(
            invalid_draft  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        manager.find_or_create(
            invalid_draft  # type: ignore[arg-type]
        )


def test_concurrent_find_or_create_prevents_duplicates() -> None:
    manager = make_manager()
    draft = make_iphone_draft()

    with ThreadPoolExecutor(
        max_workers=10
    ) as executor:
        results = list(
            executor.map(
                lambda _: manager.find_or_create(
                    draft
                ),
                range(100),
            )
        )

    assert manager.repository.count() == 1

    product_ids = {
        result.product.id
        for result in results
    }

    assert len(product_ids) == 1

    created_count = sum(
        result.created
        for result in results
    )

    assert created_count == 1