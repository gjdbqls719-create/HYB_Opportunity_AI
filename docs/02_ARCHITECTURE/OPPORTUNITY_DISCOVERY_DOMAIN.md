# Opportunity Discovery Domain

## Status

- Introduced: Sprint 4.1.0
- Package: `app/domain/discovery`
- Strategy: additive; existing engines remain unchanged

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

Create an application adapter that converts the existing orchestrator output to
`DiscoveryResult`, then expose a single discovery use case for CLI integration.
