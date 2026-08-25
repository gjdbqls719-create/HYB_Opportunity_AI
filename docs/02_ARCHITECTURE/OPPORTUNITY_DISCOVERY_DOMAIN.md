# Opportunity Discovery Domain

## Status

- Introduced: Sprint 4.1.0
- Package: `app/domain/discovery`
- Strategy: additive; existing engines remain unchanged

## Current Production Relationship

`app.domain.discovery.DiscoveryResult` remains the transient normalized result
used by the legacy pipeline and production runtime response. It is distinct from
`app.domain.discovery_identity.DiscoveryExecutionResult`, the durable completion
fact that stores ordered finalized Group IDs. The current SQLite completion
contract does not persist the full ranked `DiscoveryResult` or Engine
`OpportunityResult` payload.

The authoritative production flow also uses immutable
`CollectedProductObservation` and `FinalizedProductGroup` contracts from
`app.domain.discovery_identity`. Candidate issuance remains a separate explicit
workflow after completion.

## Purpose

The Discovery Domain coordinates already-tested HYB components without owning
price, market, confidence, opportunity, or recommendation calculations.

```text
Collected Product
    -> OpportunityQueue
    -> DiscoveryAnalyzer adapter
    -> DiscoveryResult
    -> RankingEngine
    -> DiscoveryRun
```

## Dependency Direction

- `app/domain/discovery` may depend on the shared `Product` model.
- Existing engines do not depend on Discovery.
- Marketplace collectors do not depend on Discovery internals.
- Engine-specific result conversion belongs in a future adapter/application
  layer, not in the domain result model.

## Components

### DiscoveryResult

A stable output contract for UI, CLI, storage, and alerts. It intentionally
stores normalized recommendation fields rather than importing engine-specific
result classes.

### OpportunityQueue

A protocol plus an in-memory FIFO implementation. The current identity fallback
uses marketplace + item ID, URL, or normalized title. A canonical Strong
Identity resolver can be injected later without changing the pipeline.

### DiscoveryPipeline

Coordinates queueing, duplicate removal, analysis, failure isolation, and
ranking. The analyzer is injected as a callable so the existing orchestrator can
be connected through an adapter in the next increment.

### RankingEngine

Ranks by opportunity score first, then evidence count, lower acquisition cost,
and deterministic identity fields. Ranking does not recalculate business scores.

## Non-goals for Sprint 4.1.0

- No marketplace API calls
- No changes to existing engines
- No asynchronous or persistent queue
- No scheduler
- No final adapter from `engine.orchestrator.OpportunityResult`

## Next Increment

This is the historical next increment from Sprint 4.1.0. The adapter and
production compositions were implemented by later PRs; current wiring is
documented in `OPPORTUNITY_DISCOVERY_WORKFLOW.md`.

Create an application adapter that converts the existing orchestrator output to
`DiscoveryResult`, then expose a single discovery use case for CLI integration.
