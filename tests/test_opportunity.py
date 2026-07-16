from engine.opportunity import calculate_opportunity

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
