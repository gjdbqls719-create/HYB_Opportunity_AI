from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.models.canonical_product import (
    CanonicalProduct,
)


def test_canonical_product_can_be_created() -> None:
    product = CanonicalProduct(
        display_id="CP-000001",
        brand="Apple",
        model="iPhone 15 Pro",
        category="smartphone",
        capacity="256GB",
        color="Black",
    )

    assert isinstance(product.id, UUID)
    assert product.display_id == "CP-000001"
    assert product.brand == "Apple"
    assert product.model == "iPhone 15 Pro"
    assert product.capacity == "256GB"
    assert product.color == "Black"


def test_internal_id_can_be_provided() -> None:
    internal_id = uuid4()

    product = CanonicalProduct(
        id=internal_id,
        display_id="CP-000002",
    )

    assert product.id == internal_id


def test_internal_id_is_generated_automatically() -> None:
    left = CanonicalProduct(
        display_id="CP-000003",
    )
    right = CanonicalProduct(
        display_id="CP-000004",
    )

    assert left.id != right.id


@pytest.mark.parametrize(
    "invalid_display_id",
    [
        "",
        " ",
        "000001",
        "CP-1",
        "CP-00001",
        "PRODUCT-000001",
        "cp-000001",
    ],
)
def test_invalid_display_id_raises_value_error(
    invalid_display_id: str,
) -> None:
    with pytest.raises(ValueError):
        CanonicalProduct(
            display_id=invalid_display_id,
        )


def test_optional_text_fields_are_trimmed() -> None:
    product = CanonicalProduct(
        display_id="  CP-000005  ",
        brand="  Apple  ",
        model="  iPhone 15 Pro  ",
        category="  smartphone  ",
    )

    assert product.display_id == "CP-000005"
    assert product.brand == "Apple"
    assert product.model == "iPhone 15 Pro"
    assert product.category == "smartphone"


def test_blank_optional_text_becomes_none() -> None:
    product = CanonicalProduct(
        display_id="CP-000006",
        brand="   ",
        model="",
    )

    assert product.brand is None
    assert product.model is None


def test_attributes_are_stored() -> None:
    product = CanonicalProduct(
        display_id="CP-000007",
        attributes={
            "ram": "8GB",
            "storage_type": "SSD",
        },
    )

    assert product.attributes["ram"] == "8GB"
    assert product.attributes["storage_type"] == "SSD"


def test_attributes_are_read_only() -> None:
    product = CanonicalProduct(
        display_id="CP-000008",
        attributes={
            "ram": "8GB",
        },
    )

    with pytest.raises(TypeError):
        product.attributes["ram"] = "16GB"  # type: ignore[index]


def test_attributes_are_copied_from_source() -> None:
    source_attributes = {
        "ram": "8GB",
    }

    product = CanonicalProduct(
        display_id="CP-000009",
        attributes=source_attributes,
    )

    source_attributes["ram"] = "16GB"

    assert product.attributes["ram"] == "8GB"


def test_model_is_immutable() -> None:
    product = CanonicalProduct(
        display_id="CP-000010",
        brand="Apple",
    )

    with pytest.raises(FrozenInstanceError):
        product.brand = "Samsung"  # type: ignore[misc]


def test_created_and_updated_times_are_timezone_aware() -> None:
    product = CanonicalProduct(
        display_id="CP-000011",
    )

    assert product.created_at.tzinfo is not None
    assert product.updated_at.tzinfo is not None
    assert product.updated_at >= product.created_at


def test_naive_datetime_is_rejected() -> None:
    naive_datetime = datetime.now()

    with pytest.raises(ValueError):
        CanonicalProduct(
            display_id="CP-000012",
            created_at=naive_datetime,
            updated_at=naive_datetime,
        )


def test_updated_at_cannot_be_before_created_at() -> None:
    created_at = datetime.now(timezone.utc)
    updated_at = created_at - timedelta(seconds=1)

    with pytest.raises(ValueError):
        CanonicalProduct(
            display_id="CP-000013",
            created_at=created_at,
            updated_at=updated_at,
        )


def test_identity_summary_contains_available_fields() -> None:
    product = CanonicalProduct(
        display_id="CP-000014",
        brand="Apple",
        model="iPhone 15 Pro",
        edition="Max",
        capacity="256GB",
        color="Black",
    )

    assert product.identity_summary == (
        "Apple iPhone 15 Pro Max 256GB Black"
    )


def test_identity_summary_omits_missing_fields() -> None:
    product = CanonicalProduct(
        display_id="CP-000015",
        brand="Apple",
        model="iPhone 15",
    )

    assert product.identity_summary == "Apple iPhone 15"