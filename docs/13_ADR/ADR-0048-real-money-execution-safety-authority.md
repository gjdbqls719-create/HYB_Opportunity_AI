# ADR-0048 Real-Money Execution Safety Authority

## Status

Accepted

## Implementation Status

CR-1B5D1 implements the immutable Domain/Application authority, dedicated opaque
identity supplier, versioned safety policy, and append-only SQLite intent/receipt
persistence with durable READY-per-Approval cardinality. CR-1B5D2L exposes the
exact-source execution-safety command through production API, including the
distinct post-Approval capital snapshot and durable READY alias/cardinality
behavior. UI, manual Purchase Execution Record, and Actual Economics handoff
remain unimplemented.

## Context

ADR-0047 records an immutable Founder Capital Approval over one exact Capital
Gate `PASS`. That approval proves the historical evidence, policy decision,
planned quantity, capital requirement, amount cap, currency, and explicit human
authorization. It deliberately does not prove that the Supplier Quote or capital
is still current when the Founder is about to place a manual order.

The exact chain is reconstructible:

```text
Capital Gate PASS
-> Founder Capital Approval
-> [execution-time safety gap]
-> Founder manually places the Supplier order outside HYB
-> future Purchase Execution Record
-> future exact Actual Economics handoff
```

The Sourcing Admission preserves Supplier and Sourcing Product identity, exact
option/SKU references when supplied, exact Quote revision, commercial facts,
evidence, and `valid_until`. Intended Order Quantity, approved amount/currency,
and reserve-adjusted Deployable Capital are also durable. Those facts are enough
to define a narrow manual-action safety boundary without implementing checkout,
payment, or Supplier-order semantics inside HYB.

## Decision

### Authority and Meaning

Introduce a future immutable `RealMoneyExecutionIntent` authority with states:

- `READY_FOR_MANUAL_EXECUTION`;
- `BLOCKED`.

Its only meaning is:

> This exact proposed manual purchase action is safe to proceed now under this
> exact Founder Capital Approval and execution-safety policy.

It is both the exact proposed-action manifest and its safety assessment. A READY
intent is the single durable reference the Founder uses while ordering and later
recording what occurred. It never means executed, ordered, paid, accepted, or
received.

### Exact Approval and Source Chain

The command must name one exact persisted `FounderCapitalApproval`. The owner
reconstructs, without latest lookup, its exact Capital Gate, Requirement,
Intended Order Quantity, Deployable Capital source, Sourcing Admission, Supplier,
Sourcing Product, Quote ID/revision, and Opportunity lineage. Missing named
sources are explicit source errors. Unsupported or inconsistent persisted
sources fail closed and are never corrected or inferred.

### Proposed Manual Action

The caller supplies only these factual action inputs:

- command ID;
- exact Founder Capital Approval ID;
- exact intended quantity and quantity unit;
- exact planned execution amount and currency;
- exact Quote ID and revision being confirmed;
- one exact newly declared Deployable Capital Snapshot ID;
- the same factual Founder identity as the Approval;
- requested time and factual current-execution confirmation time.

The confirmation means that the named Founder has just reviewed the exact Quote,
quantity, amount, currency, and selected capital snapshot and still intends this
specific manual action. It is not a payment command. Supplier checkout fields,
payment credentials, and an order reference do not belong to the intent because
no order exists yet.

### Amount, Quantity, and Currency

Policy v1 requires exact equality:

```text
planned execution amount == Founder Capital Approval approved amount
execution quantity == exact Intended Order Quantity
execution quantity unit == exact Intended Order Quantity unit
execution currency == Approval/Requirement currency
```

There is no tolerance, partial execution, staged release, MOQ substitution,
quoted-quantity substitution, automatic adjustment, or FX. Changed action facts
require a new Quote and downstream Capital chain as applicable, followed by a
new Gate and Approval.

### Execution-Time Quote Validity and Drift

The owner reloads the exact Admission/Quote revision named through the Approval.
At the server-owned evaluation time:

- missing `valid_until` blocks;
- `valid_until <= evaluated_at` blocks;
- a valid exact revision may proceed;
- a newer Quote is never substituted.

The Founder confirmation additionally asserts that the exact persisted terms
are still the terms offered for this manual action. Any observed change to unit
price, shipping, option/SKU, quantity, currency, or other commercial terms
requires a new Quote revision and the affected downstream chain. No drift
tolerance is introduced.

### Current Deployable Capital

Execution safety requires an exact newly admitted reserve-adjusted
`DeployableCapitalSnapshot`, not the historical snapshot used by the Gate. The
caller names it explicitly; no latest selection or bank lookup occurs. It must:

- differ from the Gate's historical snapshot;
- use the existing `founder-declared-reserve-adjusted-v1` semantics;
- have `as_of` no earlier than the Approval decision time and no later than the
  current Founder confirmation/evaluation;
- use the exact execution currency;
- contain at least the approved execution amount.

No numeric freshness duration is invented. The current Founder confirmation is
the factual assertion that this selected post-Approval snapshot remains current
for the exact action at confirmation time. A known insufficient amount is
`BLOCKED`, not a Capital policy rejection, and no reserve is subtracted again.

### Founder Confirmation and Revocation

The confirming Founder identity must equal the Approval's Founder identity.
This explicit current confirmation closes the first-MVP intent check without
mutating Approval. ADR-0048 does not add revocation. If revocation becomes
operationally necessary, it remains a separate append-only authority and future
execution must check it.

### Market and Economics Rechecks

Execution safety does not rerun Domestic Market Validation, Conservative
Economics, Capital Readiness, Capital Requirement, or Capital Gate. Commercial
change follows the explicit new-Quote/new-chain rule. Broader reevaluation needs
a new policy decision rather than an implicit execution-time orchestration.

### State and Blocking Reasons

All required inputs are structurally mandatory. Named-source absence remains a
source error. Loaded complete facts can produce deterministic ordered blockers
for:

1. Approval/source lineage mismatch;
2. unsupported source or execution-safety policy;
3. Quote ID/revision mismatch;
4. missing Quote validity;
5. expired Quote;
6. execution amount mismatch;
7. execution quantity or unit mismatch;
8. currency mismatch;
9. current capital snapshot not post-Approval/currently confirmed;
10. insufficient current Deployable Capital;
11. Founder confirmation identity/time mismatch.

Exact reason names are an implementation detail but must remain versioned and
deterministically ordered. Execution safety has no `REJECTED` state because it
does not make a new investment-policy decision.

### Identity, Replay, and Cardinality

A dedicated server-owned opaque execution-intent identity is distinct from the
command fingerprint. Replay lookup precedes source reads, identity, and clocks.
Same command/same payload returns the exact historical result without rechecking
Quote time, capital, or confirmation. A current check requires a new command.

Blocked attempts do not consume the Approval and may be retried by a new command
with corrected exact facts. Once one READY intent exists for an Approval, v1
allows no second different READY action under that Approval. An equivalent
action may alias the existing READY intent; a changed action requires a new
Capital chain and Approval. This keeps one approved full-order action from
producing multiple authoritative execution tokens.

### Persistence

The intent must be committed before the Founder acts. Future persistence uses
append-only intent history and receipts, exact source manifests, atomic commit,
restart reconstruction, command replay, READY-per-Approval cardinality, and no
current/latest projection. This ADR does not implement that persistence.

### Manual Purchase Boundary

HYB presents the READY intent and exact Supplier/Product/Quote facts. The Founder
manually places the order outside HYB. HYB does not click Buy, transmit payment,
store credentials, or call a Supplier checkout API. The durable intent reduces
authoritative duplicate actions; physical duplicate clicks outside HYB remain a
human operational risk until external execution integration exists.

### Future Purchase Execution Record

A later immutable `PurchaseExecutionRecord` must bind one READY intent and its
Approval and preserve at least:

- dedicated execution-record identity;
- exact intent, Approval, Opportunity, Supplier/Product, and Quote references;
- actual ordered quantity/unit and committed amount/currency;
- external Supplier order reference;
- Founder/operator identity and actual execution time;
- evidence/reference and schema version.

The first MVP accepts only exact quantity, amount, currency, Supplier/Product,
and Quote agreement with the READY intent. Deviations are not silently accepted
or covered by a tolerance/override; they require a new decision chain. One READY
intent may have at most one authoritative Purchase Execution Record.

### Actual Economics Handoff

Current `ActualEconomics.record_purchase` stores only Opportunity, currency,
purchase price, shipping cost, and time and is gated by generic lifecycle
`PURCHASED`. It preserves no execution-intent identity, quantity, Supplier order,
evidence, or Capital lineage, so it cannot serve as the Purchase Execution
Record and must not be called directly from intent data.

The smallest future handoff is an exact source binding or admission from the
persisted Purchase Execution Record into Actual acquisition facts. Inventory and
Actual Economics/Variance may consume that bound record in later work; their
current contracts are unchanged by this decision.

### Production Sequence

The shortest safe production sequence is:

1. expose the missing Capital source commands needed to produce Capital
   Readiness, Intent/Deployable facts, Requirement, Gate, and Founder Approval;
2. implement and expose Real-Money Execution Intent;
3. present one READY intent for the Founder to execute manually outside HYB;
4. implement Purchase Execution Record admission;
5. add the exact Actual Economics/inventory handoff.

No generalized workflow engine is required.

## Consequences

- Historical Approval is never mistaken for execution-time safety.
- Exact quantity, amount, Quote, currency, current capital, and current human
  intent are checked without automation or inferred tolerance.
- READY intent becomes the durable idempotency bridge before an external manual
  side effect.
- Current Actual Economics remains isolated until exact execution provenance can
  be admitted safely.

## Deferred Work

1. Capital and Execution Intent production entry/API/UI wiring.
2. Purchase Execution Record authority and persistence.
3. Exact Purchase Execution-to-Actual Economics/inventory binding.
4. Append-only revocation only if first-MVP operations require it.
