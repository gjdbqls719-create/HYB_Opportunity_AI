# ADR-0037: Landed Cost Composition Authority

## Status

Accepted (CR-1B3A)

## Context

An exact Sourcing Economics Binding identifies the admitted Supplier quote used
by an Opportunity, but downstream Economics cannot safely collapse one quote
unit price, three shipping scopes, MOQ, and quoted quantity into its existing
single purchase and shipping fields. Shipping facts do not state whether their
amounts are per unit, per order, per weight, or quoted-quantity totals.

## Decision

- `LandedCostComposition` names the acquisition-side facts from unit purchase
  through domestic inbound. Advertising, returns, marketplace/payment fees,
  taxes, duty, storage, and fulfillment remain outside this contract.
- The Sourcing Application boundary owns composition from one explicit
  `SourcingEconomicsBindingReference`; it never selects a latest binding or quote.
- Four canonical components remain independent and ordered: unit purchase,
  supplier-side shipping, international freight, and domestic inbound.
- `KNOWN`, `UNKNOWN`, and `NOT_APPLICABLE` retain distinct meanings. Known zero
  remains zero; absent facts carry neither amount nor currency.
- Every known component retains its source currency. There is no FX conversion.
- Quote unit price has `PER_UNIT` basis. Existing shipping facts do not own an
  allocation basis, so they remain `UNSPECIFIED`; no division by quantity occurs.
- MOQ and quoted quantity are immutable provenance, not capital calculations.
- The composition preserves exact binding, Opportunity identity, quote evidence,
  caller request time, server composition time, opaque identity, and version.
- A caller-fact fingerprint supports exact replay and changed-payload conflict
  before identity or clock calls through an Application repository port.

## Persistence scope

SQLite is deferred. Allocation semantics are newly introduced and existing
shipping authority can only state `UNSPECIFIED`. Stabilizing this contract first
avoids persisting an inferred allocation meaning. The port-level receipt/replay
contract defines the next persistence boundary.

## Consequences

Consumers receive lossless acquisition facts but cannot yet produce a normalized
single-currency or per-unit Economics input. A later quote cannot mutate an
existing composition; a new explicit binding and command are required.

## Deferred

FX conversion, shipping allocation, tax/duty calculation, Critical Cost policy,
Conservative Economics, Capital Readiness/Gate, Founder capital approval,
Verified Economics generation, Actual Economics changes, SQLite persistence,
API/UI, supplier collectors, and Snapshot Chain extension remain deferred.
