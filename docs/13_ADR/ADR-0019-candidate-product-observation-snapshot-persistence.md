# ADR-0019: Candidate Product Observation Snapshot Persistence

## Status

Accepted

## Decision

`ProductObservationSnapshot` v2 is persisted as an immutable Candidate-scoped
fact in `product_observation_snapshot_history`. The Marketplace Collection
boundary remains its owner, but production owner wiring is deferred. The
repository only stores caller-supplied Domain snapshots and never calls a
Collector or constructs Candidate identity.

Every save uses `BEGIN IMMEDIATE`, checks snapshot-ID replay, then validates the
persisted Candidate and Context. Candidate identity and discovery reference must
match exactly; complete Market identity must equal Context; Product marketplace
and listing item must match that identity. Promotion is not required because the
fact is legitimately pre-admission.

Snapshot ID is the replay key. Same ID and complete payload replay exactly; a
changed payload conflicts. A different ID with identical Product/provenance is
allowed as another observation because no existing Domain contract defines
source-provenance uniqueness. The canonical fingerprint detects corruption but
is deliberately not UNIQUE.

History has no current projection. UPDATE and DELETE are blocked. Multiple
snapshots per Candidate are ordered by observation time and opaque Snapshot ID.
Discovery Observation IDs are not reused, and no Product, Candidate, Snapshot,
or source reference is inferred or backfilled. Price/Economics persistence,
owner wiring, handoff persistence, Safety, API, and UI remain later work.
