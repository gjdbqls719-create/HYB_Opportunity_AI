from __future__ import annotations

from dataclasses import replace

import pytest

from app.application.discovery import PersistedDiscoveryExecutionEntry
from app.application.discovery.production_execution import (
    DiscoveryRuntimeCorrelationError,
)
from app.domain.discovery_identity import MalformedCollectorObservationError
from app.domain.product_observation import ObservedProductSnapshot
from app.models import Product, ProductDataSource
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from tests.test_persisted_discovery_execution_entry import (
    NOW,
    RecordingObservationRepository,
    RecordingPersister,
    RecordingRuntime,
    command,
    persist_result,
)


DESCRIPTOR = CollectorDescriptor(
    "ebay",
    "ebay-collector-implementation-v1",
)


class SequentialObservationIdentityProvider:
    def __init__(self, *observation_ids: str) -> None:
        self._observation_ids = iter(observation_ids)
        self.calls = 0

    def provide_observation_id(self) -> str:
        self.calls += 1
        return next(self._observation_ids)


def product(item_id: str, price: float) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=f"Observed {item_id}",
        price=price,
        currency="USD",
        condition="new",
        url=f"https://www.ebay.com/itm/{item_id}",
        brand="HYB",
        model_number=f"model-{item_id}",
        category="electronics",
        shipping_cost=3.25,
        seller="seller-1",
        image_url=f"https://images.example/{item_id}.png",
        rating=4.8,
        review_count=12,
        in_stock=True,
        data_source=ProductDataSource.PRODUCTION,
    )


def fact(item_id: str, price: float) -> CollectionFact:
    value = product(item_id, price)
    return CollectionFact(
        product=value,
        observed_at=NOW,
        collector_descriptor=DESCRIPTOR,
        source_reference=value.url,
    )


def execute(runtime: RecordingRuntime, provider, *, persister=None):
    events = runtime.events
    return PersistedDiscoveryExecutionEntry(
        persist_command=persister or RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=provider,
        observation_repository=RecordingObservationRepository(),
    ).execute(command())


def test_entry_assembles_one_observation_per_fact_in_input_and_id_order() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    facts = (fact("item-1", 11.5), fact("item-2", 22.75))
    runtime.collection_facts = facts
    provider = SequentialObservationIdentityProvider("opaque:first", "opaque:second")

    result = execute(runtime, provider)

    assert result.discovery_results is runtime.results
    assert result.collection_facts is facts
    assert tuple(value.observation_id for value in result.observations) == (
        "opaque:first",
        "opaque:second",
    )
    assert tuple(value.source_item_id for value in result.observations) == (
        "item-1",
        "item-2",
    )
    assert provider.calls == 2


def test_assembly_copies_product_and_collector_facts_without_calculation() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    source = fact("item-1", 11.5)
    runtime.collection_facts = (source,)

    observation = execute(
        runtime,
        SequentialObservationIdentityProvider("opaque:1"),
    ).observations[0]

    assert all(
        getattr(observation.product, name) == getattr(source.product, name)
        for name in ObservedProductSnapshot.__dataclass_fields__
    )
    assert observation.discovery_execution_id == command().discovery_execution_id
    assert observation.source_marketplace == source.product.marketplace
    assert observation.source_item_id == source.product.item_id
    assert observation.collector_provenance.collector_name == DESCRIPTOR.collector_name
    assert observation.collector_provenance.collector_version == DESCRIPTOR.collector_version
    assert observation.collector_provenance.source_reference == source.source_reference
    assert observation.observed_at is source.observed_at
    assert observation.candidate_market_identity is None


def test_zero_collection_facts_returns_no_observations_or_provider_calls() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    provider = SequentialObservationIdentityProvider()

    result = execute(runtime, provider)

    assert result.observations == ()
    assert provider.calls == 0


def test_zero_discovery_results_can_return_non_empty_observations() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.results = ()
    runtime.collection_facts = (fact("item-1", 11.5),)

    result = execute(
        runtime,
        SequentialObservationIdentityProvider("opaque:1"),
    )

    assert result.discovery_results == ()
    assert tuple(value.observation_id for value in result.observations) == ("opaque:1",)


def test_replay_assembles_with_committed_command_execution_identity() -> None:
    events: list[str] = []
    requested = command()
    committed = replace(requested, discovery_execution_id="committed-execution")

    class ReplayPersister(RecordingPersister):
        def execute(self, value):
            self.events.append("persist")
            return persist_result(committed, replayed=True)

    runtime = RecordingRuntime(events)
    runtime.discovery_execution_id = committed.discovery_execution_id
    runtime.collection_facts = (fact("item-1", 11.5),)
    result = PersistedDiscoveryExecutionEntry(
        persist_command=ReplayPersister(events),
        runtime=runtime,
        observation_identity_provider=SequentialObservationIdentityProvider("opaque:1"),
        observation_repository=RecordingObservationRepository(),
    ).execute(requested)

    assert runtime.calls == [committed]
    assert result.command_result.replayed is True
    assert result.observations[0].discovery_execution_id == "committed-execution"


def test_invalid_provider_identity_propagates_domain_error() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.collection_facts = (fact("item-1", 11.5),)
    provider = SequentialObservationIdentityProvider("")

    with pytest.raises(MalformedCollectorObservationError, match="observation_id"):
        execute(runtime, provider)

    assert provider.calls == 1


def test_correlation_mismatch_is_rejected_before_identity_supply() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.discovery_execution_id = "other-execution"
    runtime.collection_facts = (fact("item-1", 11.5),)
    provider = SequentialObservationIdentityProvider("must-not-be-used")

    with pytest.raises(DiscoveryRuntimeCorrelationError):
        execute(runtime, provider)

    assert provider.calls == 0
