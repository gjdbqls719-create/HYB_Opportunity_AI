from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import Product, ProductDataSource
from collectors.base import MarketplaceAdapter
from marketplaces import ebay
from marketplaces.ebay import EbayAdapter, ebay_item_to_product
from engine.opportunity import calculate_product_opportunity


def make_raw_item() -> dict[str, object]:
    return {
        "itemId": "v1|123456789|0",
        "title": "Apple iPhone 15 Pro 256GB Black",
        "price": {
            "value": "999.99",
            "currency": "USD",
        },
        "condition": "New",
        "itemWebUrl": "https://www.ebay.com/itm/123456789",
    }


def test_ebay_adapter_implements_marketplace_contract() -> None:
    adapter = EbayAdapter()

    assert isinstance(adapter, MarketplaceAdapter)
    assert adapter.marketplace_name == "ebay"


def test_ebay_adapter_normalizes_product() -> None:
    product = EbayAdapter().normalize(make_raw_item())

    assert isinstance(product, Product)
    assert product.marketplace == "ebay"
    assert product.item_id == "v1|123456789|0"
    assert product.title == "Apple iPhone 15 Pro 256GB Black"
    assert product.price == 999.99
    assert product.currency == "USD"
    assert product.condition == "New"
    assert product.url == "https://www.ebay.com/itm/123456789"
    assert product.data_source is ProductDataSource.PRODUCTION


def test_missing_ebay_shipping_remains_unknown_downstream() -> None:
    product = EbayAdapter().normalize(make_raw_item())

    result = calculate_product_opportunity(product, selling_price=1200)

    assert product.shipping_cost_known is False
    assert result["shipping_cost_known"] is False
    assert result["shipping_cost_source"] == "unknown"
    assert result["is_free_shipping"] is False


@pytest.mark.parametrize(
    "raw_price",
    [None, "", "not-a-price", {"unexpected": "value"}],
)
def test_ebay_adapter_rejects_invalid_price(raw_price: object) -> None:
    raw_item = make_raw_item()
    raw_item["price"] = {
        "value": raw_price,
        "currency": "USD",
    }

    with pytest.raises((TypeError, ValueError)):
        EbayAdapter().normalize(raw_item)


def test_legacy_conversion_function_uses_adapter_behavior() -> None:
    product = ebay_item_to_product(make_raw_item())

    assert product == EbayAdapter().normalize(make_raw_item())


def test_search_products_normalizes_all_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_items = [
        make_raw_item(),
        {
            **make_raw_item(),
            "itemId": "v1|987654321|0",
            "title": "Apple iPhone 15 Pro 512GB Black",
        },
    ]
    received: dict[str, object] = {}

    def fake_search_items(
        query: str,
        limit: int,
        marketplace_id: str,
    ) -> list[dict[str, object]]:
        received.update(
            query=query,
            limit=limit,
            marketplace_id=marketplace_id,
        )
        return raw_items

    monkeypatch.setattr(ebay, "search_items", fake_search_items)

    products = ebay.search_products(
        query="iphone",
        limit=2,
        marketplace_id="EBAY_US",
    )

    assert received == {
        "query": "iphone",
        "limit": 2,
        "marketplace_id": "EBAY_US",
    }
    assert [product.item_id for product in products] == [
        "v1|123456789|0",
        "v1|987654321|0",
    ]
    assert all(product.marketplace == "ebay" for product in products)


def test_ebay_us_collection_fact_exposes_exact_candidate_handoff_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 8, 10, 1, 2, 3, tzinfo=timezone.utc)
    facts = []
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: [make_raw_item()])

    ebay.search_products(
        query="iphone",
        limit=1,
        marketplace_id="EBAY_US",
        collection_fact_sink=facts.append,
        observed_at=lambda: observed_at,
    )

    assert len(facts) == 1
    fact = facts[0]
    identity = fact.candidate_market_identity
    assert identity is not None
    assert identity.scope.value == "listing"
    assert identity.market == "US"
    assert identity.marketplace == "ebay"
    assert identity.marketplace_item_id == "v1|123456789|0"
    assert identity.condition == "New"
    assert identity.window_started_at == identity.window_ended_at == observed_at
    assert identity.canonical_product_id is None
    assert identity.normalized_query is None
    assert identity.category is None
    assert identity.variant_identity is None
    assert fact.candidate_handoff_policy_name == "discovery-candidate-handoff"
    assert fact.candidate_handoff_policy_version == "1.0.0"


def test_non_us_ebay_collection_fact_has_no_candidate_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = []
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: [make_raw_item()])
    ebay.search_products(
        query="iphone",
        marketplace_id="EBAY_GB",
        collection_fact_sink=facts.append,
    )
    assert facts[0].candidate_market_identity is None
    assert facts[0].candidate_handoff_policy_name is None
    assert facts[0].candidate_handoff_policy_version is None


def test_ebay_us_missing_condition_is_none_in_candidate_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = make_raw_item()
    del raw["condition"]
    facts = []
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: [raw])
    ebay.search_products(
        query="iphone",
        marketplace_id="EBAY_US",
        collection_fact_sink=facts.append,
    )
    assert facts[0].candidate_market_identity.condition is None


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: object,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self) -> object:
        return self._payload


def test_get_item_by_id_calls_exact_browse_item_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}

    class FakeSettings:
        ebay_browse_api_url = "https://api.ebay.test/buy/browse/v1"

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        received.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse(status_code=200, payload=make_raw_item())

    monkeypatch.setattr(ebay, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        ebay,
        "get_application_token",
        lambda: {"access_token": "test-token"},
    )
    monkeypatch.setattr(ebay.requests, "get", fake_get)

    result = ebay.get_item_by_id(
        " v1|123456789|0 ",
        marketplace_id="EBAY_US",
    )

    assert result == make_raw_item()
    assert received == {
        "url": (
            "https://api.ebay.test/buy/browse/v1/item/"
            "v1%7C123456789%7C0"
        ),
        "headers": {
            "Authorization": "Bearer test-token",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Accept": "application/json",
        },
        "timeout": 30,
    }


def test_get_item_by_id_returns_none_for_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSettings:
        ebay_browse_api_url = "https://api.ebay.test/buy/browse/v1"

    monkeypatch.setattr(ebay, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        ebay,
        "get_application_token",
        lambda: {"access_token": "test-token"},
    )
    monkeypatch.setattr(
        ebay.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            status_code=404,
            payload={},
            text="not found",
        ),
    )

    assert ebay.get_item_by_id("missing-item") is None


def test_get_item_by_id_raises_for_non_404_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSettings:
        ebay_browse_api_url = "https://api.ebay.test/buy/browse/v1"

    monkeypatch.setattr(ebay, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        ebay,
        "get_application_token",
        lambda: {"access_token": "test-token"},
    )
    monkeypatch.setattr(
        ebay.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            status_code=500,
            payload={},
            text="server error",
        ),
    )

    with pytest.raises(RuntimeError, match="eBay 단일 상품 조회 실패"):
        ebay.get_item_by_id("v1|123456789|0")


@pytest.mark.parametrize("item_id", ["", "   "])
def test_get_item_by_id_rejects_empty_item_id(item_id: str) -> None:
    with pytest.raises(ValueError, match="상품 ID"):
        ebay.get_item_by_id(item_id)


def test_get_product_by_id_normalizes_exact_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ebay,
        "get_item_by_id",
        lambda item_id, marketplace_id: make_raw_item(),
    )

    product = ebay.get_product_by_id("v1|123456789|0")

    assert isinstance(product, Product)
    assert product.item_id == "v1|123456789|0"
    assert product.marketplace == "ebay"


def test_get_product_by_id_preserves_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ebay,
        "get_item_by_id",
        lambda item_id, marketplace_id: None,
    )

    assert ebay.get_product_by_id("missing-item") is None
