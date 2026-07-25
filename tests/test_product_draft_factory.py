from __future__ import annotations

from collections.abc import Callable

import pytest

from app.models import Product
from engine.catalog_manager import CanonicalProductDraft
from engine.product_attributes import ProductAttributes
from engine.product_draft_factory import (
    ProductDraftFactory,
)


def make_product(
    *,
    title: str = (
        "Apple iPhone 15 Pro 256GB Black New"
    ),
    brand: str = "",
    model_number: str = "",
    category: str = "",
    condition: str = "",
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="EBAY-001",
        title=title,
        price=999.99,
        currency="USD",
        condition=condition,
        url="https://example.com/item/1",
        brand=brand,
        model_number=model_number,
        category=category,
    )


def test_factory_can_be_created() -> None:
    factory = ProductDraftFactory()

    assert callable(
        factory.attribute_extractor
    )


def test_from_attributes_returns_draft() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title=(
            "apple iphone 15 pro 256gb black"
        ),
        brand="apple",
        model_number="iphone 15 pro",
        category="smartphone",
        capacity="256gb",
        color="black",
        edition="pro",
        condition="new",
    )

    draft = factory.from_attributes(
        attributes
    )

    assert isinstance(
        draft,
        CanonicalProductDraft,
    )


def test_from_attributes_maps_core_fields() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title=(
            "apple iphone 15 pro 256gb black"
        ),
        brand="apple",
        model_number="iphone 15 pro",
        category="smartphone",
        capacity="256gb",
        color="black",
        size="6.1 inch",
        edition="pro",
        condition="new",
    )

    draft = factory.from_attributes(
        attributes
    )

    assert draft.brand == "apple"
    assert draft.model == "iphone 15 pro"
    assert draft.category == "smartphone"
    assert draft.capacity == "256gb"
    assert draft.color == "black"
    assert draft.size == "6.1 inch"
    assert draft.edition == "pro"
    assert draft.condition == "new"


def test_structured_product_does_not_store_title_identity() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title=(
            "apple iphone 15 pro 256gb black"
        ),
        brand="apple",
        model_number="iphone 15 pro",
        capacity="256gb",
        color="black",
    )

    draft = factory.from_attributes(
        attributes
    )

    assert (
        "normalized_title"
        not in draft.attributes
    )


def test_unstructured_product_uses_normalized_title_as_fallback() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title=(
            "simple handmade wooden spoon"
        ),
    )

    draft = factory.from_attributes(
        attributes
    )

    assert draft.attributes[
        "normalized_title"
    ] == "simple handmade wooden spoon"


def test_quantity_is_stored_as_string() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title=(
            "apple usb c cable qty3"
        ),
        brand="apple",
        quantity=3,
    )

    draft = factory.from_attributes(
        attributes
    )

    assert draft.attributes[
        "quantity"
    ] == "3"


def test_bundle_flag_is_stored_only_when_true() -> None:
    factory = ProductDraftFactory()

    bundle_attributes = ProductAttributes(
        normalized_title="iphone cable bundle",
        brand="apple",
        is_bundle=True,
    )

    normal_attributes = ProductAttributes(
        normalized_title="iphone cable",
        brand="apple",
        is_bundle=False,
    )

    bundle_draft = factory.from_attributes(
        bundle_attributes
    )
    normal_draft = factory.from_attributes(
        normal_attributes
    )

    assert (
        bundle_draft.attributes[
            "is_bundle"
        ]
        == "true"
    )

    assert (
        "is_bundle"
        not in normal_draft.attributes
    )


def test_accessory_flag_is_stored_only_when_true() -> None:
    factory = ProductDraftFactory()

    accessory_attributes = ProductAttributes(
        normalized_title=(
            "iphone 15 protective case"
        ),
        brand="apple",
        is_accessory=True,
    )

    product_attributes = ProductAttributes(
        normalized_title="iphone 15",
        brand="apple",
        is_accessory=False,
    )

    accessory_draft = factory.from_attributes(
        accessory_attributes
    )
    product_draft = factory.from_attributes(
        product_attributes
    )

    assert (
        accessory_draft.attributes[
            "is_accessory"
        ]
        == "true"
    )

    assert (
        "is_accessory"
        not in product_draft.attributes
    )


def test_tokens_are_not_stored_in_draft_identity() -> None:
    factory = ProductDraftFactory()

    attributes = ProductAttributes(
        normalized_title="apple iphone 15",
        brand="apple",
        model_number="iphone 15",
        tokens=(
            "apple",
            "iphone",
            "15",
        ),
    )

    draft = factory.from_attributes(
        attributes
    )

    assert "tokens" not in draft.attributes


def test_from_product_extracts_attributes() -> None:
    factory = ProductDraftFactory()

    product = make_product()

    draft = factory.from_product(
        product
    )

    assert draft.brand == "apple"
    assert draft.category == "smartphone"
    assert draft.capacity == "256gb"
    assert draft.color == "black"
    assert draft.condition == "new"


def test_explicit_product_metadata_has_priority() -> None:
    factory = ProductDraftFactory()

    product = make_product(
        title=(
            "Generic Smartphone 256GB Black"
        ),
        brand="Example Brand",
        model_number="EX-100",
        category="Mobile Device",
        condition="Refurbished",
    )

    draft = factory.from_product(
        product
    )

    assert draft.brand == "example brand"
    assert draft.model == "ex-100"
    assert draft.category == "mobile device"
    assert draft.condition == "refurbished"


def test_factory_supports_custom_extractor() -> None:
    product = make_product(
        title="Unstructured Marketplace Title"
    )

    expected_attributes = ProductAttributes(
        normalized_title="custom normalized title",
        brand="custom brand",
        model_number="custom model",
    )

    received_products: list[Product] = []

    def custom_extractor(
        value: Product,
    ) -> ProductAttributes:
        received_products.append(value)
        return expected_attributes

    factory = ProductDraftFactory(
        attribute_extractor=custom_extractor
    )

    draft = factory.from_product(
        product
    )

    assert received_products == [product]
    assert draft.brand == "custom brand"
    assert draft.model == "custom model"


def test_custom_extractor_must_return_product_attributes() -> None:
    def invalid_extractor(
        product: Product,
    ) -> object:
        return {
            "title": product.title,
        }

    factory = ProductDraftFactory(
        attribute_extractor=(
            invalid_extractor  # type: ignore[arg-type]
        )
    )

    with pytest.raises(TypeError):
        factory.from_product(
            make_product()
        )


@pytest.mark.parametrize(
    "invalid_product",
    [
        None,
        "product",
        123,
        {},
    ],
)
def test_from_product_rejects_invalid_product(
    invalid_product: object,
) -> None:
    factory = ProductDraftFactory()

    with pytest.raises(TypeError):
        factory.from_product(
            invalid_product  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_attributes",
    [
        None,
        "attributes",
        123,
        {},
    ],
)
def test_from_attributes_rejects_invalid_attributes(
    invalid_attributes: object,
) -> None:
    factory = ProductDraftFactory()

    with pytest.raises(TypeError):
        factory.from_attributes(
            invalid_attributes  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "invalid_extractor",
    [
        None,
        123,
        "extractor",
        {},
    ],
)
def test_factory_rejects_non_callable_extractor(
    invalid_extractor: object,
) -> None:
    with pytest.raises(TypeError):
        ProductDraftFactory(
            attribute_extractor=(
                invalid_extractor  # type: ignore[arg-type]
            )
        )


def test_attribute_extractor_property_returns_same_callable() -> None:
    def extractor(
        product: Product,
    ) -> ProductAttributes:
        return ProductAttributes(
            normalized_title=product.title
        )

    typed_extractor: Callable[
        [Product],
        ProductAttributes,
    ] = extractor

    factory = ProductDraftFactory(
        attribute_extractor=typed_extractor
    )

    assert (
        factory.attribute_extractor
        is typed_extractor
    )