# ADR-0007: Production Safety Runtime Reconstruction Policy

## Status

Accepted; Economics analysis blocker resolved by ADR-0008

## Context

Production Safety still consumes runtime Product, PriceIntelligence, and
EconomicsCalculation values. PR29–PR32 establish authoritative immutable source
snapshots and lineage but intentionally do not persist runtime objects.

Product and PriceIntelligence snapshots preserve every constructor field.
EconomicsCalculationSnapshot preserves typed result fields, calculation
parameters, profitability provenance, a Verified Economics reference, and—after
PR31.1—the complete canonical runtime analysis mapping returned by
`calculate_opportunity`.

The missing analysis includes fee source/rates, marketplace-rule metadata,
estimated monthly profit, score, recommendation, decision reason, reasons, and
warnings. Recomputing or defaulting those fields would execute formulas or invent
facts.

## Decision

Runtime objects are disposable Application-boundary projections. Snapshots are
the authoritative truth and remain unchanged when runtime projections mutate.
Runtime objects are never persisted.

The adapter may:

- pass every Product snapshot scalar directly to the existing Product constructor;
- pass every PriceIntelligence result directly to its constructor;
- load the exact VerifiedEconomicsSnapshot referenced by the context; and
- validate exact identities, schemas, and externally supplied supported analyzer
  and calculator versions.

Reconstruction copies values only. It does not select a cohort or representative,
rerun an analyzer or calculator, apply a formula or threshold, infer shipping or
data source, or inject defaults for missing analysis.

The current VerifiedEconomicsSnapshot has no independent snapshot ID; its
authoritative persistence key is opportunity ID. Runtime loading therefore
requires the context reference and Opportunity identity to equal that key.

EconomicsCalculation and the complete runtime input bundle may be reconstructed
only when ADR-0008 canonical analysis is present, fingerprint-valid, and uses the
supported analysis version and value types. Fields absent from a snapshot are
never reconstructed.

The Production Safety Runtime Adapter owns reconstruction. It does not call the
Production Safety engine. Safety execution and outcome persistence belong to a
later PR; resolving analysis provenance does not authorize Safety execution.

## Consequences

- Product, PriceIntelligence, and EconomicsCalculation can be reconstructed deterministically.
- Exact Verified Economics inputs can be loaded without writes.
- Unsupported versions and malformed or conflicting sources fail distinctly.
- No formula, threshold, cohort selection, calculator, or Safety rule is rerun.
- Production Safety remains intentionally unexecuted.

## Out of Scope

- Production Safety execution, assessment, snapshot, receipt, API, or UI
- SQLite, migration, transaction, or backfill
- Collector, analyzer, calculator, Formula, Rule, Status, Decision, or Dashboard changes
- Silent Economics snapshot extension or inferred runtime analysis
