from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.application.discovery import (
    DiscoverOpportunitiesUseCase,
    DiscoverySession,
    DiscoverySessionStatus,
)
from app.domain.discovery import DiscoveryResult
from app.infrastructure.discovery import (
    OrchestratorOpportunityDiscoveryGateway,
)
from app.models import Product


def product(item_id: str, *, price: float = 100.0) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=f"Product {item_id}",
        price=price,
        currency="USD",
    )


def result(item_id: str, score: float) -> DiscoveryResult:
    return DiscoveryResult(
        product=product(item_id),
        opportunity_score=score,
    )


class FakeGateway:
    def __init__(self, results: list[DiscoveryResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def discover(self, *, query: str, limit: int) -> list[DiscoveryResult]:
        self.calls.append((query, limit))
        return list(self.results)


class FailingGateway:
    def discover(self, *, query: str, limit: int) -> list[DiscoveryResult]:
        raise RuntimeError("gateway failed")


def test_session_trims_query_and_starts_running():
    session = DiscoverySession(query="  iphone  ", requested_limit=10)

    assert session.query == "iphone"
    assert session.status is DiscoverySessionStatus.RUNNING
    assert session.finished_at is None


def test_session_validates_query_and_limit():
    with pytest.raises(ValueError):
        DiscoverySession(query=" ", requested_limit=10)

    with pytest.raises(ValueError):
        DiscoverySession(query="iphone", requested_limit=0)


def test_session_complete_records_terminal_state():
    started_at = datetime(2026, 7, 27, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    session = DiscoverySession(
        query="iphone",
        requested_limit=10,
        started_at=started_at,
    )

    session.complete(finished_at=finished_at)

    assert session.status is DiscoverySessionStatus.COMPLETED
    assert session.finished_at == finished_at
    assert session.error_message is None


def test_session_cannot_finish_twice():
    session = DiscoverySession(query="iphone", requested_limit=10)
    session.complete()

    with pytest.raises(RuntimeError):
        session.complete()


def test_use_case_calls_gateway_ranks_and_limits_results():
    gateway = FakeGateway(
        [result("low", 40), result("high", 90), result("mid", 70)]
    )
    use_case = DiscoverOpportunitiesUseCase(gateway=gateway)

    response = use_case.execute(
        query="  iphone  ",
        collection_limit=30,
        result_limit=2,
    )

    assert gateway.calls == [("iphone", 30)]
    assert [item.product.item_id for item in response.results] == [
        "high",
        "mid",
    ]
    assert [item.rank for item in response.results] == [1, 2]
    assert response.session.status is DiscoverySessionStatus.COMPLETED


def test_use_case_builds_statistics():
    gateway = FakeGateway(
        [result("strong", 80), result("watch", 50), result("weak", 20)]
    )
    use_case = DiscoverOpportunitiesUseCase(
        gateway=gateway,
        strong_score_threshold=65,
    )

    response = use_case.execute(query="camera", result_limit=2)

    assert response.statistics.discovered_count == 3
    assert response.statistics.returned_count == 2
    assert response.statistics.strong_opportunity_count == 1


def test_use_case_response_top_validates_count():
    response = DiscoverOpportunitiesUseCase(
        gateway=FakeGateway([result("1", 80)])
    ).execute(query="camera")

    assert len(response.top(1)) == 1

    with pytest.raises(ValueError):
        response.top(0)


def test_use_case_validates_threshold_and_result_limit():
    with pytest.raises(ValueError):
        DiscoverOpportunitiesUseCase(
            gateway=FakeGateway([]),
            strong_score_threshold=101,
        )

    use_case = DiscoverOpportunitiesUseCase(gateway=FakeGateway([]))

    with pytest.raises(ValueError):
        use_case.execute(query="camera", result_limit=0)


def test_use_case_propagates_gateway_failure():
    use_case = DiscoverOpportunitiesUseCase(gateway=FailingGateway())

    with pytest.raises(RuntimeError, match="gateway failed"):
        use_case.execute(query="camera")


def test_orchestrator_gateway_maps_existing_engine_result():
    source_product = product("1")
    recommendation = SimpleNamespace(
        grade="BUY",
        action="매입 추천",
        summary="좋은 기회입니다.",
        success_probability=78,
    )
    opportunity = SimpleNamespace(
        product=source_product,
        final_opportunity_score=82.5,
        matched_product_count=3,
        ai_recommendation=recommendation,
        analysis={"roi": 25.0},
        confidence=SimpleNamespace(confidence_score=90),
    )
    calls: list[tuple[str, int]] = []

    def finder(*, query: str, limit: int):
        calls.append((query, limit))
        return [opportunity]

    gateway = OrchestratorOpportunityDiscoveryGateway(finder=finder)
    mapped = gateway.discover(query="iphone", limit=20)

    assert calls == [("iphone", 20)]
    assert len(mapped) == 1
    assert mapped[0].product is source_product
    assert mapped[0].opportunity_score == 82.5
    assert mapped[0].matched_product_count == 3
    assert mapped[0].recommendation_grade == "BUY"
    assert mapped[0].metadata["analysis"] == {"roi": 25.0}
    assert mapped[0].metadata["confidence_score"] == 90
    assert mapped[0].metadata["success_probability"] == 78


def test_orchestrator_gateway_supports_missing_optional_analysis():
    opportunity = SimpleNamespace(
        product=product("1"),
        final_opportunity_score=40.0,
        matched_product_count=1,
        ai_recommendation=None,
        analysis={},
        confidence=None,
    )
    gateway = OrchestratorOpportunityDiscoveryGateway(
        finder=lambda **_: [opportunity]
    )

    mapped = gateway.discover(query="test", limit=1)[0]

    assert mapped.recommendation_grade is None
    assert mapped.metadata["confidence_score"] is None
    assert mapped.metadata["success_probability"] is None
