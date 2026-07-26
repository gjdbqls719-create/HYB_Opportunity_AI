from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.discovery.discover_opportunities import (
    DiscoverOpportunitiesResponse,
    DiscoverOpportunitiesUseCase,
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
class _PublishStep:
    publisher: OpportunityPublisher

    @property
    def name(self) -> str:
        return "publish"

    def execute(self, context: WorkflowContext) -> None:
        response = context.require("discovery_response")
        self.publisher.publish(response)


class DiscoverOpportunitiesWorkflow:
    """Opportunity 탐색과 선택적 결과 발행을 조정하는 Workflow."""

    def __init__(
        self,
        *,
        use_case: DiscoverOpportunitiesUseCase,
        publisher: OpportunityPublisher | None = None,
        observers: tuple[WorkflowObserver, ...] = (),
    ) -> None:
        self._use_case = use_case
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
        )
