from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.models import Product
from collectors.base import MarketplaceAdapter
from marketplaces.amazon import AmazonAdapter
from marketplaces.ebay import EbayAdapter


@dataclass(frozen=True)
class AdapterContractCase:
    """Marketplace Adapter 공통 계약 검증에 필요한 테스트 사례."""

    adapter_type: type[MarketplaceAdapter]
    raw_product: dict[str, Any]
    expected_marketplace: str
    expected_item_id: str
    expected_title: str
    expected_price: float
    expected_currency: str
    expected_condition: str
    expected_url: str


ADAPTER_CONTRACT_CASES = (
    AdapterContractCase(
        adapter_type=AmazonAdapter,
        raw_product={
            "asin": "AMZ-CONTRACT-001",
            "title": "Amazon Contract Product",
            "price": "89.99",
            "currency": "usd",
            "condition": "New",
            "url": "https://www.amazon.com/dp/AMZ-CONTRACT-001",
        },
        expected_marketplace="amazon",
        expected_item_id="AMZ-CONTRACT-001",
        expected_title="Amazon Contract Product",
        expected_price=89.99,
        expected_currency="USD",
        expected_condition="New",
        expected_url="https://www.amazon.com/dp/AMZ-CONTRACT-001",
    ),
    AdapterContractCase(
        adapter_type=EbayAdapter,
        raw_product={
            "itemId": "EBAY-CONTRACT-001",
            "title": "eBay Contract Product",
            "price": {
                "value": "79.50",
                "currency": "usd",
            },
            "condition": "New",
            "itemWebUrl": "https://www.ebay.com/itm/EBAY-CONTRACT-001",
        },
        expected_marketplace="ebay",
        expected_item_id="EBAY-CONTRACT-001",
        expected_title="eBay Contract Product",
        expected_price=79.50,
        expected_currency="USD",
        expected_condition="New",
        expected_url="https://www.ebay.com/itm/EBAY-CONTRACT-001",
    ),
)


@pytest.fixture(params=ADAPTER_CONTRACT_CASES, ids=lambda case: case.expected_marketplace)
def contract_case(request: pytest.FixtureRequest) -> AdapterContractCase:
    return request.param


def test_adapter_implements_marketplace_adapter_contract(
    contract_case: AdapterContractCase,
) -> None:
    adapter = contract_case.adapter_type()

    assert isinstance(adapter, MarketplaceAdapter)
    assert adapter.marketplace_name == contract_case.expected_marketplace


def test_normalize_returns_valid_common_product(
    contract_case: AdapterContractCase,
) -> None:
    adapter = contract_case.adapter_type()

    product = adapter.normalize(contract_case.raw_product)

    assert isinstance(product, Product)
    assert product.marketplace == contract_case.expected_marketplace
    assert product.item_id == contract_case.expected_item_id
    assert product.title == contract_case.expected_title
    assert product.price == contract_case.expected_price
    assert product.currency == contract_case.expected_currency
    assert product.condition == contract_case.expected_condition
    assert product.url == contract_case.expected_url


def test_normalize_preserves_required_product_invariants(
    contract_case: AdapterContractCase,
) -> None:
    adapter = contract_case.adapter_type()

    product = adapter.normalize(contract_case.raw_product)

    assert product.marketplace.strip()
    assert product.title.strip()
    assert product.currency.strip()
    assert product.price >= 0


def test_normalize_does_not_mutate_raw_product(
    contract_case: AdapterContractCase,
) -> None:
    adapter = contract_case.adapter_type()
    original = _deep_copy_mapping(contract_case.raw_product)

    adapter.normalize(contract_case.raw_product)

    assert contract_case.raw_product == original


def _deep_copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """중첩 dict만 사용하는 원본 상품 Fixture를 안전하게 복사한다."""

    copied: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, dict):
            copied[key] = _deep_copy_mapping(item)
        else:
            copied[key] = item

    return copied
