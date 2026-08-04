# ADR-0003: Product Observation Snapshot Ownership

## Status

Accepted

## Context

Production Safety currently consumes a mutable runtime `Product`, an in-memory
`PriceIntelligence`, calculation facts, and Economics results. Its persisted
outcome does not preserve the Product source observed by a marketplace collector.

`price_history` is not a Product snapshot. It omits Product facts including data
source, shipping cost, whether shipping was known, rating, review count, and stock
state. Recreating a Product from price history, admission, Review, or Safety data
would require guessing omitted values. A mutable Product inside a frozen wrapper
would also remain indirectly mutable.

## Decision

The Marketplace Collection Boundary exclusively owns creation of
`ProductObservationSnapshot`. It contains an explicit snapshot ID, Opportunity
identity, Market Observation identity, immutable field-for-field Product copy,
collector-supplied provenance, timezone-aware observation time, and schema version.

Collector provenance is explicit. No downstream layer may infer it from titles,
URLs, marketplace values, IDs, admission records, Review artifacts, or Safety
outcomes.

The Application repository boundary supports save, direct lookup, Opportunity
lookup, and Market Observation identity lookup. This ADR does not select a
persistence technology or add a schema.

Validation Admission, Review, Production Safety, Dashboard, and Decision do not
create Product Observation snapshots.

## Consequences

- Product facts are detached from mutable runtime Products.
- Unknown shipping remains distinct from confirmed zero shipping.
- Future calculations can reference a stable source without reconstruction.
- Price history retains its existing purpose and behavior.
- Collector integration and durable persistence remain future work.
- Existing Product and price-history records are not backfilled.

## Out of Scope

- Persistence tables, migration, or backfill
- Collector behavior changes
- PriceIntelligence or Economics snapshots
- Production Safety calculation, receipt, API, or UI
- Validation, Review, Dashboard, or Decision changes
