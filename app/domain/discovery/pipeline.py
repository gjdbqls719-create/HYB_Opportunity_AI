from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.domain.discovery.models import DiscoveryResult
from app.domain.discovery.queue import (
    InMemoryOpportunityQueue,
    OpportunityQueue,
)
from app.domain.discovery.ranking import RankingEngine
from app.models import Product


DiscoveryAnalyzer = Callable[[Product], DiscoveryResult]
DiscoveryErrorHandler = Callable[[Product, Exception], None]


@dataclass(slots=True, frozen=True)
class DiscoveryRunSummary:
    submitted_count: int
    queued_count: int
    duplicate_count: int
    analyzed_count: int
    failed_count: int


@dataclass(slots=True, frozen=True)
class DiscoveryRun:
    results: tuple[DiscoveryResult, ...]
    summary: DiscoveryRunSummary

    def top(self, count: int) -> tuple[DiscoveryResult, ...]:
        if count < 1:
            raise ValueError("count는 1 이상이어야 합니다.")
        return self.results[:count]


class DiscoveryPipeline:
    """수집된 상품을 큐, 분석기, 랭킹 엔진으로 연결하는 조정 계층."""

    def __init__(
        self,
        *,
        analyzer: DiscoveryAnalyzer,
        queue: OpportunityQueue | None = None,
        ranking_engine: RankingEngine | None = None,
        error_handler: DiscoveryErrorHandler | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._queue = queue or InMemoryOpportunityQueue()
        self._ranking_engine = ranking_engine or RankingEngine()
        self._error_handler = error_handler

    def run(
        self,
        products: Iterable[Product],
        *,
        limit: int | None = None,
    ) -> DiscoveryRun:
        if len(self._queue) != 0:
            raise RuntimeError(
                "DiscoveryPipeline 실행 전 대기열은 비어 있어야 합니다."
            )

        submitted_count = 0
        queued_count = 0
        duplicate_count = 0
        analyzed_count = 0
        failed_count = 0
        results: list[DiscoveryResult] = []

        try:
            for product in products:
                submitted_count += 1

                if self._queue.enqueue(product):
                    queued_count += 1
                else:
                    duplicate_count += 1

            while len(self._queue) > 0:
                product = self._queue.dequeue()

                if product is None:
                    break

                try:
                    result = self._analyzer(product)
                except Exception as error:
                    failed_count += 1

                    if self._error_handler is not None:
                        self._error_handler(product, error)

                    continue

                if result.product is not product:
                    raise ValueError(
                        "analyzer는 입력 Product를 포함한 DiscoveryResult를 "
                        "반환해야 합니다."
                    )

                analyzed_count += 1
                results.append(result)
        finally:
            self._queue.clear()

        ranked_results = self._ranking_engine.rank(
            results,
            limit=limit,
        )

        return DiscoveryRun(
            results=tuple(ranked_results),
            summary=DiscoveryRunSummary(
                submitted_count=submitted_count,
                queued_count=queued_count,
                duplicate_count=duplicate_count,
                analyzed_count=analyzed_count,
                failed_count=failed_count,
            ),
        )
