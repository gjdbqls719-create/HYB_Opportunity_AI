from __future__ import annotations

from math import inf, nan
from typing import Any

import pytest

from app.models import Product
from collectors.base import (
    MarketplaceAdapter,
    MarketplaceValidationError,
    parse_price,
    parse_rating,
    parse_review_count,
)
from marketplaces.amazon import AmazonAdapter
from marketplaces.ebay import EbayAdapter


def make_product(**overrides: Any) -> Product:
    values: dict[str, Any] = {
        "marketplace": "test-market",
        "item_id": "ITEM-001",
        "title": "Validated Product",
        "price": 10.0,
        "currency": "USD",
        "condition": "New",
        "url": "https://example.com/item/ITEM-001",
    }
    values.update(overrides)
    return Product(**values)


class StubAdapter(MarketplaceAdapter):
    marketplace_name = "test-market"

    def __init__(self, product: Product) -> None:
        self.product = product

    def normalize(self, raw_product: dict[str, Any]) -> Product:
        return self.product


def test_normalize_and_validate_rejects_non_dict_raw_product() -> None:
    adapter = StubAdapter(make_product())

    with pytest.raises(
        MarketplaceValidationError,
        match="dict 형식",
    ):
        adapter.normalize_and_validate([])  # type: ignore[arg-type]


def test_validate_product_rejects_marketplace_mismatch() -> None:
    adapter = StubAdapter(make_product(marketplace="other-market"))

    with pytest.raises(
        MarketplaceValidationError,
        match="Adapter와 일치하지 않습니다",
    ):
        adapter.normalize_and_validate({})


def test_validate_product_rejects_missing_item_id() -> None:
    adapter = StubAdapter(make_product(item_id=""))

    with pytest.raises(
        MarketplaceValidationError,
        match="상품 ID",
    ):
        adapter.normalize_and_validate({})


@pytest.mark.parametrize("value", [nan, inf, -inf, "nan", "inf", "-inf"])
def test_parse_price_rejects_non_finite_values(value: object) -> None:
    with pytest.raises(ValueError, match="유한한 숫자"):
        parse_price(value)


def test_parse_rating_rejects_non_finite_value() -> None:
    with pytest.raises(ValueError, match="유한한 숫자"):
        parse_rating("nan")


def test_parse_review_count_rejects_boolean() -> None:
    with pytest.raises(ValueError, match="True 또는 False"):
        parse_review_count(True)


@pytest.mark.parametrize("adapter_type", [AmazonAdapter, EbayAdapter])
def test_real_adapters_reject_missing_marketplace_item_id(
    adapter_type: type[MarketplaceAdapter],
) -> None:
    adapter = adapter_type()

    if adapter_type is AmazonAdapter:
        raw_product = {
            "title": "Missing ID",
            "price": "10.00",
            "currency": "USD",
        }
    else:
        raw_product = {
            "title": "Missing ID",
            "price": {"value": "10.00", "currency": "USD"},
        }

    with pytest.raises(MarketplaceValidationError, match="상품 ID"):
        adapter.normalize_and_validate(raw_product)
