# Opportunity Discovery Workflow

## Status

- Version: Sprint 4.3.0
- Layer: Application
- Test baseline: 524 tests

## Purpose

The Workflow layer coordinates repeatable application execution without moving
business calculations out of the existing Domain and Engine layers.

The first workflow intentionally models only stages that exist in the current
codebase:

```text
Discover -> Publish (optional)
```

Collection, normalization, matching, and analysis are still encapsulated by the
current discovery gateway. They will become separate workflow stages only after
their contracts are explicitly extracted. This avoids documenting or coding a
pipeline that does not yet exist.

## Dependency Direction

```text
Presentation / Scheduler
        |
        v
DiscoverOpportunitiesWorkflow
        |
        +--> DiscoverOpportunitiesUseCase
        |
        +--> OpportunityPublisher (optional port)
        |
        v
WorkflowRunner
```

The Workflow layer belongs to Application. It does not calculate prices,
opportunity scores, confidence, or recommendations.

## Runtime Components

### WorkflowRunner

- Executes ordered synchronous steps.
- Uses fail-fast semantics.
- Records completed steps and the failed step.
- Emits lifecycle events.
- Keeps observer failures isolated from the business workflow.

### WorkflowContext

- Shares explicit data between steps.
- Rejects blank keys.
- Provides immutable snapshots for diagnostics.

### Workflow Events

- `workflow_started`
- `step_started`
- `step_completed`
- `step_failed`
- `workflow_completed`
- `workflow_failed`

Observers can later connect logging, metrics, AI memory, and monitoring without
changing the workflow steps.

### DiscoverOpportunitiesWorkflow

- Runs the existing discovery use case.
- Stores the use-case response in workflow context.
- Optionally publishes the response through `OpportunityPublisher`.
- Returns both the discovery response and workflow execution record.

## Failure Policy

A failed step stops the workflow immediately. `WorkflowExecutionError` contains
a `WorkflowRun` with:

- completed steps,
- failed step,
- error message,
- timestamps,
- observer errors.

Publishing is intentionally part of the same fail-fast workflow for now. A
future durable outbox or retry queue should be introduced before notification
retries are required in production.

## Future Evolution

The next safe expansions are:

1. Infrastructure publishers for CLI, database, or notification channels.
2. Durable workflow execution storage.
3. Retry policy for infrastructure-only steps.
4. Extraction of Collect, Normalize, Match, and Analyze contracts from the
   current gateway.
5. Scheduler integration using the same application workflow entry point.
