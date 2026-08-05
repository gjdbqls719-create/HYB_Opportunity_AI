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
         -> GroupingCorrelation*
         -> DiscoveryResult*
    -> runtime/command execution ID correlation validation
    -> ObservationIdentityProvider
    -> CollectedProductObservation assembly
    -> DiscoveryObservationRepository
    -> PersistedDiscoveryExecutionResult Application response
```

The runtime receives the committed command returned by
`PersistDiscoveryCommand`, including on command replay. The runtime keeps
collection facts and grouping correlations in execution-local buffers and
returns immutable tuples with the transient Discovery results. The Application
entry rejects a runtime execution ID that differs from the committed command.

For each returned `CollectionFact`, the Application requests one opaque
observation ID, copies the collected Product and collector facts into a
`CollectedProductObservation`, and saves that observation through the existing
repository. The current production entry therefore establishes these facts:

- a persisted `DiscoveryCommand` and receipt;
- persisted `CollectedProductObservation` values; and
- runtime-returned `GroupingCorrelation` values for the execution.

The Application response also returns `DiscoveryResult` values, collection
facts, observations, and grouping correlations. That response is not the
durable command-level completion record described below.

The Infrastructure runtime adapter maps all execution-affecting command values:
query, collection limit, matching threshold, pricing multiplier, cost and fee
inputs, fee-known evidence flags, profitability thresholds, sales and competition
inputs, risk level, and target currency. Policy and source references remain
durable audit metadata and are not Engine arguments.

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

### Existing Contracts Not Yet Production-Wired

The Domain and Repository contracts already define `FinalizedProductGroup` and
`DiscoveryExecutionResult`, including durable replay and conflict behavior.
The current production entry does not yet assemble or persist either value.

The following production responsibilities remain unwired:

- finalizing each `FinalizedProductGroup` immediately after grouping;
- supplying an authoritative finalized Group ID;
- supplying the authoritative grouping policy version;
- supplying the timezone-aware `finalized_at` value;
- persisting finalized Groups through `DiscoveryGroupRepository`;
- checkpointing Groups before downstream group analysis can fail;
- assembling a successful or authoritative zero-result
  `DiscoveryExecutionResult`;
- persisting that result through `DiscoveryResultRepository`; and
- composing the production Candidate entry after Discovery completion.

The Engine emits grouping correlations immediately after grouping, before Price
Intelligence and later group analysis. The current runtime stores them in a
local buffer and exposes them to the Application only after the complete Engine
call succeeds. Consequently, a downstream analysis failure prevents the
Application from receiving those correlations. The current production wiring
therefore does not yet satisfy the ADR-0010 timing requirement that an already
finalized Group survive downstream analysis failure.

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
validated from the repositories. A successful zero-result cannot issue a
Candidate.

`DiscoveryResult` remains a transient ranking and presentation result. It is
not the authoritative source for Candidate issuance or Decision composition.
Decision does not consume live Discovery runtime output. It consumes persisted
lineage established through Candidate issuance, Opportunity promotion, Snapshot
owners, and a finalized Decision Composition.

### Failure and Replay Summary

- Command persistence failure prevents runtime execution.
- Runtime failure preserves the already committed command.
- Each observation save uses the existing individual repository transaction;
  the current entry does not wrap all observations in one transaction.
- An exact observation ID and payload replay returns the committed fact; reuse
  of that ID with changed content conflicts.
- Finalized Group and execution-result production recovery are not yet wired.
- An execution that has not committed its `DiscoveryExecutionResult` is not a
  successfully completed Discovery.

Detailed identity, persistence, atomicity, and Candidate rules remain in
ADR-0009, ADR-0010, ADR-0013, ADR-0014, ADR-0015, and ADR-0029 rather than being
duplicated here.
