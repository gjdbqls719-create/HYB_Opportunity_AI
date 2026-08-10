# ADR-0050 Purchase Execution Record Authority

## Status

Accepted

## Implementation Status

CR-1B5D2M implements the immutable Domain/Application authority, dedicated
opaque identity, append-only SQLite history/receipts, and the thin
Opportunity-scoped production API. Actual Economics binding, goods receipt,
inventory acquisition, checkout, payment, and supplier integration remain
unimplemented.

CR-1B7B2A implements ADR-0058 Purchase Execution policy `2.0.0`. V2 records the
actual source-currency supplier-order commitment and exact-matches it to the
READY v2 proposal without comparing it numerically to target-currency approved
capital. V1 remains immutable historical read/replay behavior.

## Context

ADR-0048 deliberately ends at `READY_FOR_MANUAL_EXECUTION`. READY proves that
one exact proposed purchase passed the execution-time safety policy; it does not
prove that the Founder placed the supplier order. HYB needs a separate factual
authority after the Founder performs that action outside HYB.

The existing Actual Economics purchase command is not this authority. It lacks
the execution-intent identity, quantity, Supplier/Product/Quote lineage,
external order reference, Capital lineage, and execution evidence. Marketplace
inventory observations likewise describe marketplace availability rather than
physical goods owned or received by HYB.

## Decision

### Authority and prerequisite

`PurchaseExecutionRecord` is an immutable fact meaning only that the Founder
reported this exact purchase was executed externally against this exact
persisted `READY_FOR_MANUAL_EXECUTION` intent. The caller must name the exact
intent ID; HYB never selects latest READY. BLOCKED or missing intents cannot
produce a compliant record.

The record does not prove supplier acceptance, final payment settlement,
shipment, customs clearance, receipt, owned inventory, listing, or sale. Those
must be separate future append-only facts.

### Exact-match v1 policy

The Founder supplies the new actual-world facts: actual quantity/unit, total
committed amount/currency, exact Quote ID/revision used, opaque external order
reference, Founder identity, actual execution time, request time, and one or
more evidence references. Supplier and Product identities are reconstructed
from the exact Sourcing Admission rather than accepted as duplicate claims.

Quantity, unit, amount, currency, Quote ID/revision, and Founder must exactly
equal the READY intent. A deviation is rejected and requires a new decision
chain. This authority has no DEVIATED state and no tolerance or override.

`executed_at` is caller-owned factual time and cannot precede READY evaluation.
`requested_at` is caller command time. `admitted_at` is the HYB server admission
clock, and `committed_at` belongs to the persistence receipt. All are
timezone-aware; replay reuses original authoritative times.

### External reference and evidence

The external order reference is required non-empty opaque text. It is neither
parsed nor used to derive identity. It is not globally unique because one
supplier order may contain multiple HYB opportunities. The durable cardinality
is instead one compliant record per READY intent.

Evidence is an immutable reference plus observation time. Domain objects do not
store screenshots or other binary content and do not require OCR.

### Identity, manifest, and state

The server issues a dedicated opaque UUIDv4-style record ID, never derived from
intent, Quote, external reference, row ID, or fingerprint.

The source manifest preserves O2, exact intent, Approval, Gate, Requirement,
Intended Quantity, Sourcing Admission/revision, Supplier/Product external
references, Quote/revision, execution-time Capital snapshot, exact expected
quantity/amount/currency, Founder, READY evaluation, and policy/schema versions.
Persistence reconstructs those exact historical sources.

The record has no mutable lifecycle state. Its existence is the execution fact;
PENDING, SHIPPED, RECEIVED, and CANCELLED do not belong to this authority.

### Cardinality, replay, and persistence

One READY intent has at most one compliant record, enforced by a SQLite unique
index within `BEGIN IMMEDIATE`. Same command and payload replay the exact record
and receipt. Same command with changed payload conflicts. A different command
describing the identical actual event aliases the existing record and adds only
a receipt; a different event competing for the same intent conflicts.

Dedicated history and receipt tables are append-only, integrity-fingerprinted,
schema-versioned, and atomically committed. UPDATE and DELETE are rejected.
There is no current/latest projection. Historical reads reconstruct persisted
sources but do not perform a current Quote or Capital check, Gate reevaluation,
or new execution-safety evaluation.

### Production boundary

`POST /api/v1/opportunities/{opportunity_id}/purchase-execution-records`
uses one request-owned SQLite connection, the production record identity
supplier, and `ProductionUTCClock`. Fresh commit is 201, replay/alias is 200,
conflicts are 409, missing intent is 404, invalid data is 422, and bounded
persistence failure is 503.

## Consequences

- READY and executed remain distinct, auditable authorities.
- HYB can join the first reported external money event to the complete O2
  Capital/Sourcing chain without mutating historical sources.
- Tests prove software admission behavior only. Real-world validation still
  requires a genuine Founder order and its real reference/evidence.
- Actual Economics may later consume actual quantity, amount, currency,
  execution time, O2, Supplier/Quote lineage, and evidence. It still needs
  separate actual shipping, duty/customs, FX settlement, sale, and fee facts.
- Purchase execution does not increase inventory. A future Goods Receipt or
  equivalent physical-receipt authority is required first.

## Relationship to ADR-0058

The v1 `actual_total_committed_amount/currency` remains readable and replayable
under its original exact-READY semantics and is never reinterpreted. V2 replaces
that ambiguous new-input meaning with explicit
`supplier_order_committed_amount/currency`, exact-matches it to the proposed
supplier-order money in execution-safety v2, and separately preserves the
authorized acquisition-capital envelope.

## Deferred Work

1. Real-world Founder validation with a genuine supplier order.
2. Exact Purchase Execution-to-Actual Economics acquisition binding.
3. Goods receipt and owned-inventory acquisition authority.
4. Shipment, customs, settlement, cancellation, sale, and variance facts.
5. Authentication, UI, or supplier/payment automation under separate decisions.
