from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.discovery import (
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
)
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from app.models import Product
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from engine import orchestrator
from services.currency import CurrencyConverter, MockExchangeRateProvider
from tests.test_persisted_discovery_execution_entry import (
    RecordingObservationIdentityProvider,
    RecordingObservationRepository,
    RecordingPersister,
    RecordingRuntime,
    command,
)


OBSERVED_AT = datetime(2026, 8, 6, 1, 0, tzinfo=timezone.utc)
DESCRIPTOR = CollectorDescriptor("ebay", "test-collector-implementation")


def product(
    item_id: str,
    title: str,
    price: float,
    currency: str = "USD",
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=title,
        price=price,
        currency=currency,
        condition="new",
        url=f"https://example.com/{item_id}",
    )


def fact(value: Product) -> CollectionFact:
    return CollectionFact(value, OBSERVED_AT, DESCRIPTOR, value.url)


def test_grouping_correlation_is_an_exact_immutable_position_contract() -> None:
    correlation = GroupingCorrelation((2, 0), 0)

    assert correlation.ordered_member_collection_positions == (2, 0)
    assert correlation.representative_collection_position == 0
    assert set(correlation.__dataclass_fields__) == {
        "ordered_member_collection_positions",
        "representative_collection_position",
    }
    with pytest.raises(FrozenInstanceError):
        correlation.representative_collection_position = 2


def test_engine_emits_ordered_membership_and_representative_positions() -> None:
    products = [
        product("iphone-high", "Apple iPhone 15 Pro 256GB", 900),
        product("buds", "Samsung Galaxy Buds Pro", 120),
        product("iphone-low", "Apple iPhone 15 Pro 256GB", 700),
    ]
    correlations: list[tuple[tuple[int, ...], int]] = []

    groups = orchestrator.group_similar_products(
        products,
        grouping_correlation_sink=lambda members, representative: correlations.append(
            (members, representative)
        ),
    )

    assert [tuple(group.products) for group in groups] == [
        (products[0], products[2]),
        (products[1],),
    ]
    assert correlations == [((0, 2), 2), ((1,), 1)]


def test_engine_preserves_collection_positions_after_currency_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [
        product("usd-high", "Apple iPhone 15 Pro 256GB", 20, "USD"),
        product("krw-middle", "Apple iPhone 15 Pro 256GB", 20_000, "KRW"),
        product("usd-low", "Apple iPhone 15 Pro 256GB", 10, "USD"),
    ]
    emitted_facts: list[CollectionFact] = []

    def search_products(
        query,
        limit=10,
        *,
        error_handler=None,
        collection_fact_sink=None,
    ):
        assert collection_fact_sink is not None
        for value in products:
            emitted = fact(value)
            collection_fact_sink(emitted)
            emitted_facts.append(emitted)
        return products

    monkeypatch.setattr(orchestrator, "search_products", search_products)
    converter = CurrencyConverter(
        MockExchangeRateProvider({("USD", "KRW"): "1400"}),
        quantum=Decimal("0.01"),
    )
    correlations: list[tuple[tuple[int, ...], int]] = []

    results = orchestrator.find_best_opportunities(
        "iphone",
        currency_converter=converter,
        target_currency="KRW",
        collection_fact_sink=lambda value: None,
        grouping_correlation_sink=lambda members, representative: correlations.append(
            (members, representative)
        ),
    )

    assert len(emitted_facts) == 3
    assert correlations == [((0, 1, 2), 2)]
    assert results[0].product.item_id == "usd-low"
    assert results[0].product.currency == "KRW"


def test_production_runtime_wraps_engine_positions_in_immutable_correlations() -> None:
    collected_product = product("first", "Camera", 100)

    def finder(**kwargs):
        kwargs["collection_fact_sink"](fact(collected_product))
        kwargs["grouping_correlation_sink"]((0,), 0)
        return []

    result = OrchestratorProductionDiscoveryRuntime(finder=finder).execute(command())

    assert result.discovery_results == ()
    assert result.collection_facts == (fact(collected_product),)
    assert result.grouping_correlations == (GroupingCorrelation((0,), 0),)


def test_runtime_and_application_return_the_same_grouping_correlations() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    products = (
        product("first", "Apple iPhone 15 Pro", 900),
        product("second", "Apple iPhone 15 Pro", 700),
    )
    runtime.collection_facts = tuple(fact(value) for value in products)
    correlations = (GroupingCorrelation((0, 1), 1),)
    runtime.grouping_correlations = correlations

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-1", "observation-2"
        ),
        observation_repository=RecordingObservationRepository(),
    ).execute(command())

    assert result.grouping_correlations is correlations
    assert result.discovery_results is runtime.results
    assert result.collection_facts is runtime.collection_facts
    assert tuple(value.source_item_id for value in result.observations) == (
        "first",
        "second",
    )


def test_replay_keeps_committed_command_and_grouping_correlation_semantics() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.grouping_correlations = (GroupingCorrelation((0,), 0),)
    runtime.collection_facts = (fact(product("first", "Camera", 100)),)

    class ReplayPersister(RecordingPersister):
        def execute(self, value):
            from tests.test_persisted_discovery_execution_entry import persist_result

            self.events.append("persist")
            return persist_result(command(), replayed=True)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=ReplayPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-1"
        ),
        observation_repository=RecordingObservationRepository(),
    ).execute(command())

    assert runtime.calls == [command()]
    assert result.command_result.replayed is True
    assert result.grouping_correlations is runtime.grouping_correlations
