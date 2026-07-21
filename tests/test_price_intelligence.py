import pytest

from app.models import Product
from engine.price_intelligence import (
    analyze_product_prices,
)


def make_product(
    item_id: str,
    price: float,
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
        make_product("1", 80.00),
        make_product("2", 95.00),
        make_product("3", 100.00),
    ]

    result = analyze_product_prices(products)

    assert result.currency == "USD"
    assert result.lowest_price == 80.00
    assert result.average_price == 91.67
    assert result.median_price == 95.00
    assert result.highest_price == 100.00
    assert result.recommended_selling_price == 95.00
    assert result.sample_size == 3


def test_single_product_uses_fallback_multiplier() -> None:
    products = [
        make_product("1", 100.00),
    ]

    result = analyze_product_prices(
        products,
        fallback_multiplier=1.5,
    )

    assert result.lowest_price == 100.00
    assert result.recommended_selling_price == 150.00
    assert result.sample_size == 1


def test_rejects_empty_product_list() -> None:
    with pytest.raises(ValueError):
        analyze_product_prices([])


def test_rejects_mixed_currencies() -> None:
    products = [
        make_product("1", 100.00, "USD"),
        make_product("2", 130000.00, "KRW"),
    ]

    with pytest.raises(ValueError):
        analyze_product_prices(products)


def test_rejects_invalid_fallback_multiplier() -> None:
    products = [
        make_product("1", 100.00),
    ]

    with pytest.raises(ValueError):
        analyze_product_prices(
            products,
            fallback_multiplier=0,
        )