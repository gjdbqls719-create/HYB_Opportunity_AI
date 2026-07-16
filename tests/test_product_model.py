import pytest

from database.models import Product


def test_product_total_cost() -> None:
    product = Product(
        name="Wireless Gaming Mouse",
        marketplace="eBay",
        price=18.0,
        currency="usd",
        shipping_cost=4.0,
        brand="Example",
    )

    assert product.currency == "USD"
    assert product.total_cost == 22.0
    assert product.to_dict()["marketplace"] == "eBay"


def test_product_rejects_negative_price() -> None:
    with pytest.raises(ValueError):
        Product(
            name="Invalid Product",
            marketplace="Amazon",
            price=-1.0,
            currency="USD",
        )


def test_product_rejects_invalid_rating() -> None:
    with pytest.raises(ValueError):
        Product(
            name="Invalid Rating Product",
            marketplace="Walmart",
            price=10.0,
            currency="USD",
            rating=6.0,
        )