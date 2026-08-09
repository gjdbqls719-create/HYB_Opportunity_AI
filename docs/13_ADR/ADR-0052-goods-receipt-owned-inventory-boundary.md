# ADR-0052 Goods Receipt and Owned Inventory Boundary

## Status

Accepted

## Implementation Status

CR-1B6B2 implements the immutable Domain/Application event authority, dedicated
evidence and UUID identity, append-only SQLite history/command receipts,
transactional cumulative over-receipt prevention, and the thin
Opportunity-scoped production API. Owned Inventory v2 and Actual Sale Settlement
are now implemented downstream. ADR-0055 defines Actual Outcome, but its
implementation, delivery exceptions, and external integrations remain
unimplemented.

## Context

ADR-0050 records that the Founder executed one exact purchase externally.
ADR-0051 records the actual acquisition-side money settled for that purchase.
Neither authority proves that goods physically arrived into HYB-controlled
possession, and neither may increase inventory.

The existing `market_data.InventorySnapshot` is not owned inventory. Its
`marketplace`, `source_url`, `item_id`, `available`, and optional `quantity`
fields describe external marketplace/listing availability at an observation
time. Change Detection compares those observations for a marketplace item.
There is no existing authority for HYB-owned physical stock, sellable stock, or
reserved/allocated stock. The historical type remains unchanged and must not be
renamed or reinterpreted.

HYB therefore needs a distinct factual inbound event after Purchase Execution.
It must record actual arrival and inspected condition without inferring receipt
from an order, payment, settlement, or marketplace observation.

## Decision

### Authority meaning

`GoodsReceiptRecord` is an immutable factual event meaning that a positive
quantity of the exact product bound to one persisted `PurchaseExecutionRecord`
physically arrived into HYB-controlled possession and was inspected with
explicit condition quantities and evidence.

It does not mean that goods were ordered, fully paid, fully delivered, listed,
reserved, sold, or synchronized with a marketplace. It does not calculate
financial economics, profit, margin, ROI, loss, or availability observations.

### Exact purchase source and product identity

Every command names one exact persisted Purchase Execution Record ID. The owner
loads that historical record; it never selects a latest purchase. From the
record it reconstructs and preserves at least:

- O2 Opportunity identity;
- Purchase Execution Record and Real-Money Execution Intent identities;
- Sourcing Admission identity and revision;
- Supplier identity, source platform, and external supplier reference;
- sourcing product identity and external product, option, and SKU references;
- exact Quote identity and revision;
- executed quantity and quantity unit;
- external order reference, Founder lineage, execution time, and source
  policy/schema versions.

The caller cannot substitute an Opportunity, Supplier, product, option, SKU,
Quote, quantity unit, or canonical identity. The existing O2 plus exact sourcing
product lineage is sufficient for v1; this decision creates no new canonical
product identity system.

### Receipt and financial settlement are independent

Purchase Execution, Actual Acquisition Settlement, and Goods Receipt are
separate real-world facts:

- `PurchaseExecutionRecord`: the exact external purchase was executed;
- `ActualAcquisitionSettlement`: actual acquisition-side money was settled;
- `GoodsReceiptRecord`: physical goods were received.

They may occur at different times. Physical receipt may precede or follow
financial settlement. A COMPLETE Actual Acquisition Settlement is not a Goods
Receipt prerequisite, and Goods Receipt neither requires nor mutates a
settlement. Existence of any one authority does not imply either of the others.

### Received quantity and unit

The caller supplies the factual `received_quantity`. It is a positive integer;
zero is not a receipt event. Missing delivery, failed delivery, or zero arrival
is absence of receipt and may require a separate future delivery-exception
authority rather than a fabricated zero-unit Goods Receipt.

`received_quantity_unit` is reconstructed from and must exactly equal the
Purchase Execution quantity unit. No conversion, MOQ quantity, Quote quantity,
planned quantity, or settlement denominator may be inferred or substituted.

### Partial and multiple receipts

One Purchase Execution Record may own multiple Goods Receipt Records. Each
record represents one independently evidenced arrival event. Partial shipments
are represented honestly by their received quantities; one purchase is not
assumed to equal one delivery.

A Goods Receipt does not assert that the complete purchase is fulfilled and has
no mutable `fulfilled` flag. A future aggregate may derive full arrival only
when cumulative received quantity equals executed quantity.

### Cumulative quantity safety

For one exact Purchase Execution Record:

`sum(all admitted received_quantity) <= executed_quantity`

v1 blocks an event that would exceed the executed quantity. Over-delivery is
not silently accepted, converted, or treated as free inventory. A separate
future exception authority and business policy are required before HYB can
admit over-receipt.

The future SQLite implementation must re-read the authoritative executed
quantity and cumulative immutable receipt history and enforce the invariant
inside the same `BEGIN IMMEDIATE` transaction that inserts the event and its
command receipt. An application-only precheck is insufficient.

### Condition and sellable quantity

Every v1 event records these explicit non-negative integer quantities:

- `received_quantity`;
- `sellable_quantity`;
- `damaged_quantity`, meaning received units confirmed damaged or otherwise
  unusable under the v1 receipt inspection.

v1 requires:

`sellable_quantity + damaged_quantity == received_quantity`

This is stricter than the minimum non-exceeding invariant and prevents an
unclassified remainder. v1 has no pending-inspection quantity or opaque
condition enum. The caller must inspect and explicitly classify every received
unit before admission. No received unit becomes sellable by default.

Damaged quantity is a physical condition fact. It does not alter Actual
Acquisition Settlement, calculate a loss, or initiate a refund, return, or
replacement. Those are separate future commercial events.

### Evidence and delivery reference

Every event requires one or more immutable, dedicated Goods Receipt evidence
references. Each reference preserves non-empty external reference text,
timezone-aware observation time, operator identity, and collection method.
Binary photos and documents remain outside Domain payloads.

The event also preserves the admitting operator. Existing Purchase Execution
and Actual Acquisition evidence types are semantically scoped to their own
facts and are not reused as Goods Receipt evidence.

An external delivery, carrier, or tracking reference is optional opaque text.
Some supplier and hand-delivery workflows have no standardized carrier ID. It
does not derive HYB identity, is not globally unique, and is not a v1
cross-command deduplication key.

### Time authority

The caller supplies factual `received_at`, required `inspected_at`, and command
`requested_at`. `inspected_at` cannot precede `received_at`. The server supplies
`admitted_at`; persistence supplies command-receipt `committed_at`. All times
are timezone-aware, and `admitted_at` cannot precede the receipt or inspection
fact. Exact replay preserves every original historical time.

### Identity, event semantics, and state

The server issues a dedicated opaque UUIDv4-style Goods Receipt Record ID. It
is never derived from the Purchase Execution Record, external order or delivery
reference, timestamp, database row ID, or fingerprint.

Goods Receipt is an append-only event, not a mutable snapshot. A valid admitted
record has no PENDING, COMPLETE, BLOCKED, RECEIVED, or FULFILLED lifecycle
state. Partial receipt is a quantity fact, not a state. The record stores no
current inventory balance.

### Replay, commands, and duplicate handling

The future authority follows these rules:

- same command ID and same payload returns the exact historical record and
  command receipt;
- same command ID with changed payload conflicts;
- different command IDs may create separate receipt events while cumulative
  quantity safety holds.

Delivery/tracking references and evidence references are not sufficiently
reliable universal external-event identities. v1 therefore does not merge or
alias different commands merely because one of those references matches. It
also does not claim cross-command duplicate detection. Cumulative quantity
safety remains mandatory, and stronger deduplication requires a later source-
specific decision.

### Owned inventory boundary

No owned-inventory projection exists today. A future
`OwnedInventoryPosition`, or repository-consistent equivalent, may derive an
O2 and exact sourcing-product position from immutable events:

`received sellable quantity - actual sold quantity +/- authorized adjustments`

Reserved/allocated quantity is a separate projection dimension and cannot be
inferred from physical receipt. Goods Receipt contributes only inspected
sellable inbound quantity; damaged quantity never enters sellable inventory.

The receipt event and its command receipt are the source of truth. Admission
must not mutate the unrelated marketplace `InventorySnapshot`. If a materialized
owned-inventory projection is introduced later, it should be updated in the
same transaction for read-after-write consistency but remain fully rebuildable
from immutable receipt, sale, and adjustment events. Projection absence or
rebuild must not weaken receipt cardinality enforcement.

### Marketplace and Coupang independence

Goods Receipt is marketplace-independent. It neither calls Coupang nor changes
any marketplace listing availability. A future marketplace sale authority may
consume or compare the same O2 owned-inventory lineage, but marketplace APIs,
crawling, and stock synchronization are outside this decision.

### Actual Outcome handoff

A future Actual Outcome must bind independently to:

- one exact Purchase Execution Record;
- one exact COMPLETE Actual Acquisition Settlement;
- the applicable immutable Goods Receipt Records;
- one or more future exact Actual Sale Settlement facts.

Goods Receipt contributes actual received, sellable, and damaged quantities.
It does not calculate revenue, costs, profit, margin, ROI, or variance. Legacy
`ActualEconomics` remains unchanged and is not populated or mutated by this
authority.

### First controlled MVP policy

The architectural authority supports partial and multiple receipts from day
one. The first controlled real-world validation may operationally choose one
complete, undamaged receipt where `received_quantity == sellable_quantity ==
executed_quantity` and `damaged_quantity == 0`. That operational constraint is
not a universal Domain rule and must not remove honest partial-receipt support.

## Consequences

- HYB gains an explicit physical-arrival boundary without treating order or
  payment facts as inventory.
- Partial shipments and damaged units remain factual, append-only history.
- No received unit becomes sellable without explicit inspection classification.
- Cumulative over-receipt is blocked transactionally against the exact executed
  quantity.
- Existing marketplace Inventory Snapshot and legacy Actual Economics semantics
  remain unchanged.
- Owned, sellable, and reserved inventory remain separate concepts; the future
  projection is derived rather than authoritative.

## Deferred Work

1. Authorized inventory adjustments and reservation/allocation projections.
2. Actual Outcome and Conservative-vs-Actual Variance v2.
3. Delivery exceptions, over-delivery exceptions, returns, refunds, and
   replacements.
4. Authentication, UI, warehouse automation, and marketplace synchronization.
