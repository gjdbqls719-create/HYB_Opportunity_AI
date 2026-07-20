from app.models import Product
from engine.product_matching import (
    compare_product_titles,
    compare_products,
    normalize_product_title,
)


def test_normalize_product_title() -> None:
    title = "Apple iPhone17 128 GB - Black!"

    result = normalize_product_title(title)

    assert result == "apple iphone 17 128gb black"


def test_similar_titles_are_matched() -> None:
    result = compare_product_titles(
        "Apple iPhone 17 128GB Black",
        "Apple iPhone17 Black 128 GB",
    )

    assert result.is_match is True
    assert result.score >= 75
    assert "apple" in result.common_tokens
    assert "128gb" in result.common_tokens


def test_different_products_are_not_matched() -> None:
    result = compare_product_titles(
        "Apple iPhone 17 128GB Black",
        "Samsung Galaxy Buds Pro White",
    )

    assert result.is_match is False
    assert result.score < 75


def test_compare_product_objects() -> None:
    ebay_product = Product(
        marketplace="ebay",
        item_id="ebay-1",
        title="Apple iPhone 17 128GB Black",
        price=700.0,
        currency="USD",
        condition="New",
        url="https://example.com/ebay",
    )

    amazon_product = Product(
        marketplace="amazon",
        item_id="amazon-1",
        title="Apple iPhone17 Black 128 GB",
        price=850.0,
        currency="USD",
        condition="New",
        url="https://example.com/amazon",
    )

    result = compare_products(
        ebay_product,
        amazon_product,
    )

    assert result.is_match is True
    assert result.score >= 75