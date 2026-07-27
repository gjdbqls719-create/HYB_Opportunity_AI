from __future__ import annotations

from app.application.discovery import (
    DiscoverOpportunitiesUseCase,
    DiscoverOpportunitiesWorkflow,
)
from app.application.opportunity_intelligence import (
    OpportunityIntelligenceResult,
    OpportunityIntelligenceStatus,
)
from app.application.workflow import WorkflowStatus
from app.domain.discovery import DiscoveryResult
from app.models import Product


def _result(item_id: str, score: float) -> DiscoveryResult:
    return DiscoveryResult(
        product=Product(
            marketplace="ebay",
            item_id=item_id,
            title=f"Product {item_id}",
            price=100.0,
            currency="USD",
        ),
        opportunity_score=score,
    )


class _FakeGateway:
    def __init__(self, results: list[DiscoveryResult]) -> None:
        self._results = results

    def discover(self, *, query: str, limit: int) -> list[DiscoveryResult]:
        return list(self._results)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.responses = []

    def publish(self, response) -> None:
        self.responses.append(response)


class _RecordingIntelligenceService:
    def __init__(self) -> None:
        self.calls: list[DiscoveryResult] = []

    def evaluate(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceResult:
        self.calls.append(discovery_result)
        return OpportunityIntelligenceResult(
            status=OpportunityIntelligenceStatus.UNAVAILABLE,
            missing_factors=("price_score",),
        )


class _PartiallyFailingIntelligenceService:
    def evaluate(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceResult:
        if discovery_result.product.item_id == "broken":
            raise RuntimeError("unexpected failure")

        return OpportunityIntelligenceResult(
            status=OpportunityIntelligenceStatus.UNAVAILABLE,
            missing_factors=("price_score",),
        )


def test_workflow_evaluates_each_ranked_discovery_result() -> None:
    service = _RecordingIntelligenceService()
    workflow = DiscoverOpportunitiesWorkflow(
        use_case=DiscoverOpportunitiesUseCase(
            gateway=_FakeGateway(
                [_result("low", 30), _result("high", 90)]
            )
        ),
        intelligence_service=service,
    )

    response = workflow.execute(query="iphone")

    assert service.calls == list(response.discovery.results)
    assert len(response.intelligence_results) == 2
    assert all(
        item.status is OpportunityIntelligenceStatus.UNAVAILABLE
        for item in response.intelligence_results
    )
    assert response.workflow_run.completed_steps == (
        "discover",
        "opportunity_intelligence",
    )


def test_workflow_isolates_unexpected_intelligence_failure_per_result() -> None:
    publisher = _RecordingPublisher()
    workflow = DiscoverOpportunitiesWorkflow(
        use_case=DiscoverOpportunitiesUseCase(
            gateway=_FakeGateway(
                [_result("broken", 90), _result("healthy", 70)]
            )
        ),
        intelligence_service=_PartiallyFailingIntelligenceService(),
        publisher=publisher,
    )

    response = workflow.execute(query="camera")

    assert response.workflow_run.status is WorkflowStatus.COMPLETED
    assert response.workflow_run.completed_steps == (
        "discover",
        "opportunity_intelligence",
        "publish",
    )
    assert publisher.responses == [response.discovery]
    assert (
        response.intelligence_results[0].status
        is OpportunityIntelligenceStatus.FAILED
    )
    assert "unexpected failure" in (
        response.intelligence_results[0].error_message or ""
    )
    assert (
        response.intelligence_results[1].status
        is OpportunityIntelligenceStatus.UNAVAILABLE
    )


def test_workflow_without_intelligence_preserves_existing_contract() -> None:
    workflow = DiscoverOpportunitiesWorkflow(
        use_case=DiscoverOpportunitiesUseCase(
            gateway=_FakeGateway([_result("1", 70)])
        )
    )

    response = workflow.execute(query="camera")

    assert response.intelligence_results == ()
    assert response.workflow_run.completed_steps == ("discover",)
