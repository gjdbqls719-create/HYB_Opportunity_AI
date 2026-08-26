# Opportunity Discovery Workflow

## Status

- Legacy workflow introduced: Sprint 4.3.0
- Production completion specification: Sprint 37
- Layer: Application

## Purpose

The Workflow layer coordinates repeatable application execution without moving
business calculations out of the existing Domain and Engine layers.

The first workflow intentionally models only stages that exist in the current
codebase:

```text
Discover -> Publish (optional)
```

Collection, normalization, matching, and analysis remain encapsulated by the
current discovery gateway for this legacy workflow. The persisted production
entry described below has explicit collection and grouping-correlation contracts
without changing the legacy workflow meaning.

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
4. Further extraction of Normalize, Match, and Analyze contracts from the
   current gateway when their boundaries are explicit.
5. Scheduler integration using the same application workflow entry point.

## Persisted Production Discovery Entry

The persisted production entry is a separate Application owner. It does not
change the existing `DiscoverOpportunitiesWorkflow`, whose meaning remains
transient Discover plus optional Intelligence and Publish coordination.

### Implemented in the Current HEAD

```text
DiscoveryCommand
    -> PersistDiscoveryCommand
    -> committed DiscoveryCommand
    -> ProductionDiscoveryRuntime
         -> CollectionFact*
         -> collection checkpoint
              -> CollectedProductObservation assembly/persistence
         -> GroupingCorrelation*
         -> grouping checkpoint
              -> FinalizedProductGroup assembly/persistence
              -> ordered finalized_group_id tuple returned to Engine
         -> transient economics/ranking/recommendation
              -> versioned score/recommendation/Safety/ranking descriptors
              -> raw/effective recommendation and structured reasons
              -> OpportunityResult.finalized_group_id survives sorting
         -> DiscoveryResult*
              -> exact finalized_group_id mapping
    -> runtime/command execution-ID correlation validation
    -> result/finalized-Group bijection validation
    -> DiscoveryExecutionResult assembly/persistence
    -> authoritative completion response
```

The runtime receives the committed command returned by
`PersistDiscoveryCommand`. On a completed exact replay, the Application loads
the persisted result, observations, and ordered Groups and does not call the
runtime. An incomplete command replay runs the runtime again. The runtime keeps
collection facts and grouping correlations in execution-local buffers and
returns immutable tuples with the transient Discovery results. The Application
entry rejects a runtime execution ID that differs from the committed command.

At the collection checkpoint, the Application requests one opaque observation
ID for each `CollectionFact`, copies the collected Product and collector facts
into a `CollectedProductObservation`, and persists each observation. At the
grouping checkpoint, it maps execution-local correlation positions to those
observations, requests authoritative Group IDs and times, and persists each
`FinalizedProductGroup` before downstream analysis. It returns the ordered
finalized Group IDs through the runtime callback, and the Engine binds each ID
to the corresponding `ProductGroup` before analysis. The ID remains attached to
the result while the existing three-key stable sort reorders results. After the
runtime and Application independently validate the exact result/Group
bijection, the Application persists one `DiscoveryExecutionResult`. The
production entry therefore establishes these durable facts:

- a persisted `DiscoveryCommand` and receipt;
- persisted `CollectedProductObservation` values;
- persisted `FinalizedProductGroup` values; and
- one persisted successful `DiscoveryExecutionResult`, including an explicit
  zero-result.

The internal Application response also carries transient `DiscoveryResult`
values and runtime facts on a fresh execution. The public production POST
returns only authoritative completion and finalized-Group facts. The durable
`DiscoveryExecutionResult` preserves ordered finalized Group IDs; it does not
preserve the ranked `OpportunityResult`/`DiscoveryResult` payload, economics,
score, or recommendation.

The Infrastructure runtime adapter maps all execution-affecting command values:
query, collection limit, matching threshold, pricing multiplier, cost and fee
inputs, fee-known evidence flags, profitability thresholds, sales and competition
inputs, risk level, and target currency. Policy and source references remain
durable audit metadata and are not Engine arguments.

### Screening Semantic Contracts

The authoritative production Engine result now carries one immutable
`ScreeningPolicyDescriptors` manifest containing exact v1 score,
recommendation, production-safety, and ranking descriptors. Each descriptor has
a semantic policy version and stable algorithm ID. A material algorithm or
ordered-rule change requires a new descriptor version; local Git working-tree
hashes are not durable policy identities. Build/revision evidence may be added
as separate execution provenance in PR4 without changing these policy meanings.

Ranking v1 describes the existing production sort only:

1. effective recommendation object score descending;
2. final opportunity score descending;
3. per-unit net profit descending; and
4. stable input order for complete equal-key ties.

`finalized_group_id`, grouping ordinal, and descriptors are not sort keys. The
different `app/domain/discovery/ranking.py::RankingEngine` remains outside this
production screening authority.

`ScreeningRecommendationSemantics` copies the raw grade/action/summary before
Safety and the effective values after Safety, while preserving the one numeric
recommendation score. `safety_intervention_occurred` is true only when Safety
changes the recommendation value; an unsafe existing non-BUY may gain safety
reasons without being counted as a recommendation intervention. BUY-family
downgrades retain the current WATCH behavior and unchanged score.

Structured reasons use the `discovery.screening.reason.v1` namespace. Codes are
created directly at the scoring/recommendation/Safety rule branch, never parsed
from display text. The original Korean or existing human message is retained,
order follows production rule order, identical duplicate codes collapse to the
first occurrence, and conflicting reuse of one code fails. Legacy arbitrary
text receives no inferred code.

The score descriptor identifies fixed command/profile inputs used in current
screening, including estimated monthly sales, competitor count, risk level,
profitability thresholds, and the fallback selling-price multiplier, as policy
assumption inputs. This does not implement PR4 provenance envelopes or label
any NAVER/ItemScout mixed-geography total as Korea-only demand evidence.

### Grouping Correlation Contract

`GroupingCorrelation` carries exactly:

- `ordered_member_collection_positions`; and
- `representative_collection_position`.

These positions are execution-local facts emitted by the Engine's grouping
calculation. They preserve ordered membership and representative selection so
the Application can map them to the observations persisted for the same
collection positions.

A grouping correlation is not an identity, a finalized Group ID, or a durable
Group. It does not authorize the Application to regroup Products or reinterpret
Engine matching. It carries facts from the Engine computation without carrying
new grouping meaning.

The separate screening correlation key is the existing
`finalized_group_id`. It is issued and persisted by the Application at the
grouping checkpoint, then returned in the same explicit grouping order before
analysis. The Engine copies that exact value into `OpportunityResult`; the
runtime copies it into `DiscoveryResult`. The value is not reconstructed from a
title, URL, marketplace item ID, sorted position, or grouping position after
the fact.

For this boundary, `finalized_group_id` is execution-local technical lineage:
it proves which finalized Group started one Engine analysis. It is not
Candidate, Opportunity, O1/O2, marketplace listing, or Capital identity. The
authoritative production path rejects missing, duplicate, unknown, count-
mismatched, and lost correlations. A zero-Group/zero-result execution remains
valid. Legacy transient Engine and gateway callers may omit the additive field,
but the production runtime may not silently accept it for a non-empty result.

### Current Production Limits

- The persisted completion result is a lineage/order record, not a durable
  ranked opportunity result.
- Exact result-to-finalized-Group correlation is now present in fresh transient
  production results, but it is not yet a persisted screening evaluation or
  ranking publication.
- Candidate issuance is not automatically composed after Discovery. A caller
  must read the finalized Groups, select one, and invoke the separate durable
  Candidate API.
- Checkpoint persistence does not create a durable workflow-attempt model.
  There is no persisted phase, attempt number, failure record, retry policy, or
  resume cursor for an incomplete execution.
- A later analysis failure can leave a committed command, observations, and
  Groups without a committed execution result. Those facts are durable history,
  but rerunning the command is not phase-aware resume.

### Authoritative Discovery Completion

The authoritative completion chain is:

```text
DiscoveryCommand
    -> CollectedProductObservation*
    -> FinalizedProductGroup*
    -> DiscoveryExecutionResult
```

Returning transient `DiscoveryResult` values does not complete Discovery.
Discovery is complete only when all of the following are true:

1. the command is persisted;
2. its collected observations are persisted;
3. its finalized Groups are persisted; and
4. one successful `DiscoveryExecutionResult`, including an authoritative
   zero-result when applicable, is persisted.

The `DiscoveryExecutionResult` commit is the Discovery exit boundary. Before
that commit, the execution must not be presented as a successfully completed
Discovery. An empty finalized Group tuple is successful only when explicitly
committed as the execution's zero-result; absence of Group rows alone does not
mean success.

### Responsibility Boundaries

- Collector owns raw collection facts and collector provenance.
- Engine owns grouping computation and the correlation facts emitted from that
  computation.
- Application owns orchestration, requests authoritative identity and clock
  values from their suppliers, maps execution-local correlation positions to
  persisted observations, and finalizes the workflow contracts.
- Repository owns durability, exact replay, changed-payload conflict behavior,
  and append-only storage. It does not create workflow meaning.
- Candidate workflow owns Candidate identity and receives explicit
  `discovery_reference` and LISTING or CANONICAL_PRODUCT Market identity. Those
  values are not inferred from Discovery Products, titles, queries, or Group
  identities.

### Candidate and Decision Boundary

Candidate issuance is the next workflow, not part of Discovery completion. It
may begin only after a completed `DiscoveryExecutionResult` exists and the
selected finalized Group plus representative observation lineage can be
validated from the repositories. It begins only through the explicit durable
Candidate API after caller/Founder selection. A successful zero-result cannot
issue a Candidate.

`DiscoveryResult` remains a transient ranking and presentation result. It is
not the authoritative source for Candidate issuance or Decision composition.
Decision does not consume live Discovery runtime output. It consumes persisted
lineage established through Candidate issuance, Opportunity promotion, Snapshot
owners, and a finalized Decision Composition.

### Failure and Replay Summary

- Command persistence failure prevents runtime execution.
- Runtime failure preserves the already committed command and any observation
  or Group checkpoints completed before the failure.
- Each observation save uses the existing individual repository transaction;
  the current entry does not wrap all observations in one transaction.
- An exact observation ID and payload replay returns the committed fact; reuse
  of that ID with changed content conflicts.
- A completed exact replay reconstructs persisted lineage without live runtime,
  identity-provider, or clock calls.
- An incomplete replay has no durable phase/attempt/resume contract and reruns
  the current runtime entry.
- An execution that has not committed its `DiscoveryExecutionResult` is not a
  successfully completed Discovery.

Detailed identity, persistence, atomicity, and Candidate rules remain in
ADR-0009, ADR-0010, ADR-0013, ADR-0014, ADR-0015, and ADR-0029 rather than being
duplicated here.
