# ADR-0041 Authoritative Acquisition Cost Normalization

## Status

Accepted

## Implementation Status

CR-1B5D2H exposes the existing normalization owner through an Opportunity-scoped API.
The request names the exact ordered allocation/FX manifests and explicit target
currency; the production entry derives Opportunity identity from the exact Landed Cost
composition. Same-currency normalization uses no FX fact, and unresolved/unknown or
incomplete exact manifests remain rejected without fallback.

## Context

HYB durably preserves one exact `LandedCostComposition`, reconciled
`ShippingAllocationAuthority` facts, and authoritative `FXObservation` facts.
None of those owners is allowed to turn mixed-currency, non-per-unit acquisition
costs into a common per-unit money value. Capital-facing Economics therefore
needs a separate calculation authority which does not select latest sources or
invent missing allocation, currency, or applicability facts.

## Decision

Create `NormalizeAcquisitionCosts` as the dedicated Application owner and
`AcquisitionCostNormalization` as its immutable result. The command explicitly
owns the target currency and names the exact Opportunity, Landed Cost
Composition, ordered Shipping Allocation Authority IDs, ordered FX Observation
IDs, request time, and normalization policy version.

Normalization covers only the fixed acquisition component order:

1. `UNIT_PURCHASE`
2. `SUPPLIER_SIDE_SHIPPING`
3. `INTERNATIONAL_FREIGHT`
4. `DOMESTIC_INBOUND`

It does not calculate sale-side fees, tax, duty, profit, ROI, Capital Readiness,
or an investment decision.

## Allocation Authority

- `PER_UNIT` uses the exact source amount without a denominator.
- `PER_ORDER` requires an exact resolved authority and its positive
  Founder-admitted denominator.
- `PER_QUOTED_QUANTITY` requires an exact resolved authority whose denominator
  remains bound to the exact known quoted quantity.
- `PER_WEIGHT` and `UNSPECIFIED` are not normalizable under policy v1.
- MOQ, fallback one, another component's denominator, and implicit basis
  inference are forbidden.

Every applicable shipping result preserves both the original source basis and
the effective admitted basis, the authority ID, denominator, and denominator
source.

## FX Authority and Direction

The target currency is explicit command authority; it is never hardcoded.
Same-currency components use no FX fact. Each cross-currency component uses one
exact named `FXObservation`.

For an observation where `1 base = rate quote`:

- direct `base -> quote` conversion multiplies by `rate`;
- inverse `quote -> base` conversion divides by `rate`.

Inverse use does not create another observation. The same observation ID and an
explicit `INVERSE` direction are persisted. No provider lookup, latest-rate
selection, implicit pair inversion, or freshness policy is introduced.

## Decimal Arithmetic Policy

Policy `authoritative-acquisition-cost-normalization` version `1.0.0` uses:

- `Decimal` operands only;
- a fixed 34-significant-digit context;
- `ROUND_HALF_EVEN` for non-terminating division and context rounding;
- no intermediate money quantization;
- ordered component summation under the same context;
- presentation and currency-minor-unit rounding deferred to a later boundary.

The result stores the policy identity, version, precision, and rounding mode so
restart reconstruction is deterministic. A different arithmetic rule requires
a new policy version and a new command.

## UNKNOWN, Not Applicable, and Zero

- `UNKNOWN` blocks authoritative normalization and never becomes numeric zero.
- `NOT_APPLICABLE` contributes explicit zero while preserving that source state.
- `KNOWN` `Decimal("0")` remains a valid observed zero.

The total is produced only after every applicable component is allocated and
converted into the same target currency.

## Identity, Time, Persistence, and Replay

The normalization identity is a dedicated server-owned opaque UUIDv4 value.
`requested_at` is caller-owned; `normalized_at` and `committed_at` are separate
server clocks.

Two dedicated append-only SQLite histories preserve the immutable result and
receipt in one `BEGIN IMMEDIATE` transaction. They retain the ordered component
provenance and exact source manifest. No latest/current projection exists.

- same command and same payload returns the persisted result;
- same command with changed source, target currency, or policy conflicts;
- replay lookup occurs before identity and clock calls;
- restart reconstructs stored arithmetic rather than recalculating against
  current sources;
- UPDATE and DELETE are forbidden.

## Boundaries and Consequences

Critical Cost Completeness remains a source-completeness assessment and is not
changed. Normalization independently validates its exact persisted inputs.
Existing generic currency services are not reused because they may fetch a
provider value or apply unrelated rounding defaults.

The result is a future input to Economics Source Composition, which may combine
it with expected sale price and sale-side costs. This decision does not create
Verified Economics automatically, Conservative Economics, Capital Readiness,
Capital Gate, Founder approval, UI, or external FX acquisition.

Actual Economics remains unchanged. Unit purchase and the three shipping scopes
are structurally comparable later, but actual allocation denominators, exact
actual FX use, and category-complete actual acquisition costs remain future
work.
