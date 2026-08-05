from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.application.discovery.production_execution import (
    DiscoveryRuntimeCorrelationError,
    PersistedDiscoveryExecutionEntry,
    PersistedDiscoveryExecutionResult,
    ProductionDiscoveryRuntimeResult,
)
from app.application.discovery_persistence import (
    DiscoveryCommandReceipt,
    PersistDiscoveryCommandResult,
)
from app.domain.discovery import DiscoveryResult
from app.domain.discovery_identity import DiscoveryCommand, DiscoveryCommandParameters
from app.models import Product
from collectors.collection_fact import CollectionFact
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)


NOW = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)


def command() -> DiscoveryCommand:
    return DiscoveryCommand(
        command_id="command-1",
        discovery_execution_id="execution-1",
        parameters=DiscoveryCommandParameters(
            query="iphone 15 pro",
            selling_price_multiplier=Decimal("1.75"),
            shipping_cost=Decimal("12.34"),
            marketplace_fee_rate=Decimal("0.14"),
            payment_fee_rate=Decimal("0.031"),
            fixed_fee=Decimal("0.45"),
            marketplace_fee_known=True,
            payment_fee_known=True,
            fixed_fee_known=True,
            tax_rate=Decimal("0.08"),
            other_cost=Decimal("3.21"),
            minimum_net_profit=Decimal("25.00"),
            minimum_roi=Decimal("18.50"),
            estimated_monthly_sales=55,
            competitor_count=9,
            risk_level="low",
            limit=17,
            match_threshold=Decimal("81.25"),
            target_currency="krw",
            policy_references=(("pricing", "policy-v3"),),
            source_references=(("market", "ebay-us"),),
        ),
        requested_at=NOW,
    )


def persist_result(value: DiscoveryCommand, *, replayed: bool = False) -> PersistDiscoveryCommandResult:
    return PersistDiscoveryCommandResult(
        command=value,
        receipt=DiscoveryCommandReceipt(
            command_id=value.command_id,
            execution_id=value.discovery_execution_id,
            canonical_payload_fingerprint=value.fingerprint,
            committed_at=NOW,
        ),
        replayed=replayed,
    )


def discovery_result() -> DiscoveryResult:
    return DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id="item-1",
            title="iPhone 15 Pro",
            price=100.0,
            currency="USD",
        ),
        opportunity_score=77.0,
    )


class RecordingPersister:
    def __init__(self, events: list[str], *, fail: Exception | None = None):
        self.events = events
        self.fail = fail
        self.calls: list[DiscoveryCommand] = []

    def execute(self, value: DiscoveryCommand):
        self.events.append("persist")
        self.calls.append(value)
        if self.fail is not None:
            raise self.fail
        return persist_result(value)


class RecordingRuntime:
    def __init__(self, events: list[str], *, fail: Exception | None = None):
        self.events = events
        self.fail = fail
        self.calls: list[DiscoveryCommand] = []
        self.results = (discovery_result(),)
        self.collection_facts = ()
        self.discovery_execution_id = "execution-1"

    def execute(self, value: DiscoveryCommand):
        self.events.append("runtime")
        self.calls.append(value)
        if self.fail is not None:
            raise self.fail
        return ProductionDiscoveryRuntimeResult(
            discovery_execution_id=self.discovery_execution_id,
            discovery_results=self.results,
            collection_facts=self.collection_facts,
        )


def test_entry_persists_before_runtime_and_returns_both_results() -> None:
    events: list[str] = []
    value = command()
    persister = RecordingPersister(events)
    runtime = RecordingRuntime(events)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=persister,
        runtime=runtime,
    ).execute(value)

    assert events == ["persist", "runtime"]
    assert persister.calls == [value]
    assert runtime.calls == [value]
    assert isinstance(result, PersistedDiscoveryExecutionResult)
    assert result.command_result.command is value
    assert result.discovery_results == runtime.results
    assert result.collection_facts == ()


def test_entry_does_not_run_runtime_when_persistence_fails() -> None:
    events: list[str] = []
    persistence_error = RuntimeError("persistence failed")
    runtime = RecordingRuntime(events)

    with pytest.raises(RuntimeError, match="persistence failed"):
        PersistedDiscoveryExecutionEntry(
            persist_command=RecordingPersister(events, fail=persistence_error),
            runtime=runtime,
        ).execute(command())

    assert events == ["persist"]
    assert runtime.calls == []


def test_entry_keeps_persisted_command_when_runtime_fails() -> None:
    events: list[str] = []
    persister = RecordingPersister(events)

    with pytest.raises(RuntimeError, match="runtime failed"):
        PersistedDiscoveryExecutionEntry(
            persist_command=persister,
            runtime=RecordingRuntime(events, fail=RuntimeError("runtime failed")),
        ).execute(command())

    assert events == ["persist", "runtime"]
    assert persister.calls == [command()]


def test_entry_passes_the_committed_replay_command_to_runtime() -> None:
    events: list[str] = []
    requested = command()
    committed = command()

    class ReplayPersister(RecordingPersister):
        def execute(self, value: DiscoveryCommand):
            self.events.append("persist")
            return persist_result(committed, replayed=True)

    runtime = RecordingRuntime(events)
    result = PersistedDiscoveryExecutionEntry(
        persist_command=ReplayPersister(events),
        runtime=runtime,
    ).execute(requested)

    assert runtime.calls == [committed]
    assert result.command_result.replayed is True


def test_entry_returns_collection_facts_without_changing_them() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    product = discovery_result().product
    facts = (
        CollectionFact(product, NOW, "ebay", "source-1"),
        CollectionFact(product, NOW, "ebay", "source-2"),
    )
    runtime.collection_facts = facts

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
    ).execute(command())

    assert result.collection_facts is facts
    assert result.discovery_results == runtime.results


def test_entry_rejects_runtime_execution_identity_mismatch() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.discovery_execution_id = "other-execution"

    with pytest.raises(DiscoveryRuntimeCorrelationError, match="execution identity"):
        PersistedDiscoveryExecutionEntry(
            persist_command=RecordingPersister(events),
            runtime=runtime,
        ).execute(command())

    assert events == ["persist", "runtime"]


def test_orchestrator_runtime_forwards_all_execution_affecting_parameters() -> None:
    value = command()
    calls: list[dict[str, object]] = []
    converter = object()
    price_history_repository = object()
    search_error_handler = object()
    opportunity_history_repository = object()
    ai_memory_history = [object()]
    opportunity = SimpleNamespace(
        product=SimpleNamespace(),
        final_opportunity_score=77.0,
        matched_product_count=4,
        ai_recommendation=None,
        analysis={},
        confidence=None,
    )

    def finder(**kwargs):
        calls.append(kwargs)
        return [opportunity]

    runtime = OrchestratorProductionDiscoveryRuntime(
        finder=finder,
        price_history_repository=price_history_repository,
        search_error_handler=search_error_handler,
        opportunity_history_repository=opportunity_history_repository,
        ai_memory_history=ai_memory_history,
        currency_converter=converter,
    )

    runtime_result = runtime.execute(value)

    assert len(runtime_result.discovery_results) == 1
    assert runtime_result.discovery_execution_id == "execution-1"
    collection_fact_sink = calls[0].pop("collection_fact_sink")
    assert callable(collection_fact_sink)
    assert calls == [
        {
            "query": "iphone 15 pro",
            "selling_price_multiplier": 1.75,
            "shipping_cost": 12.34,
            "marketplace_fee_rate": 0.14,
            "payment_fee_rate": 0.031,
            "fixed_fee": 0.45,
            "marketplace_fee_known": True,
            "payment_fee_known": True,
            "fixed_fee_known": True,
            "tax_rate": 0.08,
            "other_cost": 3.21,
            "minimum_net_profit": 25.0,
            "minimum_roi": 18.5,
            "estimated_monthly_sales": 55,
            "competitor_count": 9,
            "risk_level": "low",
            "limit": 17,
            "match_threshold": 81.25,
            "price_history_repository": price_history_repository,
            "search_error_handler": search_error_handler,
            "opportunity_history_repository": opportunity_history_repository,
            "ai_memory_history": ai_memory_history,
            "currency_converter": converter,
            "target_currency": "KRW",
        }
    ]
    assert "policy_references" not in calls[0]
    assert "source_references" not in calls[0]
