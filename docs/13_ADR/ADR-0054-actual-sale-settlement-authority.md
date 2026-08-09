# ADR-0054 Actual Sale Settlement Authority

## Status

Accepted

## Implementation Status

CR-1B6C2 implements the immutable Domain/Application authority, exact Goods
Receipt/product reconstruction, append-only SQLite revision history and command
receipts, transactional window/reference/chronological oversell safety,
production UUID/time ownership, and the thin Opportunity-scoped API. Owned
Inventory v2 now consumes only committed COMPLETE settlement outbound through
CR-1B6C3. Coupang automation, Actual Outcome, Variance v2, corrections, and
returned-stock admission remain unimplemented.

## Context

ADR-0050 records one exact externally executed purchase. ADR-0051 records its
actual acquisition-side settlement. ADR-0052 records physical receipt and
inspection, and ADR-0053 derives receipt-only owned inventory for one exact O2
and sourcing-product key. None records actual marketplace sales, authoritative
inventory outbound quantity, or realized sale-side costs.

The legacy `ActualEconomics` aggregate cannot fill that gap without changing its
historical meaning. Its exact audit is:

| Capability | Existing meaning | Classification for closed-loop v2 |
| --- | --- | --- |
| gross sale | one `sale_price`, documented as gross before three fees | A: the gross-before-fee concept is understandable, but the value is not reused as a v2 source |
| marketplace/payment/fixed fee | three required non-negative amounts on one settlement transition | A: the category names remain useful only where actual evidence proves matching semantics |
| payout | one preserved `settlement_amount`, intentionally not reconciled | A: preserve-as-fact behavior is reusable; the legacy value is not |
| quantity and unit | absent | B: structurally insufficient |
| multiple transactions and windows | one sale transition per mutable Opportunity aggregate | B: structurally insufficient |
| Coupang order/report/account references | absent | C: missing |
| refunds, cancellations, and returns | absent | C: missing |
| advertising, fulfillment, and storage | absent | C: missing |
| exact O2/product/receipt lineage | Opportunity ID only | D: incompatible with exact closed-loop inventory lineage |
| completeness and corrections | fixed lifecycle ending in one mutable `SETTLED` state | D: incompatible with evidence-progressive immutable revisions |

The planned `FeeProfile`/`FeeBreakdown` service is also not an actual source. It
calculates fees from profiles or overrides, uses presentation quantization, and
has no authoritative Coupang settlement contract. Existing variance compares
the legacy fields only and explicitly becomes unavailable when currency or cost
scope differs. These authorities remain unchanged.

The repository has Coupang artifact provenance and domestic-market evidence,
but no Coupang sale, order, payout, or fee adapter whose semantics could safely
be adopted. The first real validation therefore requires manual, evidenced
actual facts without network inference.

## Decision

### Authority meaning

`ActualSaleSettlement` is an immutable, evidence-backed assessment of actual
marketplace sales and realized sale-side monetary facts for one exact O2,
`OwnedInventoryProductKey`, marketplace seller scope, and explicit historical
evaluation window. Only a `COMPLETE` revision is the terminal settlement and an
authoritative inventory-out source.

It is not a forecast, listing or inventory snapshot, order-created signal,
planned sale price, profitability calculation, Capital authority, marketplace
synchronization, or mutable current total. It does not calculate final profit,
margin, ROI, or variance.

### Marketplace-generic authority and first Coupang path

The Domain remains marketplace-generic. Every settlement carries an explicit
marketplace code, with the first controlled path using `COUPANG`, plus a
marketplace seller-account/store reference and source-specific opaque
references. Coupang report terminology belongs in evidence and future adapter
mapping, not a Coupang-only Domain subtype.

No current repository contract proves a Coupang-specific payout formula that
would invalidate this generic boundary. Consequently v1 neither hardcodes a
Coupang formula nor calls a Coupang API. A later adapter may translate verified
Coupang exports into this authority but cannot redefine its facts.

### Exact O2 and product source

A future Opportunity-scoped command names one exact committed
`GoodsReceiptRecord` as the product-lineage anchor. The owner reconstructs its
O2 and the complete ADR-0053 `OwnedInventoryProductKey`:

- `OpportunityIdentity` (`opportunity_id`, `discovery_reference`);
- source platform and Supplier ID;
- sourcing product ID;
- external supplier product, option, and SKU references;
- quantity unit.

The owner rejects an anchor outside the route O2 and never accepts title,
Opportunity-only identity, a caller-restated partial key, or a transient
`OwnedInventoryPosition` result/ID as authority. The settlement additionally
preserves the marketplace selling product, option, and SKU references reported
by the sale evidence. Those references document the sold listing but do not
replace the owned-inventory key.

All committed Goods Receipt and Purchase Execution IDs eligible for the exact
key through the evaluation boundary are reconstructed and preserved in the
source manifest. Receipts from multiple Purchase Executions may contribute only
when the complete key is identical. Different option, SKU, product, Supplier,
platform, or quantity unit always produces a separate settlement and inventory
position.

### Batch/window model and scope identity

v1 uses one Founder-admitted settlement batch rather than one Domain event per
customer order. The batch minimizes manual entry while retaining an exact
marketplace report/cycle identity, immutable source evidence, aggregate
quantities, and optionally ordered transaction/order references.

Every chain has an immutable half-open evaluation window `[period_start,
period_end)`, where both times are timezone-aware and `period_start <
period_end`. There is no implicit current month, rolling latest window, or
caller-selected latest settlement. It also has an immutable external
settlement/report/cycle reference.

The chain identity is the tuple of marketplace, seller-account/store reference,
external settlement/report/cycle reference, and complete
`OwnedInventoryProductKey`. The external reference may appear once per product
within the report because one report can contain multiple product lines.

For the same marketplace, seller account, and exact product key, v1 rejects an
overlapping active or COMPLETE window even when external cycle references
differ. Adjacent half-open windows are allowed. Multiple non-overlapping windows
over time are allowed and remain separate chains. Optional transaction/order
references, when the source exposes them, are ordered, preserved, and cannot be
reused by another chain for that marketplace account and product. Their absence
does not weaken the required report/cycle identity, non-overlap rule, or
evidence.

### Quantity facts and inventory outbound point

The batch preserves explicit non-negative integer facts in the exact
`OwnedInventoryProductKey.quantity_unit`:

- `fulfilled_outbound_quantity`: units that physically left HYB-controlled
  sellable possession within the window and are confirmed as completed,
  non-cancelled fulfillment by the final source scope;
- `cancelled_quantity`: units cancelled before authoritative outbound;
- `refunded_quantity`: fulfilled units receiving any refund, with money impact
  separately recorded;
- `returned_quantity`: fulfilled units evidenced as returned to a seller or
  fulfillment location.

`refunded_quantity` and `returned_quantity` cannot exceed fulfilled outbound
quantity. They can differ because a refund need not return a unit and a return
need not yet have a final monetary refund. Cancellations before outbound never
decrement inventory. Refunds and returns do not reverse the original outbound
fact. A returned unit can increase sellable inventory only through a future
inspected return-receipt or inventory-adjustment authority; this settlement
cannot assume its condition.

A `COMPLETE ActualSaleSettlement` is the smallest safe v1 authoritative outbound
event. Its `fulfilled_outbound_quantity` is effective as an aggregate inventory
change at `period_end`; `settled_at`, payout time, admission time, order creation,
and payment acceptance are not physical decrement points. The period-end rule
does not claim every unit departed at that instant. It states that evidence
proves the aggregate departed within that closed window and supplies a
deterministic ordering boundary for a batch projection.

Only COMPLETE settlements contribute outbound quantity. BLOCKED revisions
contribute zero even if they contain tentative quantity facts. Delayed manual
admission can therefore make a receipt-only/current read temporarily overstate
inventory until the terminal settlement is recorded, which is acceptable for
the first controlled validation but not a real-time fulfillment system. If HYB
later requires order-time reservation or real-time shipment visibility, that
requires separate allocation/fulfillment authority and does not change this
historical settlement.

### Inventory eligibility and oversale safety

The future owner reconstructs committed Goods Receipts for the exact key whose
inspection was completed before each applicable outbound boundary, preserves
their IDs and Purchase Execution IDs, and validates the candidate COMPLETE
revision against immutable inbound and every COMPLETE outbound fact:

```text
sum(COMPLETE fulfilled_outbound_quantity through any event boundary)
<=
sum(eligible GoodsReceiptRecord.sellable_quantity through that event boundary)
```

An all-time totals check alone is insufficient because an earlier window may be
admitted after a later one. The candidate is inserted into the complete
chronological event sequence and the balance must remain non-negative at every
period-end boundary, including already-admitted later windows. Goods Receipt
eligibility uses `inspected_at < period_end`; COMPLETE batches sharing one
boundary are summed before the boundary balance is accepted.

The comparison is global for the exact product key across marketplace sources;
marketplace-specific windows cannot independently spend the same units. The
future SQLite implementation must serialize the source re-read, overlap and
deduplication checks, full chronological cumulative calculation, terminal
revision insert, and command receipt in one write transaction. Application-only
prechecks are insufficient. It rejects pre-order/backorder and oversale in v1
and never clamps a negative balance to zero.

### Monetary fact availability

Every canonical monetary scope has one explicit availability state:

- `KNOWN`: a non-negative Decimal amount, explicit currency, factual time, and
  evidence are present; explicit zero means evidenced zero;
- `NOT_APPLICABLE`: no amount is carried, but a reason and evidence prove that
  the category does not apply to this exact scope;
- `UNKNOWN`: no amount is carried and the unresolved scope blocks COMPLETE.

`UNKNOWN`, evidenced zero, and `NOT_APPLICABLE` never collapse into one another.
`NOT_APPLICABLE` contributes a derived zero only after its distinct state and
evidence are preserved. Planned economics, configured fee rates, marketplace
defaults, prior windows, and payout residuals are never fallbacks.

### Gross sales, shipping, tax, and discounts

The canonical gross fact is `gross_completed_merchandise_amount`: marketplace
merchandise proceeds credited to the seller for fulfilled units in the window,
after seller-funded coupons/discounts, before refunds and sale-side fees, and
excluding buyer shipping and customer tax/VAT. It is always `KNOWN`, including
an evidenced zero for a zero-sales window, and is never derived from quantity
times a planned price.

The authority separately preserves availability-aware:

- buyer shipping charge credited to the seller;
- marketplace-funded coupon/discount support credited to the seller;
- seller-funded discount amount, as an explanatory fact already reflected in
  gross and therefore not deducted a second time;
- tax/VAT collected, identifying whether HYB received it or the marketplace
  collected/remitted it as a pass-through.

Tax/VAT is not silently treated as revenue or sale-side cost. A future Actual
Outcome must apply an accepted tax scope rather than infer it from payout.
Canceled-before-fulfillment transactions are excluded from gross and outbound.

### Refunds, cancellations, returns, and finality

The settlement preserves refund amount as its own canonical monetary fact and
cancellation-reversal amount as a separate report/reconciliation fact. Refund
amount represents settlement debits against previously completed merchandise
proceeds and is available to future outcome calculation. A cancellation
reversal for a never-fulfilled sale is not deducted again because that sale is
already excluded from canonical gross. Return-related fees are a separate cost
category.

Quantity facts, monetary facts, and ordered source references remain separate;
money is never divided by price to infer a quantity. Partial refunds are
represented by the exact money amount while `refunded_quantity` counts distinct
fulfilled units affected by any refund.

COMPLETE requires an evidenced `finality_observed_at` and attestation that the
chosen report/evaluation scope is sufficiently closed under the actual source:
no unresolved cancellation, refund, return, chargeback, or replacement remains
for the batch. v1 defines no arbitrary return-age duration and does not claim
universal marketplace finality. If the source cannot support that attestation,
the chain remains BLOCKED. Replacement fulfillment is outside v1; a scope with
an unresolved or unrepresented replacement remains BLOCKED.

### Canonical realized sale-side costs

The following categories remain separate and availability-aware:

- marketplace commission/service fee;
- payment processing fee;
- fixed per-order/per-settlement fee;
- return-related fee;
- product-attributable advertising spend for the window;
- fulfillment service charge;
- storage charge;
- sale-side marketplace inbound/handling charge;
- ordered other mandatory sale-side cost items.

Payment or fixed fee may be evidenced `NOT_APPLICABLE` when the marketplace
absorbs it or exposes no distinct category; the system does not invent one for
comparison symmetry. Advertising may be `NOT_APPLICABLE` only when evidence
shows no applicable campaign/spend, not merely because attribution is difficult.
Unattributed or unresolved material spend is `UNKNOWN`.

Sale-side marketplace inbound/handling is allowed only when evidence proves a
distinct marketplace service delivered for the sale scope. Supplier/domestic
inbound already owned by Actual Acquisition Settlement is never copied here.
Other costs are an immutable ordered collection with a non-empty category/name,
amount, currency, factual time, and evidence rather than one opaque
miscellaneous total. The completeness of the other-cost scope itself must be
attested; an empty collection is valid only with evidence.

### Payout and reconciliation

Actual marketplace payout/settlement amount, external payout reference, payout
time, and evidence are preserved when available. The payout is a terminal source
fact and integrity aid, not a replacement for gross, fee, refund, advertising,
fulfillment, storage, or other components.

For a source whose payout scope exactly matches the product/window components,
the authority may preserve a `RECONCILED` result against:

```text
gross completed merchandise
+ buyer shipping credited
+ marketplace-funded support
- refunds
- marketplace fee
- payment fee
- fixed fee
- return-related fee
- advertising
- fulfillment
- storage
- distinct sale-side inbound/handling
- ordered other sale-side costs
```

Seller-funded discount is already reflected in gross, cancellation reversals
are already excluded from gross, and collected/remitted tax is outside this
expression. The expression is a reconciliation aid, not profit.

Marketplace payouts can include reserves, prior-period adjustments, account-
level items, or different timing. In that case the payout may be evidenced
`NOT_APPLICABLE` to this product evaluation scope or the reconciliation state
may be `NOT_SCOPE_COMPARABLE`, with an explicit explanation and evidence.
`UNRESOLVED` reconciliation blocks COMPLETE. No equality is fabricated by
assigning the residual to another fee.

### Currency and arithmetic

Every settlement has an explicit three-letter settlement currency. All KNOWN
v1 component amounts must already be factual in that same currency. A
cross-currency report remains BLOCKED until a separate actual sale-side FX
settlement policy exists. Planned FX observations are never reused.

All monetary arithmetic uses Decimal operands, a 34-significant-digit context,
and `ROUND_HALF_EVEN`, with no float and no intermediate presentation
quantization. Original batch amounts are preserved.

### Completeness and append-only revisions

Facts may arrive progressively, so one immutable scope owns an append-only,
exact-predecessor revision chain. Each revision has a server-owned opaque ID, a
positive revision number, and, except revision 1, the exact predecessor ID.
Successors must be `N + 1`, cannot fork a used predecessor, and cannot change
the scope identity, period, O2/product key, marketplace seller scope, quantity
unit, or settlement currency. The owner reconstructs the named predecessor; it
never selects latest.

State is derived, never caller-selected:

- `BLOCKED` when any canonical quantity, finality, source/evidence, inventory,
  cost-scope, payout/reconciliation, or required monetary fact is unresolved;
- `COMPLETE` only when all quantity facts are explicit, gross is KNOWN, every
  other required monetary scope is KNOWN or evidenced NOT_APPLICABLE, other
  costs are closed, finality is evidenced, currency is consistent, source
  lineage is complete, and transactional overlap/deduplication/oversale checks
  pass.

BLOCKED is an authoritative statement of incompleteness, not a usable sale or
inventory event. A successor cannot regress a KNOWN fact to UNKNOWN or silently
erase it. Evidence-backed corrections before terminality preserve the original
revision and record an explicit replacement reason.

COMPLETE is terminal under v1: there is at most one COMPLETE revision per
scope, and it has no child. If contradictory or late marketplace evidence
appears afterward, history is not mutated and downstream processing stops until
a separate future `SaleSettlementCorrectionEvent` or equivalent authority is
accepted. The first MVP must therefore use a sufficiently final report; this
operational restriction does not assert corrections never occur.

### Identity, time, source manifest, and evidence

Future implementation uses server-owned opaque settlement IDs, command IDs,
server UTC admission/receipt times, replay-first command receipts, and
timezone-aware factual times. Same command ID plus identical payload returns
the exact historical revision and receipt; changed payload conflicts.

Every revision's immutable source manifest preserves at least:

- O2 and complete `OwnedInventoryProductKey`;
- anchor and eligible Goods Receipt IDs plus contributing Purchase Execution
  IDs;
- marketplace, seller account/store, selling product/option/SKU, external
  settlement/report/cycle, payout, and optional ordered transaction references;
- evaluation window, finality observation, fulfilled/cancelled/refunded/returned
  quantities and unit;
- every proceeds, discount, tax, fee, refund, advertising, fulfillment,
  storage, other-cost, payout, and reconciliation fact/state;
- evidence, operator, collection method, policy/schema versions, predecessor,
  and all factual/server times.

Every quantity, money, N/A assertion, finality assertion, and source mapping has
dedicated evidence references. Suitable first-MVP sources include Coupang
settlement/order reports, sales dashboard exports, fee statements, ad-spend
statements, and Founder-reviewed manual evidence. Binary CSV files, screenshots,
and documents remain outside Domain payloads; immutable references and
provenance remain inside. Founder-entered or CSV-derived structured values are
permitted. Collection method does not change the fact's semantics.

### Owned Inventory v2 direction

ADR-0053 v1 remains unchanged and receipt-only under
`receipt-derived-owned-inventory / 1.0.0`. After this authority is implemented,
a new projection policy may be introduced as:

```text
receipt-and-complete-sale-derived-owned-inventory / 2.0.0

sellable_on_hand
= sum(GoodsReceiptRecord.sellable_quantity)
- sum(COMPLETE ActualSaleSettlement.fulfilled_outbound_quantity)
```

The projection uses period-end event ordering, refuses negative rebuilds, and
does not subtract BLOCKED revisions. Refunds and returns do not add stock.
Version 2 must be a new compatible read behavior; it cannot reinterpret or
silently change historical v1 responses.

### Actual Outcome and conservative comparison handoff

Future Actual Outcome v2 must independently bind:

- the exact Purchase Execution sources relevant to the sold product;
- exact COMPLETE Actual Acquisition Settlement sources;
- applicable Goods Receipt/inventory truth;
- one or more exact COMPLETE Actual Sale Settlement windows.

This settlement supplies original batch totals. Future Outcome may divide a
compatible amount by `fulfilled_outbound_quantity` for sold-unit economics; the
Founder never pre-divides it. When fulfilled quantity is zero, the factual
zero-sales window may still be COMPLETE and useful for calibration, but sale
per-unit amounts, margin, and sold-unit ROI are explicitly unavailable rather
than forced to zero.

Partial sale is valid. Unsold units remain in Owned Inventory and a settlement
does not require an entire purchase batch or all received stock to sell. The
future Outcome ADR must decide sold-unit, purchase-batch, or campaign/window
evaluation and acquisition-lot attribution when multiple Purchase Executions
contribute; this authority preserves the source IDs without guessing that
policy.

For future Conservative-vs-Actual comparison:

- expected sale price maps only to a semantically compatible per-unit gross
  completed merchandise basis;
- marketplace, payment, and fixed fees map category-by-category only where
  their actual meanings match;
- acquisition cost, duty, and acquisition logistics come from COMPLETE Actual
  Acquisition Settlement, not this record;
- refunds, advertising, fulfillment, storage, tax treatment, support credits,
  and unmapped sale-side costs remain explicit scope differences;
- profit, margin, and acquisition ROI are derived only by future Actual Outcome
  and Variance v2.

No field is forced into legacy comparison symmetry and legacy
`ActualEconomics`/Economics Variance remains unchanged.

### First controlled real-world path

For the first O2, the Founder receives and inspects sellable units, sells the
exact variant on Coupang, chooses one bounded non-overlapping evaluation scope,
collects sales/fee/refund/cancellation/advertising/fulfillment/storage/payout
evidence, and submits structured facts. Revisions remain BLOCKED until the
scope is sufficiently final and every required fact is KNOWN or evidenced
NOT_APPLICABLE. A terminal COMPLETE revision then becomes both the actual
sale-side settlement source and the historical outbound source for future
Owned Inventory v2 and Actual Outcome.

The future production direction is:

```text
POST /api/v1/opportunities/{opportunity_id}/actual-sale-settlements
```

This ADR adds no route, automation, crawler, UI, or authentication behavior.

## Consequences

- HYB gains a truthful sale-side boundary without inferring sales or costs from
  planned economics, availability observations, or payout residuals.
- A batch/window model limits Founder entry burden while exact source identity,
  evidence, non-overlap, and optional transaction references preserve audit.
- COMPLETE settlement can safely supply the first historical outbound event;
  real-time reservations and fulfillment remain separate concerns.
- Zero sales, partial sales, refunds, and returns remain explicit without
  fabricating per-unit economics or inventory restoration.
- Unknown material costs fail closed, and planned fee profiles never become
  actual facts.
- Existing Purchase Execution, Actual Acquisition Settlement, Goods Receipt,
  Owned Inventory v1, legacy Actual Economics, and Variance behavior remain
  unchanged.

## Deferred Work

1. Actual Outcome v2, acquisition-lot attribution, and Conservative-vs-Actual
   Variance v2.
2. Post-COMPLETE sale correction, returned-goods inspection, inventory
   adjustment, replacement, reservation, and real-time fulfillment authorities.
3. Coupang import adapter/API integration, authentication, UI, and automated
   evidence collection.
