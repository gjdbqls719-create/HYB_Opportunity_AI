from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from collectors.collection_fact import CollectionFact
from engine import orchestrator
from marketplaces import ebay


OBSERVED_AT = datetime(2026, 8, 5, 2, 30, tzinfo=timezone.utc)


def raw_item(
    *,
    item_id: str = "v1|123456789|0",
    source_url: str = "https://www.ebay.com/itm/123456789",
) -> dict[str, object]:
    return {
        "itemId": item_id,
        "title": "Apple iPhone 15 Pro 256GB Black",
        "price": {"value": "999.99", "currency": "USD"},
        "condition": "New",
        "itemWebUrl": source_url,
    }


def test_collection_fact_preserves_only_collection_boundary_facts() -> None:
    product = ebay.ebay_item_to_product(raw_item())

    fact = CollectionFact(
        product=product,
        observed_at=OBSERVED_AT,
        collector_name="ebay",
        source_reference=product.url,
    )

    assert fact.product is product
    assert fact.observed_at is OBSERVED_AT
    assert fact.collector_name == "ebay"
    assert fact.source_reference == "https://www.ebay.com/itm/123456789"
    assert set(fact.__dataclass_fields__) == {
        "product",
        "observed_at",
        "collector_name",
        "source_reference",
    }


def test_ebay_emits_one_fact_when_each_raw_item_becomes_a_product(
    monkeypatch,
) -> None:
    raw_items = [
        raw_item(),
        raw_item(
            item_id="v1|987654321|0",
            source_url="https://www.ebay.com/itm/987654321",
        ),
    ]
    facts: list[CollectionFact] = []
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: raw_items)

    products = ebay.search_products(
        query="iphone",
        limit=2,
        collection_fact_sink=facts.append,
        observed_at=lambda: OBSERVED_AT,
    )

    assert [fact.product for fact in facts] == products
    assert [fact.observed_at for fact in facts] == [OBSERVED_AT, OBSERVED_AT]
    assert [fact.collector_name for fact in facts] == ["ebay", "ebay"]
    assert [fact.source_reference for fact in facts] == [
        "https://www.ebay.com/itm/123456789",
        "https://www.ebay.com/itm/987654321",
    ]


def test_ebay_fact_sink_is_optional(monkeypatch) -> None:
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: [raw_item()])

    products = ebay.search_products(query="iphone", limit=1)

    assert len(products) == 1


def test_orchestrator_passes_collection_fact_sink_to_ebay(monkeypatch) -> None:
    facts: list[CollectionFact] = []
    received: dict[str, object] = {}

    def search_ebay_products(**kwargs):
        received.update(kwargs)
        return []

    monkeypatch.setattr(
        orchestrator,
        "search_ebay_products",
        search_ebay_products,
    )

    assert orchestrator.search_products(
        "iphone",
        collection_fact_sink=facts.append,
    ) == []
    assert received == {
        "query": "iphone",
        "limit": 10,
        "collection_fact_sink": facts.append,
    }


def test_production_runtime_buffers_facts_emitted_by_finder() -> None:
    opportunity = SimpleNamespace(
        product=SimpleNamespace(),
        final_opportunity_score=77.0,
        matched_product_count=1,
        ai_recommendation=None,
        analysis={},
        confidence=None,
    )

    def finder(**kwargs):
        sink = kwargs["collection_fact_sink"]
        product = ebay.ebay_item_to_product(raw_item())
        sink(
            CollectionFact(
                product=product,
                observed_at=OBSERVED_AT,
                collector_name="ebay",
                source_reference=product.url,
            )
        )
        return [opportunity]

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)

    runtime.execute(_command())

    assert len(runtime.collection_facts) == 1
    assert runtime.collection_facts[0].product.item_id == "v1|123456789|0"


def _command():
    from tests.test_persisted_discovery_execution_entry import command

    return command()
