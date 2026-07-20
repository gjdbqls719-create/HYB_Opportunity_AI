from app.models import Product
from engine.opportunity import (
    calculate_opportunity,
    calculate_product_opportunity,
)


def test_calculate_opportunity() -> None:
    product = {
        "name": "Wireless Gaming Mouse",
        "purchase_price": 18.0,
        "selling_price": 39.99,
        "marketplace_fee_rate": 0.15,
        "shipping_cost": 4.0,
        "estimated_monthly_sales": 240,
        "competitor_count": 12,
        "risk_level": "low",
    }

    result = calculate_opportunity(product)

    assert result["net_profit"] == 11.99
    assert result["roi"] == 66.6
    assert result["opportunity_score"] == 86
    assert result["recommendation"] == "강력 추천"


def test_calculate_product_opportunity() -> None:
    product = Product(
        marketplace="ebay",
        item_id="v1|123456|0",
        title="Wireless Gaming Mouse",
        price=18.0,
        currency="USD",
        condition="New",
        url="https://example.com/product",
    )

    result = calculate_product_opportunity(
        product=product,
        selling_price=39.99,
        shipping_cost=4.0,
        marketplace_fee_rate=0.15,
        estimated_monthly_sales=240,
        competitor_count=12,
        risk_level="low",
    )

    assert result["item_id"] == "v1|123456|0"
    assert result["marketplace"] == "ebay"
    assert result["purchase_price"] == 18.0
    assert result["net_profit"] == 11.99
    assert result["roi"] == 66.6
    assert result["opportunity_score"] == 86
    assert result["recommendation"] == "강력 추천"