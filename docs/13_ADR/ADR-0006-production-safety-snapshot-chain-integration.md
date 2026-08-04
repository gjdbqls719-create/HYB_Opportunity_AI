# ADR-0006: Production Safety Snapshot Chain Integration

## Status

Accepted

## Context

The existing `assess_production_safety` function owns the established READY,
INSUFFICIENT_DATA, and PROFITABILITY_FAILED behavior. It reads runtime `Product`,
`PriceIntelligence`, `EconomicsCalculation`, and analysis facts. PR29–PR31 define
immutable source snapshots without changing those runtime contracts.

The snapshots now preserve the Product facts, PriceIntelligence results and
ordered cohort, Economics results, profitability facts, and the Verified
Economics source reference. However, the existing function still requires
runtime engine objects, and Economics readiness requires loading the referenced
VerifiedEconomicsInput. Materializing those runtime objects in this PR would
introduce an unapproved reconstruction policy and violate the prohibition on
fake or inferred sources.

## Decision

`ProductionSafetyEvaluationContext` groups the exact Product Observation,
PriceIntelligence, and EconomicsCalculation snapshots plus the Verified
Economics snapshot reference. The Production Safety Integration Layer exclusively
owns this context.

The context validates only source lineage:

- Opportunity identities match;
- Market Observation identities match;
- the selected Product Observation belongs to the ordered price cohort; and
- the Verified Economics reference matches the EconomicsCalculation source.

`ProductionSafetySourceRepository` provides authoritative snapshot lookup and a
lineage-validation boundary. The integration service loads exact snapshots and
delegates repository validation. It does not create runtime Product,
PriceIntelligence, or EconomicsCalculation objects and does not execute Safety.

The existing `assess_production_safety` remains unchanged because its formula,
rules, status meanings, and legacy callers are already tested. A later approved
boundary must decide how immutable sources are supplied to that function without
inventing runtime facts and must load the exact Verified Economics snapshot.

Collectors, Review, Dashboard, and Decision do not create evaluation contexts.

## Consequences

- Snapshot lineage can be assembled and rejected before any Safety execution.
- No runtime object or inferred source is persisted in the context.
- Existing Safety behavior remains byte-for-byte untouched.
- Production Safety cannot yet execute from snapshots; runtime adaptation and
  Verified Economics source loading remain explicit blockers.
- No legacy snapshot is migrated or backfilled.

## Out of Scope

- Safety execution, API, UI, or receipt
- Runtime reconstruction or adaptation policy
- SQLite, transactions, migration, or backfill
- Decision or Dashboard changes
- Formula, rule, status, analyzer, calculator, or orchestrator changes
