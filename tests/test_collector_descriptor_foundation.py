from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from collectors.descriptor import CollectorDescriptor
from marketplaces import ebay
from tests.test_persisted_discovery_execution_entry import command


OBSERVED_AT = datetime(2026, 8, 6, 1, 0, tzinfo=timezone.utc)


def raw_item(item_id: str, source_reference: str) -> dict[str, object]:
    return {
        "itemId": item_id,
        "title": f"Product {item_id}",
        "price": {"value": "10.00", "currency": "USD"},
        "condition": "New",
        "itemWebUrl": source_reference,
    }


def test_ebay_declares_authoritative_collector_implementation_descriptor() -> None:
    descriptor = ebay.EbayAdapter.collector_descriptor

    assert descriptor == CollectorDescriptor(
        collector_name="ebay",
        collector_version="ebay-collector-implementation-v1",
    )
    assert descriptor.collector_name == ebay.EbayAdapter.marketplace_name
    with pytest.raises(FrozenInstanceError):
        descriptor.collector_version = "changed"


@pytest.mark.parametrize("field", ("collector_name", "collector_version"))
def test_collector_descriptor_rejects_empty_metadata(field: str) -> None:
    values = {
        "collector_name": "ebay",
        "collector_version": "ebay-collector-implementation-v1",
    }
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        CollectorDescriptor(**values)


def test_collector_descriptor_has_no_version_default() -> None:
    with pytest.raises(TypeError):
        CollectorDescriptor(collector_name="ebay")


def test_ebay_emits_descriptor_and_source_reference_for_each_raw_item(
    monkeypatch,
) -> None:
    raw_items = (
        raw_item("item-1", "https://www.ebay.com/itm/1"),
        raw_item("item-2", "https://www.ebay.com/itm/2"),
    )
    facts = []
    monkeypatch.setattr(ebay, "search_items", lambda **kwargs: list(raw_items))

    products = ebay.search_products(
        "product",
        limit=2,
        collection_fact_sink=facts.append,
        observed_at=lambda: OBSERVED_AT,
    )

    assert [fact.product for fact in facts] == products
    assert [fact.collector_descriptor for fact in facts] == [
        ebay.EbayAdapter.collector_descriptor,
        ebay.EbayAdapter.collector_descriptor,
    ]
    assert [fact.source_reference for fact in facts] == [
        "https://www.ebay.com/itm/1",
        "https://www.ebay.com/itm/2",
    ]


def test_ebay_callback_remains_optional(monkeypatch) -> None:
    monkeypatch.setattr(
        ebay,
        "search_items",
        lambda **kwargs: [raw_item("item-1", "https://www.ebay.com/itm/1")],
    )

    assert len(ebay.search_products("product", limit=1)) == 1


def test_runtime_correlation_preserves_collector_descriptor() -> None:
    def finder(**kwargs):
        ebay.ebay_item_to_product(
            raw_item("item-1", "https://www.ebay.com/itm/1"),
            collection_fact_sink=kwargs["collection_fact_sink"],
            observed_at=lambda: OBSERVED_AT,
        )
        return []

    result = OrchestratorProductionDiscoveryRuntime(finder=finder).execute(command())

    assert result.discovery_execution_id == command().discovery_execution_id
    assert result.discovery_results == ()
    assert len(result.collection_facts) == 1
    assert (
        result.collection_facts[0].collector_descriptor
        is ebay.EbayAdapter.collector_descriptor
    )
