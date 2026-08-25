from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.application.discovery import (
    DiscoveryRuntimeCorrelationError,
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
)
from app.domain.discovery import DiscoveryResult
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from app.models import Product
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from engine import orchestrator
from engine.orchestrator import OpportunityResult
from engine.recommendation import RecommendationResult
from tests.test_persisted_discovery_execution_entry import (
    RecordingObservationIdentityProvider,
    RecordingObservationRepository,
    RecordingPersister,
    RecordingRuntime,
    command,
    finalization_dependencies,
)


OBSERVED_AT = datetime(2026, 8, 26, 1, tzinfo=timezone.utc)
COLLECTOR = CollectorDescriptor("ebay", "screening-correlation-test")


def product(item_id: str, price: float = 10.0) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=f"Distinct Product {item_id}",
        price=price,
        currency="USD",
        condition="New",
        url=f"https://example.com/{item_id}",
    )


def fact(item_id: str, price: float = 10.0) -> CollectionFact:
    value = product(item_id, price)
    return CollectionFact(
        value,
        OBSERVED_AT,
        COLLECTOR,
        value.url,
    )


def recommendation(score: int) -> RecommendationResult:
    return RecommendationResult(
        score=score,
        stars=3,
        star_display="★★★☆☆",
        grade="WATCH",
        action="review",
        success_probability=score,
        reasons=("reason",),
        warnings=(),
        summary="summary",
    )


def opportunity(
    item_id: str,
    finalized_group_id: str | None,
    *,
    recommendation_score: int = 50,
    final_score: float = 50.0,
    net_profit: float = 10.0,
) -> OpportunityResult:
    return OpportunityResult(
        product=product(item_id),
        analysis={"net_profit": net_profit},
        matched_product_count=1,
        price_intelligence=object(),
        final_opportunity_score=final_score,
        ai_recommendation=recommendation(recommendation_score),
        finalized_group_id=finalized_group_id,
    )


def discovery_result(
    item_id: str,
    finalized_group_id: str | None,
) -> DiscoveryResult:
    return DiscoveryResult(
        product=product(item_id),
        opportunity_score=50,
        finalized_group_id=finalized_group_id,
    )


def test_existing_ranking_order_and_stable_ties_ignore_correlation() -> None:
    values = [
        opportunity("net-low", "group-net-low", net_profit=10),
        opportunity(
            "tie-first",
            "group-tie-first",
            recommendation_score=40,
            final_score=40,
            net_profit=5,
        ),
        opportunity(
            "recommendation-high",
            "group-recommendation-high",
            recommendation_score=90,
            final_score=1,
            net_profit=1,
        ),
        opportunity(
            "final-high",
            "group-final-high",
            final_score=80,
            net_profit=1,
        ),
        opportunity("net-high", "group-net-high", net_profit=20),
        opportunity(
            "tie-second",
            "group-tie-second",
            recommendation_score=40,
            final_score=40,
            net_profit=5,
        ),
    ]

    orchestrator._sort_opportunity_results(values)

    assert [value.product.item_id for value in values] == [
        "recommendation-high",
        "final-high",
        "net-high",
        "net-low",
        "tie-first",
        "tie-second",
    ]
    assert [value.finalized_group_id for value in values] == [
        "group-recommendation-high",
        "group-final-high",
        "group-net-high",
        "group-net-low",
        "group-tie-first",
        "group-tie-second",
    ]


def test_engine_propagates_checkpointed_group_ids_through_reordering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = [product("cheap", 10), product("expensive", 100)]
    correlations: list[tuple[tuple[int, ...], int]] = []
    monkeypatch.setattr(
        orchestrator,
        "search_products",
        lambda query, limit: products,
    )

    results = orchestrator.find_best_opportunities(
        "products",
        grouping_correlation_sink=lambda members, representative: correlations.append(
            (members, representative)
        ),
        grouping_phase_complete_callback=lambda descriptor: (
            "finalized-cheap",
            "finalized-expensive",
        ),
    )

    assert correlations == [((0,), 0), ((1,), 1)]
    assert [value.product.item_id for value in results] == ["expensive", "cheap"]
    assert {
        value.product.item_id: value.finalized_group_id for value in results
    } == {
        "cheap": "finalized-cheap",
        "expensive": "finalized-expensive",
    }


@pytest.mark.parametrize(
    ("returned_ids", "message"),
    (
        (("only-one",), "count"),
        (("duplicate", "duplicate"), "unique"),
        (("valid", ""), "non-empty"),
    ),
)
def test_engine_rejects_invalid_checkpointed_group_ids(
    monkeypatch: pytest.MonkeyPatch,
    returned_ids: tuple[str, ...],
    message: str,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "search_products",
        lambda query, limit: [product("one"), product("two")],
    )

    with pytest.raises(ValueError, match=message):
        orchestrator.find_best_opportunities(
            "products",
            grouping_phase_complete_callback=lambda descriptor: returned_ids,
        )


def test_engine_accepts_authoritative_zero_group_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "search_products",
        lambda query, limit: [],
    )

    assert orchestrator.find_best_opportunities(
        "products",
        grouping_phase_complete_callback=lambda descriptor: (),
    ) == []


def runtime_finder(
    result_ids: tuple[str | None, ...],
    *,
    correlation_count: int,
):
    def finder(**kwargs):
        for index in range(correlation_count):
            kwargs["collection_fact_sink"](fact(f"item-{index}"))
        kwargs["collection_phase_complete_callback"]()
        for index in range(correlation_count):
            kwargs["grouping_correlation_sink"]((index,), index)
        kwargs["grouping_phase_complete_callback"](
            orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR
        )
        return [
            opportunity(f"result-{index}", finalized_group_id)
            for index, finalized_group_id in enumerate(result_ids)
        ]

    return finder


def test_production_runtime_maps_reordered_results_to_exact_finalized_groups() -> None:
    runtime = OrchestratorProductionDiscoveryRuntime(
        finder=runtime_finder(
            ("group-2", "group-1"),
            correlation_count=2,
        )
    )

    result = runtime.execute(
        command(),
        collection_checkpoint_handler=lambda values: None,
        grouping_checkpoint_handler=lambda values, descriptor: (
            "group-1",
            "group-2",
        ),
    )

    assert [value.finalized_group_id for value in result.discovery_results] == [
        "group-2",
        "group-1",
    ]
    assert [value.product.item_id for value in result.discovery_results] == [
        "result-0",
        "result-1",
    ]


@pytest.mark.parametrize(
    ("result_ids", "correlation_count", "message"),
    (
        ((None,), 1, "missing"),
        (("unknown",), 1, "unknown"),
        (("group-1", "group-1"), 2, "duplicate"),
        (("group-1",), 2, "count"),
    ),
)
def test_production_runtime_rejects_invalid_result_correlation(
    result_ids: tuple[str | None, ...],
    correlation_count: int,
    message: str,
) -> None:
    expected_ids = tuple(
        f"group-{index + 1}" for index in range(correlation_count)
    )
    runtime = OrchestratorProductionDiscoveryRuntime(
        finder=runtime_finder(result_ids, correlation_count=correlation_count)
    )

    with pytest.raises(DiscoveryRuntimeCorrelationError, match=message):
        runtime.execute(
            command(),
            collection_checkpoint_handler=lambda values: None,
            grouping_checkpoint_handler=lambda values, descriptor: expected_ids,
        )


def test_application_rejects_custom_runtime_unknown_group_correlation() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.collection_facts = (fact("one"),)
    runtime.grouping_correlations = (GroupingCorrelation((0,), 0),)
    runtime.results = (discovery_result("one", "unknown-group"),)

    with pytest.raises(DiscoveryRuntimeCorrelationError, match="unknown"):
        PersistedDiscoveryExecutionEntry(
            persist_command=RecordingPersister(events),
            runtime=runtime,
            observation_identity_provider=RecordingObservationIdentityProvider(
                "observation-one"
            ),
            observation_repository=RecordingObservationRepository(),
            **finalization_dependencies(),
        ).execute(command())


def test_application_preserves_exact_mapping_after_runtime_reordering() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.collection_facts = (fact("one"), fact("two"))
    runtime.grouping_correlations = (
        GroupingCorrelation((0,), 0),
        GroupingCorrelation((1,), 1),
    )
    runtime.results = (
        discovery_result("two", "finalized-group-2"),
        discovery_result("one", "finalized-group-1"),
    )

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-one",
            "observation-two",
        ),
        observation_repository=RecordingObservationRepository(),
        **finalization_dependencies(),
    ).execute(command())

    assert [value.finalized_group_id for value in result.discovery_results] == [
        "finalized-group-2",
        "finalized-group-1",
    ]
    assert [value.finalized_group_id for value in result.finalized_groups] == [
        "finalized-group-1",
        "finalized-group-2",
    ]


def test_discovery_result_rejects_blank_correlation_but_keeps_legacy_optional() -> None:
    assert discovery_result("legacy", None).finalized_group_id is None
    with pytest.raises(ValueError, match="finalized_group_id"):
        discovery_result("invalid", " ")
