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

def test_calculate_opportunity_includes_all_sprint3_costs() -> None:
    result = calculate_opportunity(
        {
            "purchase_price": 50,
            "selling_price": 100,
            "marketplace_fee_rate": 0.10,
            "payment_fee_rate": 0.03,
            "tax_rate": 0.05,
            "shipping_cost": 8,
            "other_cost": 4,
            "estimated_monthly_sales": 10,
            "competitor_count": 8,
            "risk_level": "medium",
        }
    )

    assert result["marketplace_fee"] == 10.0
    assert result["payment_fee"] == 3.0
    assert result["tax_cost"] == 5.0
    assert result["landed_cost"] == 62.0
    assert result["total_cost"] == 80.0
    assert result["net_profit"] == 20.0
    assert result["margin_rate"] == 20.0
    assert result["roi"] == 40.0
    assert result["landed_cost_roi"] == 32.3


def test_profitability_filter_forces_rejection() -> None:
    result = calculate_opportunity(
        {
            "purchase_price": 70,
            "selling_price": 100,
            "marketplace_fee_rate": 0.10,
            "shipping_cost": 5,
            "minimum_net_profit": 20,
            "minimum_roi": 25,
            "estimated_monthly_sales": 500,
            "competitor_count": 1,
            "risk_level": "low",
        }
    )

    assert result["net_profit"] == 15.0
    assert result["passes_profitability_filter"] is False
    assert result["recommendation"] == "비추천"
    assert result["decision_reason"] == "최소 수익성 기준 미달"
    assert result["risk_warnings"]


def test_invalid_payment_fee_rate_is_rejected() -> None:
    try:
        calculate_opportunity(
            {
                "purchase_price": 10,
                "selling_price": 20,
                "payment_fee_rate": 1.1,
            }
        )
    except ValueError as error:
        assert "결제 수수료율" in str(error)
    else:
        raise AssertionError("ValueError가 발생해야 합니다.")
