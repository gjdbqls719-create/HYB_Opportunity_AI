import pytest

from marketplaces.amazon import (
    AmazonAdapter,
    search_products,
)


def test_amazon_adapter_normalizes_product() -> None:
    adapter = AmazonAdapter()

    raw_product = {
        "asin": "B000TEST",
        "title": "Test Product",
        "price": "$49.99",
        "currency": "USD",
        "condition": "New",
        "url": "https://www.amazon.com/dp/B000TEST",
    }

    product = adapter.normalize(raw_product)

    assert product.marketplace == "amazon"
    assert product.item_id == "B000TEST"
    assert product.title == "Test Product"
    assert product.price == 49.99
    assert product.currency == "USD"


def test_search_products_returns_products() -> None:
    products = search_products(
        query="headphones",
        limit=2,
    )

    assert len(products) == 2
    assert all(
        product.marketplace == "amazon"
        for product in products
    )


def test_search_products_rejects_empty_query() -> None:
    with pytest.raises(ValueError):
        search_products("   ")