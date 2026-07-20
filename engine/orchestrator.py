from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Product
from engine.opportunity import calculate_product_opportunity
from engine.product_matching import compare_products
from marketplaces.ebay import search_products


@dataclass(slots=True)
class ProductGroup:
    """
    서로 같은 상품으로 판단된 Product 묶음.
    """

    products: list[Product]

    @property
    def representative(self) -> Product:
        """
        그룹에서 가격이 가장 낮은 상품을 대표 상품으로 사용한다.
        """
        return min(
            self.products,
            key=lambda product: product.price,
        )


@dataclass(slots=True)
class OpportunityResult:
    """
    최종 상품 기회 분석 결과.
    """

    product: Product
    analysis: dict[str, Any]
    matched_product_count: int


def group_similar_products(
    products: list[Product],
    match_threshold: float = 75.0,
) -> list[ProductGroup]:
    """
    제목이 유사한 상품을 같은 그룹으로 묶는다.
    """
    if not 0 <= match_threshold <= 100:
        raise ValueError(
            "match_threshold는 0 이상 100 이하여야 합니다."
        )

    groups: list[ProductGroup] = []

    for product in products:
        matched_group: ProductGroup | None = None

        for group in groups:
            match_result = compare_products(
                product,
                group.representative,
                match_threshold=match_threshold,
            )

            if match_result.is_match:
                matched_group = group
                break

        if matched_group is None:
            groups.append(
                ProductGroup(products=[product])
            )
        else:
            matched_group.products.append(product)

    return groups


def find_best_opportunities(
    query: str,
    *,
    selling_price_multiplier: float = 1.5,
    shipping_cost: float = 0,
    marketplace_fee_rate: float = 0.15,
    estimated_monthly_sales: int = 100,
    competitor_count: int = 20,
    risk_level: str = "medium",
    limit: int = 10,
    match_threshold: float = 75.0,
) -> list[OpportunityResult]:
    """
    상품 검색부터 그룹화, 기회 분석, 정렬까지 실행한다.
    """
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    if selling_price_multiplier <= 0:
        raise ValueError(
            "selling_price_multiplier는 0보다 커야 합니다."
        )

    products = search_products(
        query=cleaned_query,
        limit=limit,
    )

    product_groups = group_similar_products(
        products,
        match_threshold=match_threshold,
    )

    results: list[OpportunityResult] = []

    for group in product_groups:
        representative = group.representative

        selling_price = round(
            representative.price
            * selling_price_multiplier,
            2,
        )

        analysis = calculate_product_opportunity(
            product=representative,
            selling_price=selling_price,
            shipping_cost=shipping_cost,
            marketplace_fee_rate=marketplace_fee_rate,
            estimated_monthly_sales=estimated_monthly_sales,
            competitor_count=competitor_count,
            risk_level=risk_level,
        )

        results.append(
            OpportunityResult(
                product=representative,
                analysis=analysis,
                matched_product_count=len(
                    group.products
                ),
            )
        )

    results.sort(
        key=lambda result: (
            result.analysis["opportunity_score"],
            result.analysis["net_profit"],
        ),
        reverse=True,
    )

    return results