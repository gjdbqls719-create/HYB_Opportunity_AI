from decimal import Decimal

import pytest

from app.models import Product
from engine import orchestrator
from services.currency import (
    CurrencyConverter,
    MockExchangeRateProvider,
    normalize_product_currency,
    normalize_products_currency,
)


def _make_product(
    *,
    marketplace: str,
    item_id: str,
    price: float,
    currency: str,
    shipping_cost: float = 0,
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title="Apple iPhone Test Product",
        price=price,
        currency=currency,
        shipping_cost=shipping_cost,
        condition="new",
        url=f"https://example.com/{item_id}",
    )


def test_normalize_product_currency_converts_price_and_shipping() -> None:
    provider = MockExchangeRateProvider(
        {
            ("USD", "KRW"): "1400",
        }
    )
    converter = CurrencyConverter(
        provider,
        quantum=Decimal("0.01"),
    )

    product = _make_product(
        marketplace="ebay",
        item_id="usd-1",
        price=10,
        currency="USD",
        shipping_cost=2,
    )

    normalized = normalize_product_currency(
        product,
        converter=converter,
        target_currency="KRW",
    )

    assert normalized is not product
    assert normalized.currency == "KRW"
    assert normalized.price == 14000.0
    assert normalized.shipping_cost == 2800.0

    assert normalized.marketplace == product.marketplace
    assert normalized.item_id == product.item_id
    assert normalized.title == product.title
    assert normalized.url == product.url

    assert product.currency == "USD"
    assert product.price == 10.0
    assert product.shipping_cost == 2.0


def test_normalize_product_currency_returns_same_product_for_same_currency() -> None:
    provider = MockExchangeRateProvider()
    converter = CurrencyConverter(provider)

    product = _make_product(
        marketplace="ebay",
        item_id="krw-1",
        price=15000,
        currency="KRW",
        shipping_cost=3000,
    )

    normalized = normalize_product_currency(
        product,
        converter=converter,
        target_currency="KRW",
    )

    assert normalized is product


def test_normalize_products_currency_uses_one_target_currency() -> None:
    provider = MockExchangeRateProvider(
        {
            ("USD", "KRW"): "1400",
        }
    )
    converter = CurrencyConverter(provider)

    products = [
        _make_product(
            marketplace="ebay",
            item_id="usd-1",
            price=10,
            currency="USD",
        ),
        _make_product(
            marketplace="amazon",
            item_id="krw-1",
            price=20000,
            currency="KRW",
        ),
    ]

    normalized = normalize_products_currency(
        products,
        converter=converter,
        target_currency="KRW",
    )

    assert len(normalized) == 2
    assert {
        product.currency
        for product in normalized
    } == {"KRW"}

    assert normalized[0].price == 14000.0
    assert normalized[1].price == 20000.0


def test_find_best_opportunities_normalizes_before_price_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [
        _make_product(
            marketplace="ebay",
            item_id="usd-1",
            price=10,
            currency="USD",
        ),
        _make_product(
            marketplace="amazon",
            item_id="krw-1",
            price=20000,
            currency="KRW",
        ),
    ]

    def fake_search_products(
        query: str,
        limit: int = 10,
        *,
        error_handler=None,
    ) -> list[Product]:
        return products

    monkeypatch.setattr(
        orchestrator,
        "search_products",
        fake_search_products,
    )

    provider = MockExchangeRateProvider(
        {
            ("USD", "KRW"): "1400",
        }
    )
    converter = CurrencyConverter(provider)

    results = orchestrator.find_best_opportunities(
        "iphone",
        currency_converter=converter,
        target_currency="KRW",
    )

    assert len(results) == 1

    result = results[0]

    assert result.product.currency == "KRW"
    assert result.product.price == 14000.0

    assert (
        result.price_intelligence.currency
        == "KRW"
    )
    assert (
        result.price_intelligence.lowest_price
        == Decimal("14000.00")
    )
    assert (
        result.price_intelligence.highest_price
        == Decimal("20000.00")
    )
    assert (
        result.price_intelligence
        .recommended_selling_price
        == Decimal("17000.00")
    )

    assert (
        result.analysis["analysis_currency"]
        == "KRW"
    )
    assert (
        result.analysis["currency_normalized"]
        is True
    )


def test_find_best_opportunities_requires_converter_for_target_currency() -> None:
    with pytest.raises(
        ValueError,
        match="currency_converter",
    ):
        orchestrator.find_best_opportunities(
            "iphone",
            target_currency="KRW",
        )