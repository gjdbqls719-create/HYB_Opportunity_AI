# ADR-0008: Canonical Economics Analysis Provenance

## Status

Accepted

## Context

`calculate_opportunity` begins with a shallow copy of its caller-supplied product
or context mapping and then adds calculator-owned facts. Consequently the
runtime `EconomicsCalculation.analysis` contains both input context and results:
fee rates and sources, marketplace-rule provenance, calculated costs and rates,
monthly profit, score, recommendation, decision reason, reason and warning
lists, and profitability booleans. The public calculator boundary permits
arbitrary Python objects in the input mapping.

Persisting that open `Mapping[str, Any]` directly would permit mutable nested
state, ambiguous serialization, bool/int collapse, Decimal-to-float loss, naive
timestamps, and objects that cannot be deterministically reconstructed. Keeping
only the fields currently read by Production Safety would discard authoritative
calculation provenance.

The persisted Verified Economics contract has no independent snapshot ID. Its
authoritative lookup key is Opportunity ID, so calling that reference a snapshot
ID is misleading.

## Decision

EconomicsCalculationSnapshot owns a complete `EconomicsAnalysisSnapshot`. It is
a versioned, fingerprinted canonical tagged tree. Mapping entries are sorted;
all stored collections are tuples. Tags distinguish null, bool, int, finite
float, finite Decimal, text, Enum type/member, timezone-aware datetime, tuple,
list, and text-keyed mapping. Runtime tuple/list/mapping distinctions are restored
exactly. Enum reconstruction requires an explicit supported type registry.

Arbitrary objects, sets, non-text mapping keys, cycles, non-finite numbers, naive
datetimes, malformed canonical nodes, unsupported analysis versions, and unknown
Enum types or members fail explicitly. Nothing is coerced, defaulted, or dropped.

The Verified Economics lineage field is
`verified_economics_opportunity_id`. This names the real persisted key and does
not invent a snapshot identifier.

The Production Safety Runtime Adapter copies canonical facts into a disposable
runtime EconomicsCalculation. It does not call the Economics calculator or the
Production Safety engine. Runtime mutation cannot change the source snapshot.

## Consequences

- Runtime analysis can round-trip with complete keys, values, and supported type semantics.
- Fingerprints and deterministic ordering provide a stable integrity boundary.
- Unsupported caller context is rejected at snapshot creation instead of becoming false provenance.
- Exact Economics and complete runtime bundles can be reconstructed without recalculation.
- Existing formulas, rules, statuses, and runtime calculator behavior remain unchanged.

## Out of Scope

- Production Safety execution, assessment persistence, receipt, API, or UI
- SQLite, schema, migration, transaction, wiring, or backfill
- Calculator, analyzer, formula, rule, status, Decision, Dashboard, or collector changes
