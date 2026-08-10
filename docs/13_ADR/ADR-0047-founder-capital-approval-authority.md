# ADR-0047 Founder Capital Approval Authority

## Status

Accepted

## Implementation Status

CR-1B5C implements the immutable Domain/Application authority, dedicated opaque
identity supplier, and append-only SQLite approval/receipt persistence.
CR-1B5D2L exposes the explicit exact-Gate Approval through production API and
keeps it separate from Gate evaluation and Execution Intent. UI, purchase, and
capital-deployment execution remain unimplemented.

## Context

ADR-0046 separates evidence readiness, Capital Gate policy, and human approval.
A Capital Gate `PASS` says only that one exact persisted decision may proceed to
Founder review. The existing generic `FounderDecision` binds no Gate, approved
amount, currency, requirement, deployable-capital source, or Capital policy and
therefore cannot authorize Capital deployment.

The Planned Acquisition Capital Requirement covers one immutable Intended Order
Quantity. The repository has no staged-release or partial-order authority. A
partial approval would therefore authorize a plan without proving that its
intended quantity can be purchased.

## Decision

### Authority and Meaning

Introduce `FounderCapitalApproval` as the final explicit human authorization
fact before any future real-money execution. Its meaning is:

> The named Founder explicitly authorizes the exact Capital Gate PASS decision,
> with the exact planned acquisition requirement as the maximum capital cap.

The existence of this valid immutable fact means approval. No `PENDING`,
`APPROVED`, or `REJECTED` state enum is added. Gate `PASS` never creates approval
automatically.

### Exact Gate Prerequisite

The Application command names one exact persisted Capital Gate ID. The owner
requires `PASS` and the supported `domestic-commerce-capital-gate` policy version
`1.0.0`, then copies its exact Opportunity, Capital Requirement, Deployable
Capital, Intended Order Quantity, Gate policy, and Gate evaluation time. It does
not select latest sources or rerun Readiness, Economics, Requirement, or Gate
policy.

### Approved Amount and Currency

Founder Capital Approval v1 requires:

```text
approved capital == exact Planned Acquisition Capital Requirement
approved capital <= exact Gate-evaluated Deployable Capital
approved capital > 0
approval currency == exact Gate Requirement/Deployable currency
```

Partial approval is not supported. It would imply staged release or a changed
order quantity, neither of which has an authoritative contract. The approved
amount is a hard cap for future execution; it is not evidence that funds were
transferred or spent. No FX or current cash lookup occurs.

ADR-0058 clarifies that this cap is a target-currency acquisition authorization,
not a prediction that the external supplier-order commitment has the same amount
or currency. V2 execution preserves the cap separately from supplier-order money.

### Founder, Identity, and Time

The caller supplies a factual non-empty Founder identity reference,
`requested_at`, and factual `approved_at`. This contract does not introduce
authentication or user management. Application-injected authorities issue a
dedicated opaque approval identity and `admitted_at`; the persistence receipt
owns `committed_at`. Replay precedes the Gate read, identity, and server clocks.

### Persistence and Replay

Approval history and receipts are immutable and append-only. Same command and
same complete payload returns the exact persisted approval and receipt. Changed
Gate, Founder, amount, currency, or approval time conflicts. Historical approval
continues to reference the exact Gate and source manifest even after new Gates,
capital snapshots, policies, or quotes exist.

### Revocation and Expiry

CR-1B5C adds neither mutable revocation nor an approval expiry duration. If
revocation becomes necessary it must be a separate append-only fact. No expiry
window is invented. This absence must not be interpreted as permission to execute
against stale commercial facts.

### Purchase Execution Boundary

Approval does not place an order, transfer funds, change Opportunity lifecycle,
or authorize autonomous purchasing. A future execution authority must name the
exact approval and independently verify current execution-time quote/order
validity, exact intended quantity, amount within the approval cap, revocation if
introduced, and idempotent execution identity before any external side effect.

## Consequences

- Human Capital authorization is separate from Gate eligibility and generic
  Opportunity approval.
- An exact full-order capital cap is reconstructible after restart.
- Partial funding, staged release, FX, and current-cash inference cannot enter the
  approval path accidentally.
- Approval remains historical evidence, not an execution command.

## Deferred Work

1. Production entry and API/UI for explicit Founder Capital Approval.
2. Implementation of ADR-0048 Real-Money Execution Intent and pre-execution
   safety contract.
3. Append-only revocation only if operational evidence requires it.
4. Authentication/identity assurance beyond the current caller-supplied factual
   Founder reference.
