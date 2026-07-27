from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.discovery.discover_opportunities import (
    DiscoverOpportunitiesResponse,
    DiscoverOpportunitiesUseCase,
)
from app.application.opportunity_intelligence import (
    OpportunityIntelligenceResult,
    OpportunityIntelligenceService,
    OpportunityIntelligenceStatus,
)
from app.application.workflow import (
    WorkflowContext,
    WorkflowObserver,
    WorkflowRun,
    WorkflowRunner,
)


class OpportunityPublisher(Protocol):
    """Discovery 결과를 외부 채널에 전달하는 Application Port."""

    def publish(self, response: DiscoverOpportunitiesResponse) -> None:
        ...


@dataclass(slots=True, frozen=True)
class DiscoverOpportunitiesWorkflowResponse:
    discovery: DiscoverOpportunitiesResponse
    workflow_run: WorkflowRun
    intelligence_results: tuple[OpportunityIntelligenceResult, ...] = ()


@dataclass(slots=True)
class _DiscoverStep:
    use_case: DiscoverOpportunitiesUseCase
    query: str
    collection_limit: int
    result_limit: int | None

    @property
    def name(self) -> str:
        return "discover"

    def execute(self, context: WorkflowContext) -> None:
        response = self.use_case.execute(
            query=self.query,
            collection_limit=self.collection_limit,
            result_limit=self.result_limit,
        )
        context.set("discovery_response", response)


@dataclass(slots=True)
class _OpportunityIntelligenceStep:
    service: OpportunityIntelligenceService

    @property
    def name(self) -> str:
        return "opportunity_intelligence"

    def execute(self, context: WorkflowContext) -> None:
        discovery_response = context.require("discovery_response")
        results: list[OpportunityIntelligenceResult] = []

        for discovery_result in discovery_response.results:
            try:
                intelligence_result = self.service.evaluate(discovery_result)
            except Exception as error:  # 마지막 격리 경계: Discovery 성공을 보존한다.
                intelligence_result = OpportunityIntelligenceResult(
                    status=OpportunityIntelligenceStatus.FAILED,
                    error_message=(
                        "Opportunity Intelligence 실행 중 예기치 않은 오류가 "
                        f"발생했습니다: {error}"
                    ),
                )
            results.append(intelligence_result)

        context.set("intelligence_results", tuple(results))


@dataclass(slots=True)
class _PublishStep:
    publisher: OpportunityPublisher

    @property
    def name(self) -> str:
        return "publish"

    def execute(self, context: WorkflowContext) -> None:
        response = context.require("discovery_response")
        self.publisher.publish(response)


class DiscoverOpportunitiesWorkflow:
    """Opportunity 탐색, 선택적 Intelligence 평가와 결과 발행을 조정한다."""

    def __init__(
        self,
        *,
        use_case: DiscoverOpportunitiesUseCase,
        intelligence_service: OpportunityIntelligenceService | None = None,
        publisher: OpportunityPublisher | None = None,
        observers: tuple[WorkflowObserver, ...] = (),
    ) -> None:
        self._use_case = use_case
        self._intelligence_service = intelligence_service
        self._publisher = publisher
        self._observers = observers

    def execute(
        self,
        *,
        query: str,
        collection_limit: int = 10,
        result_limit: int | None = None,
    ) -> DiscoverOpportunitiesWorkflowResponse:
        context = WorkflowContext()
        steps = [
            _DiscoverStep(
                use_case=self._use_case,
                query=query,
                collection_limit=collection_limit,
                result_limit=result_limit,
            )
        ]

        if self._intelligence_service is not None:
            steps.append(
                _OpportunityIntelligenceStep(
                    service=self._intelligence_service,
                )
            )

        if self._publisher is not None:
            steps.append(_PublishStep(publisher=self._publisher))

        workflow_run = WorkflowRunner(
            workflow_name="discover_opportunities",
            steps=steps,
            observers=self._observers,
        ).run(context)

        return DiscoverOpportunitiesWorkflowResponse(
            discovery=context.require("discovery_response"),
            workflow_run=workflow_run,
            intelligence_results=context.get("intelligence_results", ()),
        )
