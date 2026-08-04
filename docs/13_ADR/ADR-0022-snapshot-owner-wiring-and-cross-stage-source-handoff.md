# ADR-0022: Snapshot Owner Wiring and Cross-Stage Source Handoff

## Status

Accepted incrementally (PR35-E1)

## Decision

Collector observations are committed before grouping and Candidate issuance, so
a Candidate-scoped Product Snapshot cannot be created during original collection.
After issuance, a collector-owned capture boundary reads the exact finalized
group and ordered persisted observations, copies Product/provenance/timestamps
without inference, and atomically writes Product Snapshots, immutable source
bindings, and a command receipt. Downstream layers do not create these facts.

Product Snapshot v2 remains unchanged. The exact observation reference is an
additive `ProductSnapshotSourceBinding`, avoiding a false migration or backfill.
One `(candidate_id, collected_observation_id)` has one published Product Snapshot.
Another command may add an alias receipt only for the same exact Snapshot IDs.

Same command/fingerprint replays committed facts; changed payload conflicts.
`BEGIN IMMEDIATE` covers Snapshots, bindings, and receipt. No latest lookup or
field matching is used.

## Scope split

PR35-E1 implements Product source ownership only. Price Analyzer owner wiring,
Economics explicit Price handoff, complete Snapshot Chain binding, and Production
Safety source loading remain PR35-E2-E4 work.
