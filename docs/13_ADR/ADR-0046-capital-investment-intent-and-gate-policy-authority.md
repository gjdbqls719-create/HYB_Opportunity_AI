# ADR-0046 Capital Investment Intent and Gate Policy Authority

## Status

Accepted

## Implementation Status

Intended Order Quantity and Deployable Capital Snapshot are implemented by
CR-1B5B0A as immutable Domain/Application facts with dedicated opaque identities,
replay-first owners, and append-only SQLite history/receipt persistence.
CR-1B5B0B implements the exact-source-bound upfront-cost scope verification and
Planned Acquisition Capital Requirement with deterministic Decimal arithmetic,
CALCULABLE/BLOCKED semantics, and append-only SQLite replay persistence.
CR-1B5B implements the exact-source Capital Gate with PASS/REJECTED/BLOCKED
semantics and append-only SQLite replay persistence. Capital-bound Founder
Approval is implemented by CR-1B5C as a separate exact-Gate human authorization
fact. Production API/UI and purchase execution remain unimplemented.

## Context

ADR-0045 admits one exact evidence chain to Capital review but deliberately owns
no order quantity, required-capital, available-capital, profitability-threshold,
reserve, exposure, or Founder approval meaning. The repository has no existing
authoritative intended-order, cash, reserve, or Capital position fact.

Supplier MOQ and quoted quantity are immutable Quote provenance. Shipping
Allocation denominators are component-scoped allocation facts. None of those
facts says how many units the Founder intends to purchase for one Capital
decision. Likewise, ADR-0041 produces exact normalized acquisition cost per
unit, not total cash required for an order.

The first Real-Money MVP needs the smallest explicit authority set that can
compare a planned acquisition with capital the Founder has deliberately made
available, while keeping evidence readiness, investment policy, and human
approval separate.

## Decision

### Intended Order Quantity

Introduce a future immutable Founder-owned `IntendedOrderQuantity` authority.
It means:

> The exact positive quantity the Founder intends to purchase for this
> Opportunity and this specific Capital decision.

Its durable fact must preserve a dedicated opaque identity, exact Opportunity
identity, exact Sourcing Binding/Admission and Quote revision, positive quantity,
quantity unit, Founder/operator identity, caller-declared/requested time, server
admission/receipt time, and schema version.
Admission and history are append-only. A new quantity requires a new fact; it
does not mutate an earlier Capital decision.

Intended Order Quantity is never inferred from:

- minimum order quantity;
- quoted quantity;
- a Shipping Allocation denominator;
- inventory, Candidate, or observation counts;
- a fallback value.

MOQ remains only a Supplier constraint. A future Gate must produce `REJECTED`
for an intended quantity below a known applicable MOQ and `BLOCKED` when the
required MOQ constraint cannot be resolved, but it must never replace the
intended quantity with MOQ. Quoted quantity remains Quote/tier provenance and
is not purchase intent.

### Planned Acquisition Capital Requirement

Use the precise future name `PlannedAcquisitionCapitalRequirement`, not the
unqualified term "Capital Requirement". Its narrow amount is:

```text
exact normalized acquisition cost per unit
× exact Intended Order Quantity
```

The result binds the exact ADR-0041 normalization, Intended Order Quantity, one
target currency, arithmetic policy identity/version, and calculation time. The
v1 arithmetic policy must use Decimal-only arithmetic with the existing
ADR-0041 34-significant-digit `ROUND_HALF_EVEN` convention and no implicit
minor-unit quantization. A changed arithmetic policy requires a new version.

This amount covers only the normalized acquisition components already owned by
ADR-0041: unit purchase, supplier-side shipping, international freight, and
domestic inbound. It is not total business cash need and does not silently
include supplier deposits or payment timing, samples, inspection, certification,
additional tax/duty, storage, fulfillment, or any other unmodelled cash outflow.

Before a v1 Gate may use this amount, one exact Founder-owned upfront-cost scope
verification must confirm that every mandatory upfront acquisition cash outflow
outside ADR-0041 is either represented by a future exact authority or explicitly
not applicable to this planned order. Absence, uncertainty, or a generic zero is
`BLOCKED`; it is never treated as no additional cost. The verification is an
immutable source fact and must be bound by the requirement rather than supplied
as transient Gate input.

### Deployable Capital Snapshot

Introduce a future immutable Founder-owned `DeployableCapitalSnapshot`. It
means:

> The exact amount of capital the Founder explicitly makes available to HYB for
> an investment decision as of a stated time.

It preserves a dedicated opaque identity, non-negative Decimal amount, currency,
`as_of`, Founder/operator identity, evidence/reference when supplied, and schema
version. Explicit zero is valid and remains distinct from a missing snapshot.
History is append-only.

Deployable Capital is not a bank balance, total business cash, credit limit, or
automatically discovered money. For v1 it is already reserve-adjusted: the
Founder excludes operating, emergency, personal, and otherwise unavailable
capital before declaring it. Capital Gate must not infer or subtract another
reserve. A future automated reserve model requires a new authority and policy
version.

### Currency

`PlannedAcquisitionCapitalRequirement` uses the exact Acquisition Normalization
target currency. The selected Deployable Capital snapshot must use that same
currency. Capital Gate v1 performs no FX conversion; a mismatch or missing
currency-compatible fact is `BLOCKED`.

### Capital Gate Policy v1

Use policy identity `domestic-commerce-capital-gate` version `1.0.0` for the
future Gate. It evaluates exact persisted facts only and has three states:

- `PASS`: every required fact is complete and the explicit policy passes;
- `REJECTED`: facts are complete, but an explicit profitability or capital
  constraint fails;
- `BLOCKED`: a required fact is missing, unsafe, inconsistent, expired, or
  unsupported.

For v1, profitability passes only when all three persisted Conservative
Economics values are strictly greater than zero:

- `conservative_profit_per_unit > 0`;
- `conservative_margin > 0`;
- `conservative_acquisition_roi > 0`.

These are Capital Gate policy rules. They do not reuse Discovery's 30% ROI,
legacy Economics thresholds, or Production Safety values, and they assert only
that the explicit Conservative scenario is not loss-making. They do not assert
that the investment is attractive.

Capital sufficiency passes only when:

```text
PlannedAcquisitionCapitalRequirement.amount
<= DeployableCapitalSnapshot.amount
```

in the exact same currency. A complete but unaffordable plan is `REJECTED`.
Missing requirement, missing deployable capital, unresolved upfront-cost scope,
or currency mismatch is `BLOCKED`.

### Exact Gate Source Manifest

A future Gate result must bind, without latest lookup:

- one exact `READY_FOR_CAPITAL_REVIEW` Capital Readiness assessment;
- one exact Intended Order Quantity;
- one exact Planned Acquisition Capital Requirement, including its exact
  normalization and upfront-cost scope verification;
- one exact Deployable Capital snapshot;
- the exact Capital Gate policy name/version.

Conservative Economics and its exact source chain may be reconstructed through
Capital Readiness for policy evaluation. The Gate result must still verify that
the Capital Requirement and intended quantity use the same Opportunity and
Sourcing lineage. Redundant source IDs are not copied unless reconstruction or
arithmetic verification requires them.

### Position and Concentration

The first Real-Money validation adopts "one active capital deployment at a
time" as a manual operating procedure, not as a Capital Gate fact. The current
repository has no authoritative Active Position or portfolio exposure source,
so Gate v1 must not claim to enforce concentration.

The later Capital-bound Founder Approval boundary owns the manual check before
release. Automated active-position, category, supplier, portfolio, exposure, or
concentration enforcement requires a separate authority decision and a new Gate
policy version.

### Founder Capital Approval

Gate `PASS` means only eligible for Founder Capital Approval. It never authorizes
purchase or deployment.

Future Capital-bound Founder Approval must bind the exact Gate result, exact
approved capital amount and currency, Founder identity, approval timestamp, and
policy/source version. The existing generic `FounderDecision` does not preserve
those facts and is not reused as Capital approval authority.

### Replay and Historical Policy

All future intent, capital, requirement, Gate, and approval facts are immutable
and exact-source-bound. Same command and payload returns the persisted result;
changed payload conflicts. Replay occurs before server identity or clocks.

Policy name/version is fixed in every Gate result. New evidence, quantity,
capital snapshot, or policy requires a new command and result. Historical Gate
results are never recomputed against latest sources or a newer policy.

## Consequences

- Capital Readiness remains an evidence-admission boundary.
- Capital Gate receives explicit order intent, narrow planned acquisition cash,
  and Founder-declared reserve-adjusted deployable capital.
- Unknown upfront cash cannot disappear into a misleading requirement total.
- Complete facts that fail policy are distinguishable from incomplete facts.
- Gate pass remains separate from human authorization to spend money.
- The first MVP avoids bank integration and portfolio automation without
  claiming those controls exist.

## Deferred Work

1. Purchase execution and the one-active-deployment operating workflow.
2. Production entries and any API/UI exposure.
3. Future reserve automation, Active Position, portfolio exposure, and
   concentration policy if Real-Money evidence justifies them.
