# ADR-0013: Discovery Observation and Finalized Group Persistence

## Status

Accepted

## Implementation Status

Implemented and production-wired through the authoritative `app.web` Discovery
entry. Observations persist at the collection checkpoint and finalized Groups
persist at the grouping checkpoint, before downstream transient analysis. The
`Deferred Work` section below preserves this ADR's original PR scope and is
superseded for execution-result persistence and production wiring by later
implementation.

## Context

ADR-0012 makes Discovery command identity durable. Candidate issuance still
cannot rely on a live Collector result or runtime ProductGroup because the exact
collected facts and finalized ordered membership disappear after restart.

## Decision

Persist `CollectedProductObservation` and `FinalizedProductGroup` as immutable,
append-only SQLite facts bound to an already committed command execution.
Neither repository invokes Collector, grouping, Snapshot creation, Candidate
issuance, or downstream analysis.

An observation stores the complete `ObservedProductSnapshot`, exact
`CollectorProvenance`, observation time, schema version, and optional explicitly
supplied Candidate Market identity. Observation ID is authoritative identity.
Source marketplace/item is a lookup key, not identity or a unique constraint,
because one listing may be observed repeatedly at different times or provenance.

## Ordered Group Membership

Finalized group history stores its ordered observation IDs and Domain membership
fingerprint. A normalized member table also stores `(group ID, position,
observation ID)` so SQLite foreign keys enforce member existence and reads can
verify contiguous order against the immutable JSON representation.

Membership is unique within one group only. The existing Domain permits lookup
of multiple groups by membership fingerprint and does not define exclusive
ownership of an observation. Therefore:

- an observation may participate in multiple groups;
- the same membership fingerprint may belong to distinct opaque group IDs; and
- neither observation ID nor membership fingerprint receives an invented global
  grouping rule.

Every member and representative must exist in the group's command execution.

## Atomicity and Replay

Observation save uses `BEGIN IMMEDIATE`, validates the committed execution,
inserts one history fact, and commits. Group save validates execution and all
members, inserts group history and every ordered member, then commits. Failure at
history, membership, or commit rolls back the complete new fact while preserving
previous facts.

The same ID and exact value replays without insertion. Reusing an ID with changed
content conflicts. Separate SQLite connections provide concurrency control; no
process-local lock or silent retry is introduced.

## No Current Projection or Legacy Conversion

Observations and finalized groups do not evolve, so no current projection is
created. UPDATE and DELETE triggers protect every authoritative table. Existing
runtime Products, price history, search results, and ProductGroups are not
converted, inferred, seeded, migrated, or backfilled.

## Relationship to ADR-0057

ADR-0057 preserves this observation as the Candidate-handoff persistence owner.
For new Candidate-eligible production observations, the existing optional
Candidate Market identity is accompanied by an immutable dedicated Candidate
discovery reference and handoff policy name/version under an all-or-none
invariant. Historical observations remain unchanged and optionality is retained
for unsupported or non-Candidate-eligible Discovery observations. No historical
identity or reference is inferred or backfilled.

CR-1B7B1 implements this evolution as `collector-observation-v2`. The existing
append-only JSON history stores the complete handoff on new eligible rows while
the v1 serializer and reconstruction contract remain exact and unchanged.

## Deferred Work

DiscoveryExecutionResult and zero-result completion persistence, Candidate ID
issuance and receipts, Snapshot ownership wiring, production Collector and
orchestrator wiring, Safety, Decision, Dashboard, HTTP, and UI remain out of
scope.
