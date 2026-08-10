from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier
from types import SimpleNamespace

from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from app.application.discovery.production_execution import (
    ProductionDiscoveryRuntimeResult,
)
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from engine import orchestrator
from marketplaces import ebay


OBSERVED_AT = datetime(2026, 8, 5, 2, 30, tzinfo=timezone.utc)
TEST_COLLECTOR = CollectorDescriptor("ebay", "test-collector-implementation")


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
        collector_descriptor=TEST_COLLECTOR,
        source_reference=product.url,
    )

    assert fact.product is product
    assert fact.observed_at is OBSERVED_AT
    assert fact.collector_name == "ebay"
    assert fact.source_reference == "https://www.ebay.com/itm/123456789"
    assert set(fact.__dataclass_fields__) == {
        "product",
        "observed_at",
        "collector_descriptor",
        "source_reference",
        "candidate_market_identity",
        "candidate_handoff_policy_name",
        "candidate_handoff_policy_version",
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


def test_production_runtime_returns_execution_results_and_ordered_facts() -> None:
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
        for suffix in ("first", "second"):
            sink(
                CollectionFact(
                    product=product,
                    observed_at=OBSERVED_AT,
                    collector_descriptor=TEST_COLLECTOR,
                    source_reference=f"{product.url}#{suffix}",
                )
            )
        return [opportunity]

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)

    result = runtime.execute(_command())

    assert isinstance(result, ProductionDiscoveryRuntimeResult)
    assert result.discovery_execution_id == "execution-1"
    assert len(result.discovery_results) == 1
    assert tuple(fact.source_reference for fact in result.collection_facts) == (
        "https://www.ebay.com/itm/123456789#first",
        "https://www.ebay.com/itm/123456789#second",
    )


def test_production_runtime_isolates_consecutive_execution_fact_tuples() -> None:
    calls = 0

    def finder(**kwargs):
        nonlocal calls
        calls += 1
        product = ebay.ebay_item_to_product(raw_item(item_id=f"item-{calls}"))
        kwargs["collection_fact_sink"](
            CollectionFact(
                product=product,
                observed_at=OBSERVED_AT,
                collector_descriptor=TEST_COLLECTOR,
                source_reference=f"run-{calls}",
            )
        )
        return []

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)
    first = runtime.execute(_command())
    second = runtime.execute(_command())

    assert first.discovery_results == ()
    assert second.discovery_results == ()
    assert tuple(fact.source_reference for fact in first.collection_facts) == (
        "run-1",
    )
    assert tuple(fact.source_reference for fact in second.collection_facts) == (
        "run-2",
    )
    assert first.collection_facts is not second.collection_facts


def test_production_runtime_isolates_concurrent_execution_fact_buffers() -> None:
    barrier = Barrier(2)

    def finder(**kwargs):
        barrier.wait()
        product = ebay.ebay_item_to_product(
            raw_item(item_id=kwargs["query"], source_url=kwargs["query"])
        )
        kwargs["collection_fact_sink"](
            CollectionFact(
                product=product,
                observed_at=OBSERVED_AT,
                collector_descriptor=TEST_COLLECTOR,
                source_reference=kwargs["query"],
            )
        )
        return []

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)
    first_command = replace(
        _command(),
        discovery_execution_id="execution-1",
        parameters=replace(_command().parameters, query="first"),
    )
    second_command = replace(
        _command(),
        command_id="command-2",
        discovery_execution_id="execution-2",
        parameters=replace(_command().parameters, query="second"),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(runtime.execute, first_command)
        second_future = pool.submit(runtime.execute, second_command)
        first = first_future.result()
        second = second_future.result()

    assert first.discovery_execution_id == "execution-1"
    assert second.discovery_execution_id == "execution-2"
    assert tuple(fact.source_reference for fact in first.collection_facts) == (
        "first",
    )
    assert tuple(fact.source_reference for fact in second.collection_facts) == (
        "second",
    )


def _command():
    from tests.test_persisted_discovery_execution_entry import command

    return command()
