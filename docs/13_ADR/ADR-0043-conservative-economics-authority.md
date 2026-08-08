# ADR-0043 Conservative Economics Authority

## Status

Accepted

## Implementation Status

Implemented by CR-1B4B and exposed through the thin CR-1B4B1 production entry
and Opportunity-scoped API. The Domain/Application authority and append-only
SQLite result/receipt persistence enforce this ADR; the web boundary only
provides exact source/scenario facts, server identity/clocks, resource
lifecycle, transport mapping, and authoritative result serialization. No UI or
Capital decision composition is included.

The implemented policy identity is `conservative-unit-economics` version
`1.0.0`. Its only scenario assumption is an explicitly caller-supplied Decimal
sale-price factor greater than zero and at most one. There is no default or
automatic haircut.

## Context

ADR-0042 provides an immutable, exact-source `EconomicsSourceComposition`, but
three meanings were intentionally not sufficient for a Capital-facing unit
economics calculation:

- `duty_cost` is absolute money but does not prove a per-unit customs scope;
- `tax_rate` is a generic rate and does not prove seller-cost, inclusion, or
  recovery semantics;
- existing `roi`, `landed_cost_roi`, and Actual ROI use different denominator
  scopes.

Treating any unresolved duty or tax as zero would violate UNKNOWN safety.
Reusing an existing ROI name with the normalized acquisition total would change
historical meaning. Conservative Economics therefore needs explicit semantics
before it can calculate an authoritative result.

## Decision

Conservative Economics will be a distinct future financial evaluation owner.
It will consume only one exact READY `EconomicsSourceComposition` and one
explicit versioned scenario. It may calculate unit economics, but it will not
decide Capital Readiness, Capital Gate, BUY/INVEST, position size, or Founder
capital approval.

This ADR resolves only duty, tax, and ROI authority. It does not implement the
calculation.

## Duty Authority

Current `duty_cost` is a `MoneyInput`, so it is an absolute amount in the
Verified Economics currency with preserved evidence. The current contract does
not prove that a non-zero amount is per unit, belongs to the exact normalized
acquisition scope, or is safe to add once to unit economics. Existing
operational Economics does not consume it, and ADR-0042 explicitly deferred its
formula.

Conservative policy therefore applies these rules:

- explicit `VERIFIED` zero with an evidence reference contributes exact zero;
- missing, unsupported, weak, or non-zero duty blocks calculation;
- current evidence has no authoritative `NOT_APPLICABLE` state, so N/A is not
  inferred from absence or zero;
- a future exact per-unit, target-currency duty authority may permit non-zero
  duty through a new versioned policy;
- no customs, tariff, allocation, or currency calculation is inferred.

## Tax Authority

Current `tax_rate` is a `RateInput` with evidence. The legacy calculator applies
it to gross sale price, but the Domain contract does not establish whether it is
seller-borne, included in displayed price, marketplace-collected, recoverable,
or a jurisdiction-specific scenario. That operational formula is not promoted
to Capital authority.

Conservative policy therefore applies these rules:

- explicit `VERIFIED` zero with an evidence reference contributes exact zero;
- missing, unsupported, weak, or non-zero generic tax blocks calculation;
- N/A is not inferred because the current evidence model has no authoritative
  applicability state;
- a future Capital-facing tax treatment may permit non-zero tax under a new
  exact contract and policy version;
- no generalized tax or VAT engine is introduced.

## Conservative Acquisition ROI

Define a new metric named `conservative_acquisition_roi`:

```text
conservative_acquisition_roi =
    conservative_profit_per_unit
    / authoritative_normalized_acquisition_cost_per_unit
    * 100
```

The denominator is the exact `acquisition_cost_per_unit` carried by the source
composition. It represents the normalized per-unit acquisition capital already
bound to exact allocation and FX facts. Sale-side fees reduce the profit
numerator but are not acquisition capital and therefore do not enter this
denominator.

This metric is distinct from:

- legacy `roi`, whose denominator is purchase price;
- legacy `landed_cost_roi`, whose denominator is the legacy landed-cost value;
- Actual Economics ROI, whose denominator remains actual purchase price.

Those existing fields and formulas are unchanged and are never aliased to the
new metric.

## Denominator Safety

- acquisition cost greater than zero permits ROI calculation;
- acquisition cost equal to zero makes ROI undefined and blocks the result;
- a negative acquisition cost is an invalid authoritative source;
- infinity, fallback zero, and silent substitution are forbidden.

## Future Actual Symmetry

Actual Economics is unchanged. A future `actual_acquisition_roi` may be added
only after Actual Economics can preserve a denominator comparable to the exact
normalized acquisition scope. Legacy Actual ROI remains purchase-price based.
Until that contract exists, variance must not compare it directly with
`conservative_acquisition_roi`.

## Consequences

CR-1B4B can safely support the narrow MVP path where duty and tax are explicit
verified zero, all other required sources are authoritative, and normalized
acquisition cost is positive. Unsupported cases produce a deterministic BLOCKED
result rather than guessed profitability.

The future calculation must preserve exact source composition, scenario and
policy identity/version, assumptions, Decimal arithmetic, and historical replay.
It must not route through the legacy purchase/shipping calculator or create
monthly forecasts or Capital decisions.

## Deferred Work

- authoritative non-zero per-unit duty admission;
- explicit tax applicability and seller-cost treatment;
- actual normalized acquisition-cost symmetry;
- Capital Readiness, Capital Gate, and Founder capital approval.
