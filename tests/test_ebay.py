from __future__ import annotations

import pytest

from app.models import Product
from collectors.base import MarketplaceAdapter
from marketplaces import ebay
from marketplaces.ebay import EbayAdapter, ebay_item_to_product


def make_raw_item() -> dict[str, object]:
    return {
        "itemId": "v1|123456789|0",
        "title": "Apple iPhone 15 Pro 256GB Black",
        "price": {
            "value": "999.99",
            "currency": "USD",
        },
        "condition": "New",
        "itemWebUrl": "https://www.ebay.com/itm/123456789",
    }


def test_ebay_adapter_implements_marketplace_contract() -> None:
    adapter = EbayAdapter()

    assert isinstance(adapter, MarketplaceAdapter)
    assert adapter.marketplace_name == "ebay"


def test_ebay_adapter_normalizes_product() -> None:
    product = EbayAdapter().normalize(make_raw_item())

    assert isinstance(product, Product)
    assert product.marketplace == "ebay"
    assert product.item_id == "v1|123456789|0"
    assert product.title == "Apple iPhone 15 Pro 256GB Black"
    assert product.price == 999.99
    assert product.currency == "USD"
    assert product.condition == "New"
    assert product.url == "https://www.ebay.com/itm/123456789"


@pytest.mark.parametrize(
    "raw_price",
    [None, "", "not-a-price", {"unexpected": "value"}],
)
def test_ebay_adapter_uses_zero_for_invalid_price(raw_price: object) -> None:
    raw_item = make_raw_item()
    raw_item["price"] = {
        "value": raw_price,
        "currency": "USD",
    }

    product = EbayAdapter().normalize(raw_item)

    assert product.price == 0.0


def test_legacy_conversion_function_uses_adapter_behavior() -> None:
    product = ebay_item_to_product(make_raw_item())

    assert product == EbayAdapter().normalize(make_raw_item())


def test_search_products_normalizes_all_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_items = [
        make_raw_item(),
        {
            **make_raw_item(),
            "itemId": "v1|987654321|0",
            "title": "Apple iPhone 15 Pro 512GB Black",
        },
    ]
    received: dict[str, object] = {}

    def fake_search_items(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[dict[str, object]]:
        received.update(
            query=query,
            limit=limit,
            marketplace_id=marketplace_id,
        )
        return raw_items

    monkeypatch.setattr(ebay, "search_items", fake_search_items)

    products = ebay.search_products(
        query="iphone",
        limit=2,
        marketplace_id="EBAY_US",
    )

    assert received == {
        "query": "iphone",
        "limit": 2,
        "marketplace_id": "EBAY_US",
    }
    assert [product.item_id for product in products] == [
        "v1|123456789|0",
        "v1|987654321|0",
    ]
    assert all(product.marketplace == "ebay" for product in products)
