from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.models import Product
from services.fees import calculate_marketplace_fee
from services.shipping import resolve_shipping_cost


MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.1")


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:
        raise ValueError(
            f"{field_name}은(는) 숫자여야 합니다."
        ) from error


def _money(value: Decimal) -> float:
    return float(
        value.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    )


def _percent(value: Decimal) -> float:
    return float(
        value.quantize(
            PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    )


def _validate_non_negative(
    value: Decimal,
    field_name: str,
) -> None:
    if value < 0:
        raise ValueError(
            f"{field_name}은(는) 0 이상이어야 합니다."
        )


def _validate_rate(
    value: Decimal,
    field_name: str,
) -> None:
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(
            f"{field_name}은(는) 0 이상 1 이하여야 합니다."
        )


def calculate_opportunity(
    product: dict[str, Any],
) -> dict[str, Any]:
    """
    상품 한 건의 비용, 수익성, 점수,
    판정 근거를 계산한다.

    기존 dict 입력 방식을 유지하면서
    Marketplace Fee Engine을 지원한다.

    use_fee_profile=True이면 마켓플레이스별
    기본 수수료 프로필을 사용한다.

    기본값 False에서는 기존 계산 방식과
    호환되도록 15% 수수료를 사용한다.
    """
    purchase_price = _decimal(
        product.get("purchase_price", 0),
        "구매가",
    )
    selling_price = _decimal(
        product.get("selling_price", 0),
        "판매가",
    )

    tax_rate = _decimal(
        product.get("tax_rate", 0),
        "세율",
    )
    shipping_cost = _decimal(
        product.get("shipping_cost", 0),
        "배송비",
    )
    other_cost = _decimal(
        product.get("other_cost", 0),
        "기타 비용",
    )
    minimum_net_profit = _decimal(
        product.get("minimum_net_profit", 0),
        "최소 순이익",
    )
    minimum_roi = _decimal(
        product.get("minimum_roi", 0),
        "최소 ROI",
    )

    monthly_sales = int(
        product.get(
            "estimated_monthly_sales",
            0,
        )
    )
    competitor_count = int(
        product.get(
            "competitor_count",
            0,
        )
    )
    risk_level = str(
        product.get(
            "risk_level",
            "medium",
        )
    ).strip().lower()

    marketplace = str(
        product.get(
            "marketplace",
            "default",
        )
    ).strip().lower()

    use_fee_profile = bool(
        product.get(
            "use_fee_profile",
            False,
        )
    )

    for value, name in (
        (purchase_price, "구매가"),
        (selling_price, "판매가"),
        (shipping_cost, "배송비"),
        (other_cost, "기타 비용"),
        (minimum_net_profit, "최소 순이익"),
        (minimum_roi, "최소 ROI"),
    ):
        _validate_non_negative(
            value,
            name,
        )

    _validate_rate(
        tax_rate,
        "세율",
    )

    if monthly_sales < 0:
        raise ValueError(
            "예상 월 판매량은 0 이상이어야 합니다."
        )

    if competitor_count < 0:
        raise ValueError(
            "경쟁 판매자 수는 0 이상이어야 합니다."
        )

    if risk_level not in {
        "low",
        "medium",
        "high",
    }:
        raise ValueError(
            "위험도는 low, medium, high 중 "
            "하나여야 합니다."
        )

    if use_fee_profile:
        fee_breakdown = calculate_marketplace_fee(
            marketplace=marketplace,
            selling_price=selling_price,
            marketplace_fee_rate=product.get(
                "marketplace_fee_rate"
            ),
            payment_fee_rate=product.get(
                "payment_fee_rate"
            ),
            fixed_fee=product.get(
                "fixed_fee"
            ),
        )
    else:
        marketplace_fee_rate = _decimal(
            product.get(
                "marketplace_fee_rate",
                0.15,
            ),
            "마켓플레이스 수수료율",
        )
        payment_fee_rate = _decimal(
            product.get(
                "payment_fee_rate",
                0,
            ),
            "결제 수수료율",
        )
        fixed_fee = _decimal(
            product.get(
                "fixed_fee",
                0,
            ),
            "고정 수수료",
        )

        _validate_rate(
            marketplace_fee_rate,
            "마켓플레이스 수수료율",
        )
        _validate_rate(
            payment_fee_rate,
            "결제 수수료율",
        )
        _validate_non_negative(
            fixed_fee,
            "고정 수수료",
        )

        fee_breakdown = calculate_marketplace_fee(
            marketplace=marketplace,
            selling_price=selling_price,
            marketplace_fee_rate=(
                marketplace_fee_rate
            ),
            payment_fee_rate=(
                payment_fee_rate
            ),
            fixed_fee=fixed_fee,
        )

    marketplace_fee = (
        fee_breakdown.marketplace_fee
    )
    payment_fee = (
        fee_breakdown.payment_fee
    )
    fixed_fee = fee_breakdown.fixed_fee
    total_marketplace_fees = (
        fee_breakdown.total_fee
    )

    tax_cost = selling_price * tax_rate

    selling_cost = (
        total_marketplace_fees
        + tax_cost
    )

    landed_cost = (
        purchase_price
        + shipping_cost
        + other_cost
    )

    total_cost = (
        landed_cost
        + selling_cost
    )

    net_profit = (
        selling_price
        - total_cost
    )

    roi = (
        net_profit
        / purchase_price
        * Decimal("100")
        if purchase_price > 0
        else Decimal("0")
    )

    landed_cost_roi = (
        net_profit
        / landed_cost
        * Decimal("100")
        if landed_cost > 0
        else Decimal("0")
    )

    margin_rate = (
        net_profit
        / selling_price
        * Decimal("100")
        if selling_price > 0
        else Decimal("0")
    )

    score = 0
    reasons: list[str] = []
    risk_warnings: list[str] = []

    if roi >= 50:
        score += 40
        reasons.append(
            "ROI가 매우 높음"
        )
    elif roi >= 30:
        score += 30
        reasons.append(
            "ROI가 높음"
        )
    elif roi >= 15:
        score += 20
        reasons.append(
            "ROI가 보통 이상"
        )
    elif roi > 0:
        score += 10
        reasons.append(
            "수익은 남지만 ROI가 낮음"
        )
    else:
        reasons.append(
            "예상 순이익이 없음"
        )
        risk_warnings.append(
            "판매 후 손실 가능성이 있습니다."
        )

    if monthly_sales >= 500:
        score += 30
        reasons.append(
            "예상 판매량이 매우 높음"
        )
    elif monthly_sales >= 200:
        score += 22
        reasons.append(
            "예상 판매량이 높음"
        )
    elif monthly_sales >= 50:
        score += 15
        reasons.append(
            "예상 판매량이 보통"
        )
    elif monthly_sales > 0:
        score += 7
        reasons.append(
            "예상 판매량이 낮음"
        )
    else:
        reasons.append(
            "판매량 데이터가 없음"
        )
        risk_warnings.append(
            "판매량 데이터가 없어 "
            "수요 신뢰도가 낮습니다."
        )

    if competitor_count <= 5:
        score += 20
        reasons.append(
            "경쟁 판매자가 적음"
        )
    elif competitor_count <= 20:
        score += 14
        reasons.append(
            "경쟁이 보통"
        )
    elif competitor_count <= 50:
        score += 7
        reasons.append(
            "경쟁이 높음"
        )
        risk_warnings.append(
            "경쟁 판매자가 많아 "
            "가격 하락 가능성이 있습니다."
        )
    else:
        reasons.append(
            "경쟁 판매자가 매우 많음"
        )
        risk_warnings.append(
            "경쟁이 매우 높아 판매 속도와 "
            "마진이 악화될 수 있습니다."
        )

    if risk_level == "low":
        score += 10
        reasons.append(
            "위험도가 낮음"
        )
    elif risk_level == "medium":
        score += 5
        reasons.append(
            "위험도가 보통"
        )
    else:
        reasons.append(
            "위험도가 높음"
        )
        risk_warnings.append(
            "상품 또는 거래 위험도가 "
            "높게 설정되었습니다."
        )

    passes_net_profit_filter = (
        net_profit
        >= minimum_net_profit
    )
    passes_roi_filter = (
        roi
        >= minimum_roi
    )
    passes_profitability_filter = (
        passes_net_profit_filter
        and passes_roi_filter
    )

    if not passes_net_profit_filter:
        risk_warnings.append(
            "순이익이 최소 기준 "
            f"{_money(minimum_net_profit):.2f}"
            "보다 낮습니다."
        )

    if not passes_roi_filter:
        risk_warnings.append(
            "ROI가 최소 기준 "
            f"{_percent(minimum_roi):.1f}%"
            "보다 낮습니다."
        )

    score = max(
        0,
        min(
            round(score),
            100,
        ),
    )

    if not passes_profitability_filter:
        recommendation = "비추천"
    elif score >= 85:
        recommendation = "강력 추천"
    elif score >= 70:
        recommendation = "추천"
    elif score >= 50:
        recommendation = "검토"
    elif score >= 30:
        recommendation = "주의"
    else:
        recommendation = "비추천"

    decision_reason = "; ".join(
        reasons[:3]
    )

    if not passes_profitability_filter:
        decision_reason = (
            "최소 수익성 기준 미달"
        )

    result = product.copy()

    result.update(
        {
            "marketplace": marketplace,
            "marketplace_fee_rate": float(
                fee_breakdown.marketplace_fee_rate
            ),
            "payment_fee_rate": float(
                fee_breakdown.payment_fee_rate
            ),
            "fixed_fee": _money(
                fixed_fee
            ),
            "marketplace_fee": _money(
                marketplace_fee
            ),
            "payment_fee": _money(
                payment_fee
            ),
            "total_marketplace_fees": _money(
                total_marketplace_fees
            ),
            "total_fee_rate": float(
                fee_breakdown.total_fee_rate
            ),
            "fee_source": (
                fee_breakdown.source
            ),
            "use_fee_profile": (
                use_fee_profile
            ),
            "tax_cost": _money(
                tax_cost
            ),
            "selling_cost": _money(
                selling_cost
            ),
            "landed_cost": _money(
                landed_cost
            ),
            "total_cost": _money(
                total_cost
            ),
            "net_profit": _money(
                net_profit
            ),
            "margin_rate": _percent(
                margin_rate
            ),
            "roi": _percent(
                roi
            ),
            "landed_cost_roi": _percent(
                landed_cost_roi
            ),
            "estimated_monthly_profit": _money(
                net_profit
                * monthly_sales
            ),
            "opportunity_score": score,
            "recommendation": recommendation,
            "decision_reason": decision_reason,
            "reasons": reasons,
            "risk_warnings": risk_warnings,
            "passes_net_profit_filter": (
                passes_net_profit_filter
            ),
            "passes_roi_filter": (
                passes_roi_filter
            ),
            "passes_profitability_filter": (
                passes_profitability_filter
            ),
        }
    )

    return result


def calculate_product_opportunity(
    product: Product,
    selling_price: float,
    shipping_cost: float | None = None,
    marketplace_fee_rate: float | None = None,
    payment_fee_rate: float | None = None,
    fixed_fee: float | None = None,
    tax_rate: float = 0,
    other_cost: float = 0,
    minimum_net_profit: float = 0,
    minimum_roi: float = 0,
    estimated_monthly_sales: int = 0,
    competitor_count: int = 0,
    risk_level: str = "medium",
    use_fee_profile: bool = False,
) -> dict[str, Any]:
    """
    공통 Product 모델을 Opportunity Engine 입력으로
    변환한다.

    use_fee_profile=True로 설정하면 marketplace에
    맞는 수수료 프로필을 사용한다.

    프로필 사용 중에도 수수료 값을 직접 전달하면
    해당 값만 재정의할 수 있다.
    """
    shipping = resolve_shipping_cost(
        product.shipping_cost,
        shipping_cost,
    )

    opportunity_input: dict[str, Any] = {
        "marketplace": product.marketplace,
        "item_id": product.item_id,
        "name": product.title,
        "url": product.url,
        "condition": product.condition,
        "currency": product.currency,
        "purchase_price": product.price,
        "selling_price": selling_price,
        "tax_rate": tax_rate,
        "shipping_cost": shipping.cost,
        "shipping_cost_source": (
            shipping.source
        ),
        "is_free_shipping": (
            shipping.is_free_shipping
        ),
        "other_cost": other_cost,
        "minimum_net_profit": (
            minimum_net_profit
        ),
        "minimum_roi": minimum_roi,
        "estimated_monthly_sales": (
            estimated_monthly_sales
        ),
        "competitor_count": (
            competitor_count
        ),
        "risk_level": risk_level,
        "use_fee_profile": (
            use_fee_profile
        ),
    }

    if marketplace_fee_rate is not None:
        opportunity_input[
            "marketplace_fee_rate"
        ] = marketplace_fee_rate

    if payment_fee_rate is not None:
        opportunity_input[
            "payment_fee_rate"
        ] = payment_fee_rate

    if fixed_fee is not None:
        opportunity_input[
            "fixed_fee"
        ] = fixed_fee

    return calculate_opportunity(
        opportunity_input
    )