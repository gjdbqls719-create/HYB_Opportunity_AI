from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.models.canonical_product import (
    CanonicalProduct,
)
from engine.catalog_repository import (
    CanonicalProductNotFoundError,
    CatalogRepository,
    DuplicateCanonicalProductError,
    InMemoryCatalogRepository,
)


def make_product(
    display_id: str,
    *,
    brand: str = "Apple",
    model: str = "iPhone 15 Pro",
) -> CanonicalProduct:
    return CanonicalProduct(
        display_id=display_id,
        brand=brand,
        model=model,
    )


def test_repository_implements_interface() -> None:
    repository = InMemoryCatalogRepository()

    assert isinstance(
        repository,
        CatalogRepository,
    )


def test_repository_starts_empty() -> None:
    repository = InMemoryCatalogRepository()

    assert repository.count() == 0
    assert repository.list_all() == ()


def test_create_stores_product() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000001")

    result = repository.create(product)

    assert result is product
    assert repository.count() == 1


def test_get_by_id_returns_product() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000002")

    repository.create(product)

    result = repository.get_by_id(
        product.id
    )

    assert result is product


def test_get_by_display_id_returns_product() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000003")

    repository.create(product)

    result = repository.get_by_display_id(
        "CP-000003"
    )

    assert result is product


def test_display_id_lookup_trims_whitespace() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000004")

    repository.create(product)

    result = repository.get_by_display_id(
        "  CP-000004  "
    )

    assert result is product


def test_find_by_id_returns_none_when_missing() -> None:
    repository = InMemoryCatalogRepository()

    assert (
        repository.find_by_id(uuid4())
        is None
    )


def test_find_by_display_id_returns_none_when_missing() -> None:
    repository = InMemoryCatalogRepository()

    assert (
        repository.find_by_display_id(
            "CP-999999"
        )
        is None
    )


def test_get_by_id_raises_when_missing() -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(
        CanonicalProductNotFoundError
    ):
        repository.get_by_id(uuid4())


def test_get_by_display_id_raises_when_missing() -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(
        CanonicalProductNotFoundError
    ):
        repository.get_by_display_id(
            "CP-999999"
        )


def test_exists_by_id_returns_correct_value() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000005")

    assert (
        repository.exists_by_id(product.id)
        is False
    )

    repository.create(product)

    assert (
        repository.exists_by_id(product.id)
        is True
    )


def test_exists_by_display_id_returns_correct_value() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000006")

    assert (
        repository.exists_by_display_id(
            product.display_id
        )
        is False
    )

    repository.create(product)

    assert (
        repository.exists_by_display_id(
            product.display_id
        )
        is True
    )


def test_duplicate_internal_id_is_rejected() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000007")

    duplicate = CanonicalProduct(
        id=product.id,
        display_id="CP-000008",
    )

    repository.create(product)

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create(duplicate)


def test_duplicate_display_id_is_rejected() -> None:
    repository = InMemoryCatalogRepository()
    first = make_product("CP-000009")
    second = make_product("CP-000009")

    repository.create(first)

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create(second)


def test_failed_duplicate_create_does_not_change_count() -> None:
    repository = InMemoryCatalogRepository()
    first = make_product("CP-000010")
    duplicate = make_product("CP-000010")

    repository.create(first)

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create(duplicate)

    assert repository.count() == 1
    assert repository.get_by_display_id(
        "CP-000010"
    ) is first


def test_create_many_stores_all_products() -> None:
    repository = InMemoryCatalogRepository()

    products = [
        make_product("CP-000011"),
        make_product("CP-000012"),
        make_product("CP-000013"),
    ]

    result = repository.create_many(
        products
    )

    assert result == tuple(products)
    assert repository.count() == 3


def test_create_many_accepts_generator_expression() -> None:
    repository = InMemoryCatalogRepository()

    products = (
        make_product(
            f"CP-{number:06d}"
        )
        for number in range(14, 17)
    )

    result = repository.create_many(
        products
    )

    assert len(result) == 3
    assert repository.count() == 3


def test_create_many_is_atomic_when_existing_duplicate_found() -> None:
    repository = InMemoryCatalogRepository()
    existing = make_product("CP-000017")

    repository.create(existing)

    products = [
        make_product("CP-000018"),
        make_product("CP-000017"),
        make_product("CP-000019"),
    ]

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create_many(products)

    assert repository.count() == 1
    assert repository.find_by_display_id(
        "CP-000018"
    ) is None
    assert repository.find_by_display_id(
        "CP-000019"
    ) is None


def test_create_many_is_atomic_for_internal_duplicates() -> None:
    repository = InMemoryCatalogRepository()

    first = make_product("CP-000020")

    second = CanonicalProduct(
        id=first.id,
        display_id="CP-000021",
    )

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create_many(
            [first, second]
        )

    assert repository.count() == 0


def test_create_many_is_atomic_for_display_id_duplicates() -> None:
    repository = InMemoryCatalogRepository()

    products = [
        make_product("CP-000022"),
        make_product("CP-000022"),
    ]

    with pytest.raises(
        DuplicateCanonicalProductError
    ):
        repository.create_many(products)

    assert repository.count() == 0


def test_create_many_with_empty_collection_returns_empty_tuple() -> None:
    repository = InMemoryCatalogRepository()

    result = repository.create_many([])

    assert result == ()
    assert repository.count() == 0


def test_list_all_preserves_insertion_order() -> None:
    repository = InMemoryCatalogRepository()

    first = make_product("CP-000023")
    second = make_product("CP-000024")
    third = make_product("CP-000025")

    repository.create_many(
        [first, second, third]
    )

    assert repository.list_all() == (
        first,
        second,
        third,
    )


def test_list_all_returns_immutable_tuple() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000026")

    repository.create(product)

    result = repository.list_all()

    assert isinstance(result, tuple)


def test_delete_removes_product() -> None:
    repository = InMemoryCatalogRepository()
    product = make_product("CP-000027")

    repository.create(product)

    deleted = repository.delete(
        product.id
    )

    assert deleted is product
    assert repository.count() == 0
    assert (
        repository.find_by_id(product.id)
        is None
    )
    assert (
        repository.find_by_display_id(
            product.display_id
        )
        is None
    )


def test_delete_raises_when_product_is_missing() -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(
        CanonicalProductNotFoundError
    ):
        repository.delete(uuid4())


def test_display_id_can_be_reused_after_delete() -> None:
    repository = InMemoryCatalogRepository()

    first = make_product("CP-000028")
    repository.create(first)
    repository.delete(first.id)

    second = make_product("CP-000028")
    repository.create(second)

    assert repository.count() == 1
    assert repository.get_by_display_id(
        "CP-000028"
    ) is second


def test_clear_removes_all_products() -> None:
    repository = InMemoryCatalogRepository()

    repository.create_many(
        [
            make_product("CP-000029"),
            make_product("CP-000030"),
            make_product("CP-000031"),
        ]
    )

    repository.clear()

    assert repository.count() == 0
    assert repository.list_all() == ()


@pytest.mark.parametrize(
    "invalid_product",
    [
        None,
        "product",
        123,
        {},
    ],
)
def test_create_rejects_invalid_product(
    invalid_product: object,
) -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(TypeError):
        repository.create(
            invalid_product  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_product_id",
    [
        None,
        "not-a-uuid",
        123,
        True,
    ],
)
def test_id_methods_reject_invalid_product_id(
    invalid_product_id: object,
) -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(TypeError):
        repository.find_by_id(
            invalid_product_id  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        repository.get_by_id(
            invalid_product_id  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        repository.exists_by_id(
            invalid_product_id  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        repository.delete(
            invalid_product_id  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_display_id",
    [
        None,
        123,
        True,
    ],
)
def test_display_id_methods_reject_non_string_values(
    invalid_display_id: object,
) -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(TypeError):
        repository.find_by_display_id(
            invalid_display_id  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        repository.get_by_display_id(
            invalid_display_id  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        repository.exists_by_display_id(
            invalid_display_id  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "blank_display_id",
    [
        "",
        "   ",
    ],
)
def test_display_id_methods_reject_blank_values(
    blank_display_id: str,
) -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(ValueError):
        repository.find_by_display_id(
            blank_display_id
        )

    with pytest.raises(ValueError):
        repository.get_by_display_id(
            blank_display_id
        )

    with pytest.raises(ValueError):
        repository.exists_by_display_id(
            blank_display_id
        )


def test_create_many_rejects_single_string() -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(TypeError):
        repository.create_many(
            "not-products"  # type: ignore[arg-type]
        )


def test_create_many_rejects_invalid_item() -> None:
    repository = InMemoryCatalogRepository()

    with pytest.raises(TypeError):
        repository.create_many(
            [
                make_product("CP-000032"),
                "invalid",
            ]  # type: ignore[list-item]
        )

    assert repository.count() == 0


def test_concurrent_creates_store_all_unique_products() -> None:
    repository = InMemoryCatalogRepository()

    products = [
        make_product(
            f"CP-{number:06d}"
        )
        for number in range(100, 200)
    ]

    with ThreadPoolExecutor(
        max_workers=10
    ) as executor:
        results = list(
            executor.map(
                repository.create,
                products,
            )
        )

    assert len(results) == 100
    assert repository.count() == 100

    stored_display_ids = {
        product.display_id
        for product in repository.list_all()
    }

    assert len(stored_display_ids) == 100