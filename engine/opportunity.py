from __future__ import annotations

from typing import Any

from app.models import Product


def calculate_opportunity(
    product: dict[str, Any],
) -> dict[str, Any]:
    """
    상품의 수익성, 판매량, 경쟁도, 위험도를 바탕으로
    기회 점수와 추천 결과를 계산한다.
    """
    purchase_price = float(product.get("purchase_price", 0))
    selling_price = float(product.get("selling_price", 0))
    fee_rate = float(
        product.get("marketplace_fee_rate", 0.15)
    )
    shipping_cost = float(product.get("shipping_cost", 0))
    monthly_sales = int(
        product.get("estimated_monthly_sales", 0)
    )
    competitor_count = int(
        product.get("competitor_count", 0)
    )
    risk_level = str(
        product.get("risk_level", "medium")
    ).strip().lower()

    if purchase_price < 0:
        raise ValueError("구매가는 0 이상이어야 합니다.")

    if selling_price < 0:
        raise ValueError("판매가는 0 이상이어야 합니다.")

    if shipping_cost < 0:
        raise ValueError("배송비는 0 이상이어야 합니다.")

    if not 0 <= fee_rate <= 1:
        raise ValueError(
            "마켓플레이스 수수료율은 0 이상 1 이하여야 합니다."
        )

    if monthly_sales < 0:
        raise ValueError(
            "예상 월 판매량은 0 이상이어야 합니다."
        )

    if competitor_count < 0:
        raise ValueError(
            "경쟁 판매자 수는 0 이상이어야 합니다."
        )

    if risk_level not in {"low", "medium", "high"}:
        raise ValueError(
            "위험도는 low, medium, high 중 하나여야 합니다."
        )

    marketplace_fee = selling_price * fee_rate

    net_profit = (
        selling_price
        - purchase_price
        - marketplace_fee
        - shipping_cost
    )

    roi = (
        net_profit / purchase_price * 100
        if purchase_price > 0
        else 0
    )

    score = 0
    reasons: list[str] = []

    if roi >= 50:
        score += 40
        reasons.append("ROI가 매우 높음")
    elif roi >= 30:
        score += 30
        reasons.append("ROI가 높음")
    elif roi >= 15:
        score += 20
        reasons.append("ROI가 보통 이상")
    elif roi > 0:
        score += 10
        reasons.append("수익은 남지만 ROI가 낮음")
    else:
        reasons.append("예상 순이익이 없음")

    if monthly_sales >= 500:
        score += 30
        reasons.append("예상 판매량이 매우 높음")
    elif monthly_sales >= 200:
        score += 22
        reasons.append("예상 판매량이 높음")
    elif monthly_sales >= 50:
        score += 15
        reasons.append("예상 판매량이 보통")
    elif monthly_sales > 0:
        score += 7
        reasons.append("예상 판매량이 낮음")
    else:
        reasons.append("판매량 데이터가 없음")

    if competitor_count <= 5:
        score += 20
        reasons.append("경쟁 판매자가 적음")
    elif competitor_count <= 20:
        score += 14
        reasons.append("경쟁이 보통")
    elif competitor_count <= 50:
        score += 7
        reasons.append("경쟁이 높음")
    else:
        reasons.append("경쟁 판매자가 매우 많음")

    if risk_level == "low":
        score += 10
        reasons.append("위험도가 낮음")
    elif risk_level == "medium":
        score += 5
        reasons.append("위험도가 보통")
    else:
        reasons.append("위험도가 높음")

    score = max(0, min(round(score), 100))

    if score >= 85:
        recommendation = "강력 추천"
    elif score >= 70:
        recommendation = "추천"
    elif score >= 50:
        recommendation = "검토"
    elif score >= 30:
        recommendation = "주의"
    else:
        recommendation = "비추천"

    result = product.copy()

    result.update(
        {
            "marketplace_fee": round(
                marketplace_fee,
                2,
            ),
            "net_profit": round(net_profit, 2),
            "roi": round(roi, 1),
            "estimated_monthly_profit": round(
                net_profit * monthly_sales,
                2,
            ),
            "opportunity_score": score,
            "recommendation": recommendation,
            "reasons": reasons,
        }
    )

    return result


def calculate_product_opportunity(
    product: Product,
    selling_price: float,
    shipping_cost: float = 0,
    marketplace_fee_rate: float = 0.15,
    estimated_monthly_sales: int = 0,
    competitor_count: int = 0,
    risk_level: str = "medium",
) -> dict[str, Any]:
    """
    공통 Product 객체를 Opportunity Engine에 연결한다.

    product.price는 매입 후보 가격으로 사용하며,
    아직 수집되지 않은 시장 데이터는 인자로 전달받는다.
    """
    opportunity_input: dict[str, Any] = {
        "marketplace": product.marketplace,
        "item_id": product.item_id,
        "name": product.title,
        "url": product.url,
        "condition": product.condition,
        "currency": product.currency,
        "purchase_price": product.price,
        "selling_price": selling_price,
        "marketplace_fee_rate": marketplace_fee_rate,
        "shipping_cost": shipping_cost,
        "estimated_monthly_sales": estimated_monthly_sales,
        "competitor_count": competitor_count,
        "risk_level": risk_level,
    }

    return calculate_opportunity(opportunity_input)