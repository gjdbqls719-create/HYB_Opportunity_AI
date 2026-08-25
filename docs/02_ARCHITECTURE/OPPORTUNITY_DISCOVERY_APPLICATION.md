# Opportunity Discovery Application Layer

## Status

- Introduced: Sprint 4.2.0
- Legacy use case: Implemented and retained
- Authoritative production entry: Implemented separately through
  `PersistedDiscoveryExecutionEntry`

## Current Production Boundary

`DiscoverOpportunitiesUseCase` remains the legacy transient use case described
below. The authoritative FastAPI composition does not replace it; it separately
composes `PersistedDiscoveryExecutionEntry` with SQLite command, observation,
finalized-Group, and execution-result repositories.

That production entry persists collection and grouping checkpoints before
committing one `DiscoveryExecutionResult`. The runtime's economics, ranking,
and recommendation output remains transient. The persisted result retains the
ordered finalized Group IDs, not the complete ranked result payload. Candidate
issuance is a later explicit API and is not automatically chained to completion.

## Purpose

The Application Layer exposes one stable use case for every presentation channel:

```python
DiscoverOpportunitiesUseCase.execute(...)
```

CLI, API, scheduler, dashboard, and future agents should call this use case instead of importing engine modules directly.

## Dependency Direction

```text
Presentation
    -> Application Use Case
        -> Application Port
            <- Infrastructure Gateway
                -> Existing Engine Orchestrator
        -> Discovery Domain Ranking
```

The Application Layer does not import `engine.orchestrator`. It depends only on `OpportunityDiscoveryGateway`.

## Components

### DiscoverOpportunitiesUseCase

Responsibilities:

- validate execution input;
- create and finish a discovery session;
- invoke the discovery gateway;
- apply domain ranking and result limits;
- return results and operational statistics.

It does not calculate prices, profits, confidence, or recommendations.

### OpportunityDiscoveryGateway

Application Port defining the minimum discovery contract:

```text
discover(query, limit) -> DiscoveryResult list
```

This makes the use case independent from eBay, Amazon, the current orchestrator, and future asynchronous collectors.

### OrchestratorOpportunityDiscoveryGateway

Transitional Infrastructure Adapter that:

- invokes the existing `find_best_opportunities` flow;
- converts `OpportunityResult` into the domain `DiscoveryResult`;
- preserves recommendation and explainability metadata.

This adapter lets HYB adopt the new architecture without rewriting stable engines.

### DiscoverySession

Tracks one execution:

- unique session ID;
- query and requested collection limit;
- running, completed, or failed state;
- start and finish timestamps;
- terminal error message.

A session can finish only once.

### DiscoveryStatistics

Reports:

- discovered candidate count;
- returned candidate count;
- strong opportunity count based on a configurable threshold.

## Transitional Decision

The current engine orchestrator already performs collection, grouping, analysis, recommendation, and historical enrichment. Sprint 4.2 connects it through an Infrastructure Gateway instead of duplicating that logic.

Later sprints may replace the gateway internals with collectors, queues, workers, or marketplace-specific implementations without changing the Application Use Case or presentation clients.

## Non-goals

Sprint 4.2 does not:

- rewrite existing engines;
- change marketplace collectors;
- introduce asynchronous processing;
- persist sessions;
- add CLI or API entry points;
- implement notifications.

## Next Step

This section records the next step at Sprint 4.2.0. It is historical: later
increments added both CLI integration and the separate authoritative persisted
production entry described above.

Create a composition root or presentation entry point that wires:

```python
OrchestratorOpportunityDiscoveryGateway
    -> DiscoverOpportunitiesUseCase
```

Then expose the use case through CLI first, while retaining existing CLI compatibility.
