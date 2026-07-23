from __future__ import annotations

from collections.abc import Iterable

from app.models import Product
from services.currency.converter import CurrencyConverter
from services.currency.models import normalize_currency_code


def normalize_product_currency(
    product: Product,
    *,
    converter: CurrencyConverter,
    target_currency: str,
) -> Product:
    """Product 가격과 상품 자체 배송비를 기준 통화로 변환한다."""
    target = normalize_currency_code(target_currency, "대상 통화")
    source = normalize_currency_code(product.currency, "상품 통화")

    if source == target:
        return product

    converted_price = converter.convert(product.price, source, target)
    converted_shipping_cost = converter.convert(
        product.shipping_cost,
        source,
        target,
    )

    return Product(
        marketplace=product.marketplace,
        item_id=product.item_id,
        title=product.title,
        price=float(converted_price),
        currency=target,
        condition=product.condition,
        url=product.url,
        brand=product.brand,
        model_number=product.model_number,
        category=product.category,
        shipping_cost=float(converted_shipping_cost),
        seller=product.seller,
        image_url=product.image_url,
        rating=product.rating,
        review_count=product.review_count,
        in_stock=product.in_stock,
    )


def normalize_products_currency(
    products: Iterable[Product],
    *,
    converter: CurrencyConverter,
    target_currency: str,
) -> list[Product]:
    """여러 Product를 동일한 기준 통화로 변환한다."""
    target = normalize_currency_code(target_currency, "대상 통화")
    return [
        normalize_product_currency(
            product,
            converter=converter,
            target_currency=target,
        )
        for product in products
    ]
