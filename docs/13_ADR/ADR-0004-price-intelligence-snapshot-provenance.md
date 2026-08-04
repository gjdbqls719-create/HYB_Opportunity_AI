# ADR-0004: PriceIntelligence Snapshot Provenance

## Status

Accepted

## Context

The existing analyzer receives the Product cohort produced by grouping and an
explicit fallback multiplier. It returns an in-memory frozen `PriceIntelligence`
containing currency, price statistics, stability, recommended price, and sample
size. No authoritative repository preserves that result or the exact Product
observations that produced it.

Price history cannot identify the ordered grouped cohort used by one analyzer
execution. Product Observation snapshots provide authoritative source facts but
must not be selected or reconstructed downstream by inference.

## Decision

The Price Intelligence Analyzer owns creation of `PriceIntelligenceSnapshot`.
The snapshot copies every current analyzer output into immutable scalar fields
and adds:

- snapshot, Opportunity, and Market Observation identities;
- ordered Product Observation snapshot IDs;
- analyzer version;
- timezone-aware generation time; and
- snapshot schema version.

The runtime `PriceIntelligence` object is not stored inside the snapshot. Its
runtime class is an execution result without source identities, analyzer version,
or durable ownership, and coupling persistence to that class would allow future
runtime changes to alter the persistence contract implicitly.

Ordered Product Observation IDs preserve the exact cohort and ordering supplied
to the analyzer. Sample size must equal that source count because Safety and
confidence paths distinguish single-observation fallback from multi-observation
analysis. Analyzer version is required so identical source observations can be
interpreted against the exact analyzer semantics that produced the stored result.

The Application repository boundary supports save, direct lookup, Opportunity
lookup, and Market Observation identity lookup. No persistence technology is
selected in this decision.

Collectors, Validation Admission, Review, Production Safety, Dashboard, and
Decision do not create PriceIntelligence snapshots.

## Consequences

- Analyzer output and exact source provenance can be referenced immutably.
- Repeated or reordered Product source IDs remain distinguishable.
- Runtime analyzer and snapshot contracts can version independently.
- Durable persistence and analyzer integration remain future work.
- Existing observations are not migrated or backfilled.

## Out of Scope

- SQLite tables, transactions, migration, or backfill
- Existing analyzer, formula, grouping, fallback, or orchestrator changes
- Collector changes
- Economics or Production Safety snapshots
- Safety API/UI, Decision, Review, or Dashboard changes
