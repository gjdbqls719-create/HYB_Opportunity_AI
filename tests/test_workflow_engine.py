from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.application.discovery import (
    DiscoverOpportunitiesUseCase,
    DiscoverOpportunitiesWorkflow,
)
from app.application.workflow import (
    WorkflowContext,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowStatus,
)
from app.domain.discovery import DiscoveryResult
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


@dataclass
class SetValueStep:
    step_name: str
    key: str
    value: object

    @property
    def name(self) -> str:
        return self.step_name

    def execute(self, context: WorkflowContext) -> None:
        context.set(self.key, self.value)


@dataclass
class FailingStep:
    step_name: str = "fail"

    @property
    def name(self) -> str:
        return self.step_name

    def execute(self, context: WorkflowContext) -> None:
        raise RuntimeError("step failed")


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[WorkflowEvent] = []

    def on_event(self, event: WorkflowEvent) -> None:
        self.events.append(event)


class BrokenObserver:
    def on_event(self, event: WorkflowEvent) -> None:
        raise RuntimeError("observer failed")


class FakeGateway:
    def __init__(self, results: list[DiscoveryResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def discover(self, *, query: str, limit: int) -> list[DiscoveryResult]:
        self.calls.append((query, limit))
        return list(self.results)


class RecordingPublisher:
    def __init__(self) -> None:
        self.responses = []

    def publish(self, response) -> None:
        self.responses.append(response)


def clock_sequence(*values: datetime):
    iterator = iter(values)
    return lambda: next(iterator)


def test_workflow_context_validates_and_protects_snapshot():
    context = WorkflowContext()
    context.set("answer", 42)

    assert context.require("answer") == 42
    assert context.get("missing", "fallback") == "fallback"

    with pytest.raises(ValueError):
        context.set(" ", 1)

    with pytest.raises(KeyError):
        context.require("missing")

    with pytest.raises(TypeError):
        context.snapshot()["new"] = "value"


def test_workflow_runner_executes_steps_and_emits_lifecycle_events():
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    observer = RecordingObserver()
    context = WorkflowContext()
    runner = WorkflowRunner(
        workflow_name="sample",
        steps=[
            SetValueStep("first", "a", 1),
            SetValueStep("second", "b", 2),
        ],
        observers=[observer],
        clock=clock_sequence(
            started,
            started + timedelta(seconds=1),
            started + timedelta(seconds=2),
            started + timedelta(seconds=3),
            started + timedelta(seconds=4),
            started + timedelta(seconds=5),
        ),
    )

    run = runner.run(context)

    assert run.status is WorkflowStatus.COMPLETED
    assert run.completed_steps == ("first", "second")
    assert run.duration_seconds == 5.0
    assert context.require("a") == 1
    assert context.require("b") == 2
    assert [event.event_type for event in observer.events] == [
        WorkflowEventType.WORKFLOW_STARTED,
        WorkflowEventType.STEP_STARTED,
        WorkflowEventType.STEP_COMPLETED,
        WorkflowEventType.STEP_STARTED,
        WorkflowEventType.STEP_COMPLETED,
        WorkflowEventType.WORKFLOW_COMPLETED,
    ]


def test_workflow_runner_rejects_invalid_definition():
    with pytest.raises(ValueError):
        WorkflowRunner(workflow_name=" ", steps=[SetValueStep("a", "a", 1)])

    with pytest.raises(ValueError):
        WorkflowRunner(workflow_name="sample", steps=[])

    with pytest.raises(ValueError):
        WorkflowRunner(
            workflow_name="sample",
            steps=[SetValueStep("same", "a", 1), SetValueStep("same", "b", 2)],
        )


def test_workflow_runner_fails_fast_and_exposes_partial_run():
    started = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    observer = RecordingObserver()
    runner = WorkflowRunner(
        workflow_name="sample",
        steps=[SetValueStep("first", "a", 1), FailingStep()],
        observers=[observer],
        clock=clock_sequence(
            started,
            started + timedelta(seconds=1),
            started + timedelta(seconds=2),
            started + timedelta(seconds=3),
            started + timedelta(seconds=4),
            started + timedelta(seconds=5),
        ),
    )

    with pytest.raises(WorkflowExecutionError) as captured:
        runner.run()

    run = captured.value.run
    assert run.status is WorkflowStatus.FAILED
    assert run.completed_steps == ("first",)
    assert run.failed_step == "fail"
    assert run.error_message == "step failed"
    assert observer.events[-1].event_type is WorkflowEventType.WORKFLOW_FAILED


def test_observer_failure_is_recorded_without_breaking_workflow():
    runner = WorkflowRunner(
        workflow_name="sample",
        steps=[SetValueStep("first", "a", 1)],
        observers=[BrokenObserver()],
    )

    run = runner.run()

    assert run.status is WorkflowStatus.COMPLETED
    assert run.observer_errors
    assert all("BrokenObserver" in item for item in run.observer_errors)


def test_discovery_workflow_runs_use_case_and_optional_publisher():
    gateway = FakeGateway([result("low", 30), result("high", 90)])
    publisher = RecordingPublisher()
    observer = RecordingObserver()
    workflow = DiscoverOpportunitiesWorkflow(
        use_case=DiscoverOpportunitiesUseCase(gateway=gateway),
        publisher=publisher,
        observers=(observer,),
    )

    response = workflow.execute(
        query="  iphone  ",
        collection_limit=20,
        result_limit=1,
    )

    assert gateway.calls == [("iphone", 20)]
    assert len(response.discovery.results) == 1
    assert response.discovery.results[0].product.item_id == "high"
    assert publisher.responses == [response.discovery]
    assert response.workflow_run.status is WorkflowStatus.COMPLETED
    assert response.workflow_run.completed_steps == ("discover", "publish")


def test_discovery_workflow_can_run_without_publisher():
    gateway = FakeGateway([result("1", 70)])
    workflow = DiscoverOpportunitiesWorkflow(
        use_case=DiscoverOpportunitiesUseCase(gateway=gateway)
    )

    response = workflow.execute(query="camera")

    assert response.workflow_run.completed_steps == ("discover",)
    assert len(response.discovery.results) == 1
