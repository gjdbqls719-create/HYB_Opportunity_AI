from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Product
from engine.product_attribute_extractor import (
    extract_product_attributes,
)
from engine.product_draft_factory import (
    ProductDraftFactory,
)


def make_product(
    *,
    title: str,
    brand: str = "",
    model_number: str = "",
    category: str = "",
    condition: str = "",
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="TEST-001",
        title=title,
        price=Decimal("100.00"),
        currency="USD",
        condition=condition,
        url="https://example.com/test-item",
        brand=brand,
        model_number=model_number,
        category=category,
    )


def test_identity_field_groups_are_explicit() -> None:
    assert (
        ProductDraftFactory.STRONG_IDENTITY_FIELDS
        == (
            "brand",
            "model_number",
            "capacity",
            "edition",
        )
    )

    assert (
        ProductDraftFactory.WEAK_IDENTITY_FIELDS
        == (
            "category",
            "condition",
            "color",
            "size",
        )
    )


def test_category_and_condition_are_weak_identity() -> None:
    attributes = extract_product_attributes(
        "Generic Smartphone Alpha New",
        category="smartphone",
        condition="new",
    )

    assert (
        ProductDraftFactory
        ._has_strong_identity(attributes)
        is False
    )

    assert (
        ProductDraftFactory
        ._has_weak_identity(attributes)
        is True
    )


def test_weak_identity_preserves_normalized_title() -> None:
    factory = ProductDraftFactory()

    attributes = extract_product_attributes(
        "Generic Smartphone Alpha New",
        category="smartphone",
        condition="new",
    )

    draft = factory.from_attributes(
        attributes
    )

    assert draft.category == "smartphone"
    assert draft.condition == "new"

    assert (
        draft.attributes["normalized_title"]
        == "generic smartphone alpha new"
    )


@pytest.mark.parametrize(
    ("title", "explicit_values"),
    [
        (
            "Apple Generic Product",
            {},
        ),
        (
            "Generic Product",
            {
                "model_number": "ZX-900",
            },
        ),
        (
            "Generic Storage Device 256GB",
            {},
        ),
        (
            "Generic Product Limited Edition",
            {},
        ),
    ],
)
def test_strong_identity_removes_normalized_title(
    title: str,
    explicit_values: dict[str, str],
) -> None:
    factory = ProductDraftFactory()

    attributes = extract_product_attributes(
        title,
        **explicit_values,
    )

    assert (
        ProductDraftFactory
        ._has_strong_identity(attributes)
        is True
    )

    draft = factory.from_attributes(
        attributes
    )

    assert (
        "normalized_title"
        not in draft.attributes
    )


@pytest.mark.parametrize(
    "title",
    [
        "Generic Black Product",
        "Generic Product Size XL",
    ],
)
def test_weak_color_or_size_preserves_title(
    title: str,
) -> None:
    factory = ProductDraftFactory()

    attributes = extract_product_attributes(
        title
    )

    assert (
        ProductDraftFactory
        ._has_strong_identity(attributes)
        is False
    )

    draft = factory.from_attributes(
        attributes
    )

    assert (
        draft.attributes["normalized_title"]
        == attributes.normalized_title
    )


def test_different_weak_identity_titles_produce_different_drafts() -> None:
    factory = ProductDraftFactory()

    first_attributes = extract_product_attributes(
        "Generic Smartphone Alpha New",
        category="smartphone",
        condition="new",
    )

    second_attributes = extract_product_attributes(
        "Generic Smartphone Beta New",
        category="smartphone",
        condition="new",
    )

    first_draft = factory.from_attributes(
        first_attributes
    )

    second_draft = factory.from_attributes(
        second_attributes
    )

    assert first_draft.category == second_draft.category
    assert first_draft.condition == second_draft.condition

    assert (
        first_draft.attributes["normalized_title"]
        != second_draft.attributes["normalized_title"]
    )

    assert first_draft != second_draft


def test_same_weak_identity_title_produces_same_draft_identity() -> None:
    factory = ProductDraftFactory()

    first_attributes = extract_product_attributes(
        "Generic Smartphone Alpha New",
        category="smartphone",
        condition="new",
    )

    second_attributes = extract_product_attributes(
        "  Generic Smartphone Alpha New  ",
        category="smartphone",
        condition="new",
    )

    first_draft = factory.from_attributes(
        first_attributes
    )

    second_draft = factory.from_attributes(
        second_attributes
    )

    assert (
        first_draft.attributes["normalized_title"]
        == second_draft.attributes["normalized_title"]
    )

    assert first_draft == second_draft


def test_from_product_preserves_title_for_weak_identity_only() -> None:
    factory = ProductDraftFactory()

    product = make_product(
        title="Unknown Smartphone Prototype New",
        category="smartphone",
        condition="new",
    )

    draft = factory.from_product(
        product
    )

    assert draft.category == "smartphone"
    assert draft.condition == "new"

    assert (
        draft.attributes["normalized_title"]
        == "unknown smartphone prototype new"
    )


def test_from_product_removes_title_when_brand_exists() -> None:
    factory = ProductDraftFactory()

    product = make_product(
        title="Apple Generic Device New",
        brand="Apple",
        category="smartphone",
        condition="new",
    )

    draft = factory.from_product(
        product
    )

    assert draft.brand == "apple"

    assert (
        "normalized_title"
        not in draft.attributes
    )


def test_strong_identity_validation_rejects_invalid_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "attributes는 ProductAttributes "
            "객체여야 합니다"
        ),
    ):
        ProductDraftFactory._has_strong_identity(
            object(),  # type: ignore[arg-type]
        )


def test_weak_identity_validation_rejects_invalid_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "attributes는 ProductAttributes "
            "객체여야 합니다"
        ),
    ):
        ProductDraftFactory._has_weak_identity(
            object(),  # type: ignore[arg-type]
        )