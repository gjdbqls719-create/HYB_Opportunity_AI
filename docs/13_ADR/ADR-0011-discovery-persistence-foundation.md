# ADR-0011: Discovery Persistence Foundation

## Status

Accepted as an Application boundary

## Implementation Status

The infrastructure deferral below records this ADR's original scope. Subsequent
ADR-0012 through ADR-0014 implement append-only SQLite command/receipt,
observation/Group, and execution-result repositories. ADR-0029 and later
production completion PRs wire those repositories through the authoritative
`app.web` Discovery composition.

The current persisted execution result stores ordered finalized Group IDs, not
the full transient ranked opportunity payload. Incomplete executions still have
no durable phase/attempt/failure/resume contract.

## Context

ADR-0010 defines immutable Discovery commands, collector observations, finalized
groups, command results, and Candidate issuance replay keys. PR34-B Candidate
issuance requires those facts to become durable, but choosing SQLite tables and
transaction ownership before the Application contracts would couple replay
semantics to infrastructure details.

## Decision

Introduce three repository boundaries:

- `DiscoveryCommandRepository` saves and queries commands and validates replay;
- `DiscoveryGroupRepository` saves and queries finalized groups by ID,
  execution, or membership fingerprint; and
- `DiscoveryResultRepository` saves and queries command-level execution results.

No repository implementation is selected in this PR.

`DiscoveryCommandReceipt` is an immutable acknowledgment containing command ID,
execution ID, the canonical command payload fingerprint, committed time, and a
fixed receipt schema version. The receipt does not contain Candidate or
Opportunity identity and does not claim collection or grouping has completed.

## Replay and Conflict

The Application service first asks the repository to validate the command ID and
canonical fingerprint.

- Same command ID and fingerprint returns the exact committed command and
  receipt without generating a new timestamp.
- Same command ID and a different fingerprint is
  `DiscoveryReplayConflict`.
- A different command ID is a new discovery execution even if user intent is
  otherwise similar.
- A receipt without its committed command is `MissingDiscoveryCommand` rather
  than a reconstructed or defaulted command.

The first save creates commit time using an injected clock and requires the
repository to return the unchanged immutable receipt. Repository failures are
reported as `DiscoveryPersistenceError`; malformed and unsupported receipt
contracts remain distinguishable.

## Persistence Ownership

The Discovery Application boundary owns command and receipt semantics.
Infrastructure will later own atomic durable storage. Collector adapters,
grouping, Economics, Safety, Candidate issuance, Snapshot owners, Opportunity
lifecycle, and presentation layers cannot create or reinterpret receipts.

## Separation from Candidate Issuance

Persisting a Discovery command does not issue a Candidate ID, create a Candidate
context, finalize a ProductGroup, create an Opportunity, or admit a lifecycle.
Candidate issuance remains a later command keyed by the committed command and
finalized group contracts.

## Why SQLite Is Deferred

The command/group/result Protocols must be reviewable before table shape,
append-only triggers, `BEGIN IMMEDIATE`, failure taxonomy, and multi-connection
concurrency are fixed. The next infrastructure PR must implement these contracts
without changing replay meaning. This PR therefore adds no tables, migrations,
triggers, receipts table, seed, or backfill.

## Consequences

- Replay semantics are testable without persistence technology.
- Clock and repository effects are explicit and replaceable.
- Infrastructure can later provide atomicity without owning business meaning.
- Durable replay is not yet available in production.

## Out of Scope

- SQLite repositories, tables, triggers, migrations, or transactions
- Collector, grouping, or orchestrator changes
- Candidate ID issuance and admission promotion
- Product/Price/Economics Snapshot persistence or owner wiring
- Safety, Decision, Dashboard, API, or UI changes
