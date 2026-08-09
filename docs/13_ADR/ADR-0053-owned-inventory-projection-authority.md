# ADR-0053 Owned Inventory Projection Authority

## Status

Accepted

## Implementation Status

CR-1B6B4 implements the historical receipt-only v1 Domain/read projection.
CR-1B6C3 adds the separate v2 Domain/read projection, deterministic COMPLETE
Actual Sale Settlement enumeration, and the current production GET response.
No mutable or materialized inventory table exists. Adjustments, reservations,
Actual Outcome, UI, and external integrations remain unimplemented.

## Context

ADR-0052 and CR-1B6B2 establish `GoodsReceiptRecord` as the immutable factual
event that exact goods physically arrived and were inspected. A receipt preserves
the O2 Opportunity, Purchase Execution, Supplier, sourcing product, external
product/option/SKU, quantity unit, and inspected sellable/damaged quantities.
One Purchase Execution may have multiple partial receipts.

Neither Purchase Execution nor Actual Acquisition Settlement proves receipt or
creates inventory. The historical `market_data.InventorySnapshot` observes the
availability of an external marketplace listing and is not HYB-owned stock.
Legacy `ActualEconomics` records one gross sale price and time but has no sold
quantity, exact sourcing-product identity, Goods Receipt lineage, fulfillment
event, cancellation/refund semantics, or inventory-decrement point. Therefore it
cannot be used as an outbound inventory source.

HYB needs a read model for the physical sellable quantity it currently owns. The
model must not become a second mutable truth, collapse variants, invent future
sales, or reinterpret financial and marketplace facts.

## Decision

### Projection meaning and authority

`OwnedInventoryPosition` is a deterministic, rebuildable derived view of
HYB-owned physical inventory for one exact O2 and sourcing-product lineage. It is
not independently admitted by a Founder and is never an authoritative manual
balance input.

Immutable source events remain authoritative. Deleting the projection or any
future cache and replaying all applicable immutable events under the same
projection policy must reproduce the same position.

### Exact projection key

The v1 `OwnedInventoryProductKey` is the following complete tuple copied from
committed Goods Receipt source manifests:

- `OpportunityIdentity` (`opportunity_id`, `discovery_reference`);
- `source_platform`;
- `supplier_id`;
- `sourcing_product_id`;
- `external_product_reference`;
- `option_reference`;
- `sku_reference`;
- `quantity_unit`.

Every component participates in grouping, including explicit `None` option/SKU
values. This reuses the existing exact Supplier/Product lineage. It does not
create a canonical product identity, infer product equivalence, or use title,
URL, Quote, latest Sourcing Admission, or marketplace item identity as a key.

A projection read must reject malformed source history in which one claimed key
has conflicting identity or unit facts. It must not merge near matches.

### Multiple Purchase Executions

Goods Receipts from multiple Purchase Execution Records aggregate only when the
complete `OwnedInventoryProductKey` is identical. O2 identity alone is
insufficient. Different Supplier, sourcing product, external product, option,
SKU, platform, or quantity unit produces a distinct position even if a human
believes the products are equivalent.

Aggregation never erases provenance. Every position preserves the ordered set of
contributing Purchase Execution Record IDs and Goods Receipt Record IDs, with
counts. Quote and Sourcing Admission lineage remains available through each
receipt source manifest rather than becoming part of the balance key.

### v1 source events and calculation

Before an authoritative outbound event exists, committed Goods Receipt Records
are the only v1 calculation source. For one exact key:

```text
total_received_quantity = sum(received_quantity)
total_sellable_received_quantity = sum(sellable_quantity)
damaged_received_quantity = sum(damaged_quantity)
outbound_quantity = sum(empty authoritative outbound event set) = 0
sellable_on_hand_quantity = total_sellable_received_quantity - outbound_quantity
```

The empty-set zero does not assert that a marketplace reported zero sales. It
states only that this policy has no admitted outbound inventory events. The
projection must not subtract planned, expected, scraped, latest, or otherwise
speculative sales.

`total_received_quantity` and `damaged_received_quantity` are cumulative receipt
facts. `sellable_on_hand_quantity` is the current physical sellable projection.
Damaged receipt quantity never enters sellable inventory and does not calculate a
financial loss, refund, return, replacement, or disposal.

### Received, sellable, and available are different

`received` means physically arrived. `sellable` means inspected as sellable at
receipt. `sellable_on_hand` means physical sellable inventory remaining under
this projection policy. `available` in legacy `InventorySnapshot` means an
external listing observation. These terms are not aliases and no synchronization
or reconciliation is implied.

### Outbound sale boundary

The exact event that decrements inventory is intentionally deferred. The next
Actual Sale Settlement authority decision must determine at least:

- the sale/settlement window and exact sold quantity;
- O2, exact product, Purchase Execution, and receipt applicability lineage;
- order, fulfillment, shipment, or settlement identity and decrement point;
- marketplace and payment fees;
- cancellations, refunds, returns, replacements, and partial fulfillment;
- advertising, fulfillment, and storage charges where financially applicable.

This ADR requires only a future outbound interface: an immutable event must name
the exact `OwnedInventoryProductKey`, positive quantity and matching unit, opaque
event identity, factual event time, exact sale/fulfillment source lineage, and
evidence. Legacy `ActualEconomics` is not adapted or reinterpreted for this role.

When outbound admission is implemented, the write authority must transactionally
reject or explicitly represent oversell according to its accepted policy. The
projection must never silently clamp a negative result to zero. A negative
rebuild from accepted events is malformed/unsafe history and must fail closed.

### Reservation and allocation boundary

v1 represents physical sellable on-hand only. It has no reserved, allocated,
committed-to-order, available-to-promise, safety-stock, or marketplace-published
quantity. Those are separate future dimensions with separate event and policy
decisions. No such quantity is inferred from Capital Approval, Execution Intent,
Purchase Execution, listing state, or an unfulfilled order.

### Representation and persistence

v1 is an on-demand event-derived Application read model. It reads immutable
Goods Receipt history, groups by the exact key, calculates integer totals, and
returns the result. No owned-inventory history/current SQLite table or mutable
balance column is introduced in v1.

If performance later requires materialization, that table is a disposable cache,
not a second consistency boundary. It must be fully rebuildable and must not
accept manual quantity writes. A future event writer may update such a cache in
the same transaction for read-after-write consistency, as ADR-0052 permits, but
receipt and outbound events remain the sources of truth.

### Projection policy and schema version

The minimum v1 contract is:

- policy name: `receipt-derived-owned-inventory`;
- policy version: `1.0.0`;
- response/schema version: `owned-inventory-position-v1`.

Every returned position identifies this policy and schema. A change to grouping,
event eligibility, arithmetic, or outbound interpretation requires an explicit
new policy version and compatible read behavior. Historical receipt events and
their policy/schema versions remain unchanged.

### v2 projection evolution

CR-1B6C3 preserves the v1 contract above and introduces a distinct current
production projection:

- policy name: `receipt-and-complete-sale-derived-owned-inventory`;
- policy version: `2.0.0`;
- response/schema version: `owned-inventory-position-v2`.

For one complete `OwnedInventoryProductKey`, v2 adds only terminal committed
`ActualSaleSettlement` events whose state is `COMPLETE`. It sums their explicit
`fulfilled_outbound_quantity`, ordered by normalized UTC `period_end` and then
settlement ID, and subtracts that total from sellable receipt quantity. BLOCKED
revisions contribute neither quantity nor source identity. A zero-sale COMPLETE
event contributes its settlement ID and outbound event count while contributing
zero quantity. Every position exposes separate inbound/outbound event counts and
the ordered COMPLETE settlement IDs.

The projection does not re-run overlap or oversell admission policy. A COMPLETE
sale without an exact receipt key, a non-COMPLETE value returned by the COMPLETE
read contract, duplicate source identity, or reconstructed negative balance is
malformed source history and fails closed. The existing production GET now emits
this explicit v2 contract; the v1 Domain owner remains callable with its original
receipt-only meaning.

### Determinism and rebuildability

Integer addition is performed over the complete committed event set for an exact
key. Source manifests are returned in deterministic order by normalized UTC
`received_at`, then Goods Receipt Record ID as the tie-breaker. Derived unique
Purchase Execution IDs retain first-contribution order, with ID as the tie-breaker
when event times coincide. Database row order, wall-clock read time, and a
`latest` selector never affect totals.

The projection consumes admitted Goods Receipt Records. It does not reproduce
receipt admission policy or independently resolve/revalidate Purchase Execution,
Quote, Capital, or settlement on every projection calculation. Persistence may
still perform its existing historical integrity checks while hydrating a receipt;
the projection owner adds no second admission check.

### Quantity safety and concurrency

Goods Receipt already transactionally enforces cumulative physical receipt not
exceeding the exact Purchase Execution quantity. The projection consumes only
committed receipts and does not add another receipt cardinality boundary.
Concurrent uncommitted events are absent from a read; a subsequent read includes
them after commit. Each returned total is a non-negative integer in one exact
unit.

### Actual Acquisition Settlement independence

Actual Acquisition Settlement is a parallel money fact. BLOCKED, COMPLETE,
missing, revised, or later settlement state has no effect on owned inventory.
The projection neither requires nor mutates settlement and never converts money
into quantity.

### Marketplace InventorySnapshot and Coupang independence

`market_data.InventorySnapshot` remains an independent external observation and
may disagree with `OwnedInventoryPosition` without either being rewritten.
Change Detection continues to compare external marketplace observations only.

The projection is marketplace-independent. It does not call Coupang, crawl a
listing, publish stock, reserve units, or synchronize a seller account. A future
Coupang adapter may consume an explicitly authorized inventory view but cannot
become this projection's source of truth.

### Production read boundary

CR-1B6B4 exposes the read-only Opportunity-scoped endpoint:

```text
GET /api/v1/opportunities/{opportunity_id}/owned-inventory
```

It returns zero or more positions because one O2 may contain multiple exact
product keys. A missing O2 is distinct from an existing O2 with no received
inventory. No POST/PUT/PATCH manual balance endpoint is permitted.

A position response should include:

- complete `OwnedInventoryProductKey` identity;
- total received, total sellable received, damaged received, authoritative
  outbound, and current sellable-on-hand quantities plus unit;
- Goods Receipt and Purchase Execution source IDs and counts;
- projection policy name/version and response schema version.

Any read timestamp is response metadata only and must not affect the position.
Exact source traceability is mandatory; a numeric balance without source IDs is
not sufficient for real-money use.

### First controlled MVP examples

One full undamaged receipt of 10 units yields total received 10, total sellable
received 10, damaged received 0, outbound 0, and sellable on-hand 10.

For one 100-unit purchase received in two events, 60 units classified as 58
sellable plus 2 damaged and then 40 units classified as sellable yields total
received 100, total sellable received 98, damaged received 2, outbound 0, and
sellable on-hand 98. Both receipt IDs remain visible.

### Future adjustments

Returns, loss, post-receipt damage, disposal, corrections, and audited manual
adjustments are not implemented. A future adjustment authority must be
append-only and preserve exact product key, signed effect or explicit direction,
positive quantity/unit, reason, operator, evidence, factual time, identity, and
policy version. It must not overwrite a balance or rewrite a Goods Receipt.

### Actual Outcome handoff

This projection supplies physical quantity facts only. Future Actual Outcome
must still bind the exact Purchase Execution, COMPLETE Actual Acquisition
Settlement, applicable Goods Receipt events, and authoritative Actual Sale
Settlement events. It must calculate economics independently and must not treat
sellable on-hand as revenue, loss, or profit.

## Consequences

- HYB gains one unambiguous rebuildable owned-inventory view without a second
  mutable source of truth.
- Exact Supplier/Product variants and quantity units cannot collapse at O2 level.
- Partial receipts and damage produce transparent cumulative quantities with
  source-level auditability.
- v1 provides truthful pre-sale sellable on-hand while refusing to invent an
  outbound decrement.
- Marketplace observations, acquisition settlement, Capital authorities, and
  legacy Actual Economics remain unchanged.
- The next sale authority must define outbound semantics before sold quantity
  can reduce this position.

## Deferred Work

1. Append-only inventory adjustments and reservation/allocation projections.
2. Actual Outcome and Conservative-vs-Actual Variance v2.
3. Optional rebuildable materialized cache, authentication, UI, and marketplace
   synchronization.
