from engine.opportunity import calculate_opportunity

def run_demo() -> None:
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
    print("HYB Opportunity AI")
    print("=" * 40)
    print("상품명:", result["name"])
    print("예상 순이익: $", result["net_profit"])
    print("ROI:", result["roi"], "%")
    print("예상 월 수익: $", result["estimated_monthly_profit"])
    print("Opportunity Score:", result["opportunity_score"])
    print("판정:", result["recommendation"])
    for reason in result["reasons"]:
        print("-", reason)
