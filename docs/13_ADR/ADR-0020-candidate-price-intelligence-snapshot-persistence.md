# ADR-0020: Candidate PriceIntelligence Snapshot Persistence

## Status

Accepted

## Decision

The Price Analyzer owns Candidate-scoped `PriceIntelligenceSnapshot` v2 facts.
SQLite persists the supplied Snapshot without invoking grouping, Analyzer,
fallback calculation, or Product Snapshot creation. Runtime `PriceIntelligence`
objects are never stored.

Each save uses `BEGIN IMMEDIATE` and validates authoritative Candidate/Context
plus every ordered Product Observation Snapshot through the existing Product
Snapshot reconstitution boundary. Every Product source must exist, pass its own
fingerprint/version checks, and have the exact Candidate and Market identity of
the Price Snapshot. Ordered cohort identity and Decimal result values are
preserved exactly.

Snapshot ID is the replay key. Same ID and payload replay; changed payload
conflicts. Different IDs for the same cohort are permitted because they may be
separate Analyzer facts. The payload fingerprint detects corruption and is not a
UNIQUE business key. History is append-only and has no current projection.

Analyzer owner wiring, Economics persistence, Production Safety execution,
handoff persistence, migration, and backfill remain deferred.
