from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

import pytest

from app.application.discovery import (
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
    ProductionDiscoveryRuntimeResult,
)
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from app.models import Product
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from engine import orchestrator
from tests.test_persisted_discovery_execution_entry import (
    RecordingObservationIdentityProvider,
    RecordingPersister,
    command,
)


OBSERVED_AT = datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc)
DESCRIPTOR = CollectorDescriptor("ebay", "test-collector-implementation")


def product(item_id: str, *, price: float = 10.0) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=f"Product {item_id}",
        price=price,
        currency="USD",
        condition="new",
        url=f"https://example.com/{item_id}",
    )


def fact(item_id: str) -> CollectionFact:
    value = product(item_id)
    return CollectionFact(value, OBSERVED_AT, DESCRIPTOR, value.url)


def test_engine_calls_phase_checkpoints_at_exact_lifecycle_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [product("high", price=20), product("low", price=10)]
    facts = [fact("high"), fact("low")]
    events: list[str] = []

    def search_products(*args, collection_fact_sink=None, **kwargs):
        for value in facts:
            events.append(f"item:{value.product.item_id}")
            collection_fact_sink(value)
        return products

    def normalize_products_currency(values, **kwargs):
        events.append("normalize")
        return values

    original_group = orchestrator.group_similar_products

    def group_similar_products(values, **kwargs):
        events.append("grouping")
        sink = kwargs["grouping_correlation_sink"]

        def recording_sink(members, representative):
            events.append(f"correlation:{members}:{representative}")
            sink(members, representative)

        return original_group(
            values,
            match_threshold=kwargs["match_threshold"],
            grouping_correlation_sink=recording_sink,
        )

    monkeypatch.setattr(orchestrator, "search_products", search_products)
    monkeypatch.setattr(
        orchestrator, "normalize_products_currency", normalize_products_currency
    )
    monkeypatch.setattr(orchestrator, "group_similar_products", group_similar_products)
    monkeypatch.setattr(
        orchestrator,
        "_build_price_change_detector",
        lambda **kwargs: events.append("price-history") or None,
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_product_prices",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("downstream analysis started")
        ),
    )

    with pytest.raises(RuntimeError, match="downstream analysis started"):
        orchestrator.find_best_opportunities(
            "product",
            currency_converter=object(),
            target_currency="USD",
            collection_fact_sink=lambda value: None,
            grouping_correlation_sink=lambda members, representative: None,
            collection_phase_complete_callback=lambda: events.append(
                "collection-checkpoint"
            ),
            grouping_phase_complete_callback=lambda descriptor: events.append(
                "grouping-checkpoint"
            ),
        )

    assert events == [
        "item:high",
        "item:low",
        "normalize",
        "collection-checkpoint",
        "grouping",
        "correlation:(0,):0",
        "correlation:(1,):1",
        "grouping-checkpoint",
        "price-history",
    ]


def test_engine_calls_both_phase_checkpoints_once_for_zero_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(orchestrator, "search_products", lambda *args, **kwargs: [])

    result = orchestrator.find_best_opportunities(
        "nothing",
        collection_phase_complete_callback=lambda: events.append("collection"),
        grouping_phase_complete_callback=lambda descriptor: events.append("grouping"),
    )

    assert result == []
    assert events == ["collection", "grouping"]


def test_engine_omitted_and_noop_callbacks_preserve_existing_zero_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "search_products", lambda *args, **kwargs: [])

    without_callbacks = orchestrator.find_best_opportunities("nothing")
    with_noops = orchestrator.find_best_opportunities(
        "nothing",
        collection_phase_complete_callback=lambda: None,
        grouping_phase_complete_callback=lambda descriptor: None,
    )

    assert without_callbacks == with_noops == []


def test_collection_checkpoint_failure_stops_grouping_and_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "search_products", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        orchestrator,
        "group_similar_products",
        lambda *args, **kwargs: pytest.fail("grouping must not start"),
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_product_prices",
        lambda *args, **kwargs: pytest.fail("analysis must not start"),
    )

    with pytest.raises(RuntimeError, match="collection checkpoint failed"):
        orchestrator.find_best_opportunities(
            "product",
            collection_phase_complete_callback=lambda: (_ for _ in ()).throw(
                RuntimeError("collection checkpoint failed")
            ),
        )


def test_grouping_checkpoint_failure_stops_price_history_and_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator, "search_products", lambda *args, **kwargs: [product("one")]
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_price_change_detector",
        lambda **kwargs: pytest.fail("price history must not start"),
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_product_prices",
        lambda *args, **kwargs: pytest.fail("analysis must not start"),
    )

    with pytest.raises(RuntimeError, match="grouping checkpoint failed"):
        orchestrator.find_best_opportunities(
            "product",
            grouping_phase_complete_callback=lambda descriptor: (_ for _ in ()).throw(
                RuntimeError("grouping checkpoint failed")
            ),
        )


def test_runtime_bridges_immutable_ordered_phase_facts() -> None:
    facts = (fact("one"), fact("two"))
    correlations = (
        GroupingCorrelation((0,), 0),
        GroupingCorrelation((1,), 1),
    )
    events: list[object] = []

    def finder(**kwargs):
        for value in facts:
            kwargs["collection_fact_sink"](value)
        kwargs["collection_phase_complete_callback"]()
        for correlation in correlations:
            kwargs["grouping_correlation_sink"](
                correlation.ordered_member_collection_positions,
                correlation.representative_collection_position,
            )
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    result = OrchestratorProductionDiscoveryRuntime(finder=finder).execute(
        command(),
        collection_checkpoint_handler=lambda values: events.append(
            ("collection", values)
        ),
        grouping_checkpoint_handler=lambda values, descriptor: events.append(
            ("grouping", values)
        ),
    )

    assert events == [
        ("collection", facts),
        ("grouping", correlations),
    ]
    assert result.collection_facts == facts
    assert result.grouping_correlations == correlations
    assert isinstance(events[0][1], tuple)
    assert isinstance(events[1][1], tuple)


def test_runtime_calls_handlers_with_empty_tuples() -> None:
    received: list[tuple[object, ...]] = []

    def finder(**kwargs):
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    OrchestratorProductionDiscoveryRuntime(finder=finder).execute(
        command(),
        collection_checkpoint_handler=received.append,
        grouping_checkpoint_handler=lambda values, descriptor: received.append(values),
    )

    assert received == [(), ()]


def test_runtime_checkpoint_handlers_isolate_consecutive_executions() -> None:
    calls = 0
    received: list[tuple[CollectionFact, ...]] = []

    def finder(**kwargs):
        nonlocal calls
        calls += 1
        kwargs["collection_fact_sink"](fact(f"item-{calls}"))
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_correlation_sink"]((0,), 0)
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)
    runtime.execute(command(), collection_checkpoint_handler=received.append)
    runtime.execute(command(), collection_checkpoint_handler=received.append)

    assert tuple(value.product.item_id for value in received[0]) == ("item-1",)
    assert tuple(value.product.item_id for value in received[1]) == ("item-2",)
    assert received[0] is not received[1]


def test_runtime_omitted_handlers_preserve_existing_result_contract() -> None:
    def finder(**kwargs):
        kwargs["collection_fact_sink"](fact("one"))
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_correlation_sink"]((0,), 0)
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    result = OrchestratorProductionDiscoveryRuntime(finder=finder).execute(command())

    assert result == ProductionDiscoveryRuntimeResult(
        discovery_execution_id="execution-1",
        discovery_results=(),
        collection_facts=(fact("one"),),
        grouping_correlations=(GroupingCorrelation((0,), 0),),
    )


class CheckpointRuntime:
    def __init__(
        self,
        events: list[str],
        *,
        fail_after_grouping: Exception | None = None,
    ) -> None:
        self.events = events
        self.fail_after_grouping = fail_after_grouping
        self.calls = []
        self.collection_facts = (fact("one"), fact("two"))
        self.grouping_correlations = (GroupingCorrelation((0, 1), 0),)

    def execute(
        self,
        value,
        *,
        collection_checkpoint_handler=None,
        grouping_checkpoint_handler=None,
    ):
        self.events.append("runtime")
        self.calls.append(value)
        self.events.append("collection-checkpoint")
        collection_checkpoint_handler(self.collection_facts)
        self.events.append("grouping")
        grouping_checkpoint_handler(
            self.grouping_correlations,
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR,
        )
        self.events.append("grouping-checkpoint")
        if self.fail_after_grouping is not None:
            raise self.fail_after_grouping
        self.events.append("analysis")
        return ProductionDiscoveryRuntimeResult(
            value.discovery_execution_id,
            (),
            self.collection_facts,
            self.grouping_correlations,
        )


class CheckpointObservationRepository:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.calls = []

    def save_observation(self, observation):
        self.events.append(f"observation:{observation.source_item_id}")
        self.calls.append(observation)
        if self.fail:
            raise RuntimeError("observation persistence failed")
        return observation


def entry(events, runtime, repository, *, persister=None):
    return PersistedDiscoveryExecutionEntry(
        persist_command=persister or RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-one", "observation-two"
        ),
        observation_repository=repository,
    )


def test_entry_persists_observations_at_collection_checkpoint_without_duplicate_save() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    repository = CheckpointObservationRepository(events)

    result = entry(events, runtime, repository).execute(command())

    assert events == [
        "persist",
        "runtime",
        "collection-checkpoint",
        "observation:one",
        "observation:two",
        "grouping",
        "grouping-checkpoint",
        "analysis",
    ]
    assert len(repository.calls) == 2
    assert result.observations == tuple(repository.calls)
    assert result.grouping_correlations is runtime.grouping_correlations


def test_observation_failure_at_checkpoint_prevents_grouping() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    repository = CheckpointObservationRepository(events, fail=True)

    with pytest.raises(RuntimeError, match="observation persistence failed"):
        entry(events, runtime, repository).execute(command())

    assert "grouping" not in events
    assert "analysis" not in events


def test_runtime_failure_preserves_already_checkpointed_observations() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(
        events, fail_after_grouping=RuntimeError("downstream failed")
    )
    repository = CheckpointObservationRepository(events)

    with pytest.raises(RuntimeError, match="downstream failed"):
        entry(events, runtime, repository).execute(command())

    assert tuple(value.observation_id for value in repository.calls) == (
        "observation-one",
        "observation-two",
    )
    assert "analysis" not in events


def test_persistence_failure_prevents_runtime_and_checkpoints() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)

    with pytest.raises(RuntimeError, match="command persistence failed"):
        entry(
            events,
            runtime,
            CheckpointObservationRepository(events),
            persister=RecordingPersister(
                events, fail=RuntimeError("command persistence failed")
            ),
        ).execute(command())

    assert runtime.calls == []
    assert events == ["persist"]


def test_replay_passes_committed_command_to_checkpoint_runtime() -> None:
    events: list[str] = []
    requested = command()
    committed = replace(requested, discovery_execution_id="committed-execution")

    class ReplayPersister(RecordingPersister):
        def execute(self, value):
            from tests.test_persisted_discovery_execution_entry import persist_result

            self.events.append("persist")
            return persist_result(committed, replayed=True)

    runtime = CheckpointRuntime(events)
    result = entry(
        events,
        runtime,
        CheckpointObservationRepository(events),
        persister=ReplayPersister(events),
    ).execute(requested)

    assert runtime.calls == [committed]
    assert result.command_result.replayed is True
    assert all(
        value.discovery_execution_id == "committed-execution"
        for value in result.observations
    )


def test_runtime_checkpoint_buffers_are_isolated_across_concurrent_executions() -> None:
    barrier = Barrier(2)
    received: dict[str, tuple[CollectionFact, ...]] = {}

    def finder(**kwargs):
        barrier.wait()
        value = fact(kwargs["query"])
        kwargs["collection_fact_sink"](value)
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_correlation_sink"]((0,), 0)
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    runtime = OrchestratorProductionDiscoveryRuntime(finder=finder)
    first = replace(command(), parameters=replace(command().parameters, query="first"))
    second = replace(
        command(),
        command_id="command-2",
        discovery_execution_id="execution-2",
        parameters=replace(command().parameters, query="second"),
    )

    def execute(value):
        return runtime.execute(
            value,
            collection_checkpoint_handler=lambda facts: received.__setitem__(
                value.discovery_execution_id, facts
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(execute, first)
        second_future = pool.submit(execute, second)
        first_result = first_future.result()
        second_result = second_future.result()

    assert tuple(value.product.item_id for value in received["execution-1"]) == (
        "first",
    )
    assert tuple(value.product.item_id for value in received["execution-2"]) == (
        "second",
    )
    assert first_result.collection_facts is not second_result.collection_facts
