from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import Product
from engine.price_intelligence import (
    analyze_product_prices,
)


def make_product(
    item_id: str,
    price: Decimal | int | float | str,
    currency: str = "USD",
) -> Product:
    return Product(
        marketplace="test",
        item_id=item_id,
        title="Test Product",
        price=price,
        currency=currency,
        condition="New",
        url=f"https://example.com/{item_id}",
    )


def test_analyze_multiple_product_prices() -> None:
    products = [
        make_product("1", Decimal("80.00")),
        make_product("2", Decimal("95.00")),
        make_product("3", Decimal("100.00")),
    ]

    result = analyze_product_prices(products)

    assert result.currency == "USD"

    assert result.lowest_price == Decimal("80.00")
    assert result.average_price == Decimal("91.67")
    assert result.median_price == Decimal("95.00")
    assert result.highest_price == Decimal("100.00")
    assert (
        result.recommended_selling_price
        == Decimal("95.00")
    )

    assert isinstance(result.lowest_price, Decimal)
    assert isinstance(result.average_price, Decimal)
    assert isinstance(result.median_price, Decimal)
    assert isinstance(result.highest_price, Decimal)
    assert isinstance(
        result.recommended_selling_price,
        Decimal,
    )

    assert result.sample_size == 3


def test_single_product_uses_fallback_multiplier() -> None:
    products = [
        make_product("1", Decimal("100.00")),
    ]

    result = analyze_product_prices(
        products,
        fallback_multiplier=Decimal("1.50"),
    )

    assert result.lowest_price == Decimal("100.00")
    assert (
        result.recommended_selling_price
        == Decimal("150.00")
    )
    assert isinstance(
        result.recommended_selling_price,
        Decimal,
    )
    assert result.sample_size == 1


def test_accepts_float_fallback_multiplier_safely() -> None:
    products = [
        make_product("1", Decimal("19.99")),
    ]

    result = analyze_product_prices(
        products,
        fallback_multiplier=1.5,
    )

    assert (
        result.recommended_selling_price
        == Decimal("29.99")
    )


def test_rejects_empty_product_list() -> None:
    with pytest.raises(
        ValueError,
        match="가격을 분석할 상품이 하나 이상 필요합니다.",
    ):
        analyze_product_prices([])


def test_rejects_mixed_currencies() -> None:
    products = [
        make_product("1", Decimal("100.00"), "USD"),
        make_product("2", Decimal("130000.00"), "KRW"),
    ]

    with pytest.raises(
        ValueError,
        match=(
            "서로 다른 통화의 상품 가격은 "
            "함께 분석할 수 없습니다."
        ),
    ):
        analyze_product_prices(products)


@pytest.mark.parametrize(
    "fallback_multiplier",
    [
        Decimal("0"),
        Decimal("-1"),
        0,
        -1.5,
    ],
)
def test_rejects_invalid_fallback_multiplier(
    fallback_multiplier: Decimal | int | float,
) -> None:
    products = [
        make_product("1", Decimal("100.00")),
    ]

    with pytest.raises(
        ValueError,
        match="fallback_multiplier는 0보다 커야 합니다.",
    ):
        analyze_product_prices(
            products,
            fallback_multiplier=fallback_multiplier,
        )


