from __future__ import annotations
from typing import Any

def calculate_opportunity(product: dict[str, Any]) -> dict[str, Any]:
    purchase_price = float(product.get("purchase_price", 0))
    selling_price = float(product.get("selling_price", 0))
    fee_rate = float(product.get("marketplace_fee_rate", 0.15))
    shipping_cost = float(product.get("shipping_cost", 0))
    monthly_sales = int(product.get("estimated_monthly_sales", 0))
    competitor_count = int(product.get("competitor_count", 0))
    risk_level = str(product.get("risk_level", "medium")).lower()

    marketplace_fee = selling_price * fee_rate
    net_profit = selling_price - purchase_price - marketplace_fee - shipping_cost
    roi = (net_profit / purchase_price * 100) if purchase_price > 0 else 0

    score = 0
    reasons: list[str] = []

    if roi >= 50:
        score += 40; reasons.append("ROI가 매우 높음")
    elif roi >= 30:
        score += 30; reasons.append("ROI가 높음")
    elif roi >= 15:
        score += 20; reasons.append("ROI가 보통 이상")
    elif roi > 0:
        score += 10; reasons.append("수익은 남지만 ROI가 낮음")
    else:
        reasons.append("예상 순이익이 없음")

    if monthly_sales >= 500:
        score += 30; reasons.append("예상 판매량이 매우 높음")
    elif monthly_sales >= 200:
        score += 22; reasons.append("예상 판매량이 높음")
    elif monthly_sales >= 50:
        score += 15; reasons.append("예상 판매량이 보통")
    elif monthly_sales > 0:
        score += 7; reasons.append("예상 판매량이 낮음")
    else:
        reasons.append("판매량 데이터가 없음")

    if competitor_count <= 5:
        score += 20; reasons.append("경쟁 판매자가 적음")
    elif competitor_count <= 20:
        score += 14; reasons.append("경쟁이 보통")
    elif competitor_count <= 50:
        score += 7; reasons.append("경쟁이 높음")
    else:
        reasons.append("경쟁 판매자가 매우 많음")

    if risk_level == "low":
        score += 10; reasons.append("위험도가 낮음")
    elif risk_level == "medium":
        score += 5; reasons.append("위험도가 보통")
    else:
        reasons.append("위험도가 높음")

    score = max(0, min(round(score), 100))
    recommendation = (
        "강력 추천" if score >= 85 else
        "추천" if score >= 70 else
        "검토" if score >= 50 else
        "주의" if score >= 30 else
        "비추천"
    )

    result = product.copy()
    result.update({
        "marketplace_fee": round(marketplace_fee, 2),
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 1),
        "estimated_monthly_profit": round(net_profit * monthly_sales, 2),
        "opportunity_score": score,
        "recommendation": recommendation,
        "reasons": reasons,
    })
    return result
