from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.application.discovery import GroupingCorrelation
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from engine import orchestrator
from engine.grouping_policy import GroupingPolicyDescriptor
from tests.test_discovery_phase_checkpoints import engine_opportunity, fact, product
from tests.test_persisted_discovery_execution_entry import command


def test_grouping_policy_descriptor_is_an_exact_immutable_contract() -> None:
    descriptor = GroupingPolicyDescriptor(
        policy_name="caller-policy",
        policy_version="2026.08",
    )

    assert descriptor.policy_name == "caller-policy"
    assert descriptor.policy_version == "2026.08"
    assert set(descriptor.__dataclass_fields__) == {
        "policy_name",
        "policy_version",
    }
    assert descriptor.__slots__ == ("policy_name", "policy_version")
    with pytest.raises(FrozenInstanceError):
        descriptor.policy_version = "changed"


@pytest.mark.parametrize("field", ("policy_name", "policy_version"))
@pytest.mark.parametrize("invalid", ("", "   ", None))
def test_grouping_policy_descriptor_rejects_missing_metadata(
    field: str,
    invalid: object,
) -> None:
    values = {
        "policy_name": "caller-policy",
        "policy_version": "2026.08",
    }
    values[field] = invalid

    with pytest.raises((TypeError, ValueError), match=field):
        GroupingPolicyDescriptor(**values)


def test_grouping_policy_descriptor_has_no_implicit_version() -> None:
    with pytest.raises(TypeError):
        GroupingPolicyDescriptor(policy_name="caller-policy")


def test_production_grouping_owner_declares_authoritative_descriptor() -> None:
    descriptor = orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR

    assert descriptor == GroupingPolicyDescriptor(
        policy_name="product-similarity-greedy-first-match",
        policy_version="1.0.0",
    )


def test_engine_supplies_descriptor_for_zero_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[GroupingPolicyDescriptor] = []
    monkeypatch.setattr(orchestrator, "search_products", lambda *args, **kwargs: [])

    result = orchestrator.find_best_opportunities(
        "nothing",
        grouping_phase_complete_callback=received.append,
    )

    assert result == []
    assert received == [orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR]
    assert received[0] is orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR


def test_engine_descriptor_is_independent_of_execution_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[GroupingPolicyDescriptor] = []
    monkeypatch.setattr(orchestrator, "search_products", lambda *args, **kwargs: [])

    for threshold in (1.0, 99.0):
        orchestrator.find_best_opportunities(
            "nothing",
            match_threshold=threshold,
            grouping_phase_complete_callback=received.append,
        )

    assert received == [
        orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR,
        orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR,
    ]


def test_engine_supplies_descriptor_after_all_correlations_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [product("one"), product("two")]
    events: list[object] = []
    monkeypatch.setattr(
        orchestrator,
        "search_products",
        lambda *args, **kwargs: products,
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_price_change_detector",
        lambda **kwargs: events.append("price-history") or None,
    )
    monkeypatch.setattr(
        orchestrator,
        "analyze_product_prices",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("analysis started")
        ),
    )

    with pytest.raises(RuntimeError, match="analysis started"):
        orchestrator.find_best_opportunities(
            "products",
            grouping_correlation_sink=lambda members, representative: events.append(
                ("correlation", members, representative)
            ),
            grouping_phase_complete_callback=lambda descriptor: events.append(
                ("checkpoint", descriptor)
            ),
        )

    assert events == [
        ("correlation", (0,), 0),
        ("correlation", (1,), 1),
        ("checkpoint", orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR),
        "price-history",
    ]


def test_grouping_checkpoint_failure_prevents_downstream_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "search_products",
        lambda *args, **kwargs: [product("one")],
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_price_change_detector",
        lambda **kwargs: pytest.fail("price history must not start"),
    )

    def fail(descriptor: GroupingPolicyDescriptor) -> None:
        assert descriptor is orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        raise RuntimeError("grouping checkpoint failed")

    with pytest.raises(RuntimeError, match="grouping checkpoint failed"):
        orchestrator.find_best_opportunities(
            "product",
            grouping_phase_complete_callback=fail,
        )


def test_runtime_bridges_correlations_with_exact_engine_descriptor() -> None:
    correlation = GroupingCorrelation((0,), 0)
    received: list[
        tuple[tuple[GroupingCorrelation, ...], GroupingPolicyDescriptor]
    ] = []

    def finder(**kwargs):
        kwargs["collection_fact_sink"](fact("one"))
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_correlation_sink"]((0,), 0)
        finalized_group_ids = kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return [engine_opportunity(product("one"), finalized_group_ids[0])]

    def record_grouping(correlations, descriptor):
        received.append((correlations, descriptor))
        return ("group-1",)

    result = OrchestratorProductionDiscoveryRuntime(finder=finder).execute(
        command(),
        grouping_checkpoint_handler=record_grouping,
    )

    assert received == [
        (
            (correlation,),
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR,
        )
    ]
    assert received[0][1] is orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
    assert result.grouping_correlations == (correlation,)


def test_runtime_bridges_authoritative_descriptor_with_empty_correlations() -> None:
    received = []

    def finder(**kwargs):
        kwargs["collection_phase_complete_callback"]()
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return []

    OrchestratorProductionDiscoveryRuntime(finder=finder).execute(
        command(),
        grouping_checkpoint_handler=lambda correlations, descriptor: (
            received.append((correlations, descriptor)) or ()
        ),
    )

    assert received == [
        ((), orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR)
    ]
