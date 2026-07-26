from __future__ import annotations

import pytest

from app.domain.discovery import (
    DiscoveryPipeline,
    DiscoveryResult,
    InMemoryOpportunityQueue,
    RankingEngine,
)
from app.models import Product


def product(
    item_id: str,
    *,
    title: str | None = None,
    price: float = 100.0,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=title or f"Product {item_id}",
        price=price,
        currency="USD",
    )


def result(
    item_id: str,
    score: float,
    *,
    matched_count: int = 1,
    price: float = 100.0,
) -> DiscoveryResult:
    return DiscoveryResult(
        product=product(item_id, price=price),
        opportunity_score=score,
        matched_product_count=matched_count,
    )


def test_discovery_result_is_immutable_and_metadata_is_read_only():
    discovery_result = DiscoveryResult(
        product=product("1"),
        opportunity_score=80,
        metadata={"source": "test"},
    )

    with pytest.raises(TypeError):
        discovery_result.metadata["source"] = "changed"


def test_discovery_result_validates_score():
    with pytest.raises(ValueError):
        DiscoveryResult(
            product=product("1"),
            opportunity_score=101,
        )


def test_queue_rejects_duplicate_identity():
    queue = InMemoryOpportunityQueue()

    assert queue.enqueue(product("1")) is True
    assert queue.enqueue(product("1", title="Other title")) is False
    assert len(queue) == 1


def test_queue_is_fifo_and_allows_requeue_after_dequeue():
    queue = InMemoryOpportunityQueue()
    first = product("1")
    second = product("2")

    queue.enqueue(first)
    queue.enqueue(second)

    assert queue.dequeue() is first
    assert queue.dequeue() is second
    assert queue.enqueue(first) is True


def test_ranking_orders_by_score_and_assigns_rank():
    ranked = RankingEngine().rank(
        [
            result("low", 50),
            result("high", 90),
            result("mid", 70),
        ]
    )

    assert [item.product.item_id for item in ranked] == [
        "high",
        "mid",
        "low",
    ]
    assert [item.rank for item in ranked] == [1, 2, 3]


def test_ranking_uses_evidence_count_as_first_tiebreaker():
    ranked = RankingEngine().rank(
        [
            result("weak", 80, matched_count=1),
            result("strong", 80, matched_count=3),
        ]
    )

    assert ranked[0].product.item_id == "strong"


def test_ranking_applies_limit():
    ranked = RankingEngine().rank(
        [result("1", 90), result("2", 80)],
        limit=1,
    )

    assert len(ranked) == 1
    assert ranked[0].rank == 1


def test_pipeline_deduplicates_analyzes_and_ranks():
    def analyzer(item: Product) -> DiscoveryResult:
        return DiscoveryResult(
            product=item,
            opportunity_score=float(item.price),
        )

    run = DiscoveryPipeline(analyzer=analyzer).run(
        [
            product("1", price=40),
            product("2", price=90),
            product("1", price=80),
        ]
    )

    assert [item.product.item_id for item in run.results] == ["2", "1"]
    assert run.summary.submitted_count == 3
    assert run.summary.queued_count == 2
    assert run.summary.duplicate_count == 1
    assert run.summary.analyzed_count == 2
    assert run.summary.failed_count == 0


def test_pipeline_isolates_analyzer_failure_and_reports_it():
    errors: list[tuple[str, str]] = []

    def analyzer(item: Product) -> DiscoveryResult:
        if item.item_id == "bad":
            raise RuntimeError("analysis failed")

        return DiscoveryResult(
            product=item,
            opportunity_score=70,
        )

    run = DiscoveryPipeline(
        analyzer=analyzer,
        error_handler=lambda item, error: errors.append(
            (item.item_id, str(error))
        ),
    ).run([product("bad"), product("good")])

    assert [item.product.item_id for item in run.results] == ["good"]
    assert run.summary.failed_count == 1
    assert errors == [("bad", "analysis failed")]


def test_pipeline_clears_queue_after_unexpected_contract_error():
    queue = InMemoryOpportunityQueue()

    def analyzer(item: Product) -> DiscoveryResult:
        return DiscoveryResult(
            product=product("different"),
            opportunity_score=50,
        )

    pipeline = DiscoveryPipeline(
        analyzer=analyzer,
        queue=queue,
    )

    with pytest.raises(ValueError):
        pipeline.run([product("original")])

    assert len(queue) == 0


def test_discovery_run_top_validates_count():
    run = DiscoveryPipeline(
        analyzer=lambda item: DiscoveryResult(
            product=item,
            opportunity_score=50,
        )
    ).run([product("1")])

    assert len(run.top(1)) == 1

    with pytest.raises(ValueError):
        run.top(0)
