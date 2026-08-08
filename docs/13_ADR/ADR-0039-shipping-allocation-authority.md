# ADR-0039 — Shipping Allocation Authority

## Status
Accepted

## Context

HYB must not convert non-per-unit shipping costs into unit economics
without an authoritative allocation denominator.

The existing LandedCostComposition preserves allocation basis but does
not own the denominator authority required for PER_ORDER and similar costs.

## Decision

Introduce a separate Shipping Allocation Authority boundary.

The authority records whether a specific landed-cost shipping component
has sufficient allocation facts to be used later by cost normalization.

Supported semantics:

- PER_UNIT
  - resolved
  - no denominator required

- PER_QUOTED_QUANTITY
  - may use the exact persisted quoted quantity
  - only when that quantity is explicitly known

- PER_ORDER
  - requires an explicit founder/operator-admitted denominator
  - MOQ is never inferred as the denominator
  - quoted quantity is not reused implicitly

- PER_WEIGHT
  - unresolved/unsupported until authoritative weight facts exist

- UNSPECIFIED
  - unresolved
  - no automatic inference

## Authority Boundary

Shipping Allocation Authority does not:

- perform division
- normalize shipping to per-unit cost
- perform FX conversion
- calculate landed-cost totals
- determine profitability
- determine Capital Readiness
- determine Capital Gate or investment approval

It only records whether the denominator authority exists and its provenance.

## Quantity Semantics

MOQ and allocation denominator are separate facts.

MOQ means the minimum quantity that may be ordered.
Allocation denominator means the quantity to which a specific total cost
actually applies.

HYB must not assume they are equal.

## Trust / Evidence

Source-derived allocation may use exact admitted sourcing facts such as
quoted quantity when the allocation basis explicitly permits it.

Founder/operator-admitted allocation remains a separate factual authority.

Existing sourcing evidence references are reused.
No new evidence system is introduced.

## Immutability / Replay

The contract is immutable.

Replay semantics follow the existing sourcing authority pattern:

- same command + same payload → exact replay
- same command + changed payload → conflict

Persistence is intentionally deferred to a follow-up PR.

## Deferred

- SQLite persistence
- production API/UI
- Critical Cost integration
- actual shipping division
- cost normalization
- FX authority
- Conservative Economics
- Capital Readiness
- Capital Gate