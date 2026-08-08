# ADR-0039 — Shipping Allocation Authority

## Status

Accepted; reconciled and persisted by CR-1B3C1.

## Context

HYB must not convert non-per-unit shipping costs into unit economics without
authoritative allocation basis and denominator facts. Production
`LandedCostComposition` deliberately records existing shipping terms with an
`UNSPECIFIED` basis because the Supplier quote does not own that meaning. The
original Shipping Allocation foundation merely read that basis, so real
production facts could never reach `PER_ORDER` or `PER_QUOTED_QUANTITY`.

The original foundation was also ephemeral. It had no durable identity,
receipt, restart reconstruction, or exact replay and therefore could not serve
as a historical financial-calculation source.

## Decision

Shipping Allocation Authority is an immutable overlay on one exact persisted
Landed Cost composition and shipping component. It does not mutate composition
history.

### Basis and denominator authority

Allocation basis and allocation denominator are separate facts:

- basis answers what the shipping amount applies to;
- denominator answers the exact positive quantity to which a non-per-unit
  amount may be allocated.

A denominator never infers a basis, and a basis never invents a denominator.
For a source component already carrying an explicit basis, the same basis may be
reaffirmed but a different basis is rejected. For a production `UNSPECIFIED`
component, an operator must explicitly admit the effective basis with evidence
and factual verification time.

### Supported MVP semantics

- `PER_UNIT` resolves without a denominator.
- `PER_ORDER` requires an explicit positive founder/operator-admitted
  denominator and its evidence provenance.
- `PER_QUOTED_QUANTITY` may resolve only from the exact composition's known
  quoted quantity and preserves that source-derived provenance.
- `PER_WEIGHT` remains unresolved until authoritative weight facts exist.
- `UNSPECIFIED` remains unresolved and is never inferred.

MOQ is never an allocation denominator. Quoted quantity is not reused for
`PER_ORDER` and is eligible only for explicit `PER_QUOTED_QUANTITY`.

### Provenance and time

Operator-admitted basis facts preserve operator identity, factual
`verified_at`, and one existing `SourcingEvidenceReference`. Caller
`requested_at`, server `admitted_at`, and persistence `committed_at` remain
separate. A generated string is not evidence.

### Identity, replay, and persistence

Each authority receives a dedicated server-owned opaque UUIDv4-style identity.
Identity is not derived from composition, component, denominator, fingerprint,
or SQLite row ID.

The caller command fingerprint includes exact composition, Opportunity,
component, effective basis, denominator, operator/evidence, factual timestamps,
and command version. Server identity and server timestamps are excluded.

- same command and payload returns the exact persisted authority and receipt;
- changed payload under the same command conflicts;
- replay occurs before identity or server clocks.

Dedicated SQLite history and receipt tables commit atomically under
`BEGIN IMMEDIATE`. Both tables are append-only. Reads reconstruct the exact
original/effective basis, denominator, provenance, timestamps, and version and
revalidate the exact composition, Opportunity, component, and quoted-quantity
source without selecting latest facts.

## Boundaries

Shipping Allocation Authority does not divide costs, perform FX conversion,
calculate totals, determine profitability, change Critical Cost assessment,
or assert Capital Readiness, Capital Gate, or investment approval.

## Consequences

Future normalization can explicitly name one durable allocation authority for
each applicable shipping component. Existing historical composition remains
unchanged, concurrent identical commands converge, and failed transactions do
not create partial financial authority.

## Deferred

Cost normalization, Critical Cost consumption of allocation identities, FX
binding/conversion, rounding, `PER_WEIGHT` logistics, production API/UI,
Conservative Economics, Capital Readiness/Gate, and Founder capital approval
remain deferred.
