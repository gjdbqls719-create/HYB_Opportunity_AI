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

def test_get_item_by_id_returns_exact_fake_catalog_item() -> None:
    from marketplaces.amazon import get_item_by_id

    item = get_item_by_id(" amz-002 ")

    assert item is not None
    assert item["asin"] == "AMZ-002"
    assert item["price"] == 84.50


def test_get_item_by_id_returns_none_when_asin_is_unknown() -> None:
    from marketplaces.amazon import get_item_by_id

    assert get_item_by_id("UNKNOWN-ASIN") is None


@pytest.mark.parametrize("item_id", ["", "   "])
def test_get_item_by_id_rejects_empty_asin(item_id: str) -> None:
    from marketplaces.amazon import get_item_by_id

    with pytest.raises(ValueError, match="ASIN"):
        get_item_by_id(item_id)


def test_get_product_by_id_returns_valid_product() -> None:
    from marketplaces.amazon import get_product_by_id

    product = get_product_by_id("AMZ-003")

    assert product is not None
    assert product.marketplace == "amazon"
    assert product.item_id == "AMZ-003"
    assert product.price == 109.99


def test_get_product_by_id_returns_none_when_missing() -> None:
    from marketplaces.amazon import get_product_by_id

    assert get_product_by_id("UNKNOWN-ASIN") is None
