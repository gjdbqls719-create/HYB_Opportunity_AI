# ADR-0026: Production Safety Operational Evaluation and Provenance

## Status

Accepted (PR36-A)

## Decision

Operational Production Safety evaluates an explicitly selected complete Snapshot
Chain binding and an explicit Product Snapshot member. It reconstructs disposable
runtime Product, PriceIntelligence, EconomicsCalculation, and analysis values
through the existing adapter and calls only the existing
`assess_production_safety()` engine. No source is selected by latest order and no
Safety status, missing field, failed check, threshold, or formula is duplicated.

The admission-time `production_safety_snapshots` table remains an immutable legacy
admission outcome with one row per Opportunity. Operational results are separate:
append-only evaluation history is authoritative, append-only provenance records
the exact chain/Product/Price/Economics/Verified sources, receipts provide command
replay, and a controlled current projection selects the most recently committed
explicit operational evaluation for Decision Readiness.

An Opportunity can have multiple operational evaluations. The same chain,
selected Product, and rule version is one authoritative evaluation; another
command receives an alias receipt. A different chain or selected Product appends
a new version and advances current atomically. Same-command replay returns the
persisted facts without runtime reconstruction, engine execution, ID generation,
or clock calls.

Decision Readiness uses operational current when an operational repository is
wired. Legacy admission outcomes are neither converted nor preferred and receive
no migration or backfill. API/UI execution, ProductionSafetySnapshot replacement,
Decision policy changes, and production orchestration remain deferred.

PR36-B designates validated operational current as the production Decision source.
Finalized compositions preserve its exact evaluation ID, while Dashboard reads
that immutable evaluation rather than a later current projection.
