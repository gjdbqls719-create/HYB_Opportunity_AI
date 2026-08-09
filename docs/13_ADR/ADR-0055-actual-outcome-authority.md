# ADR-0055 Actual Outcome Authority

## Status

Accepted

## Implementation Status

CR-1B6D2 implements `ActualOutcome` as an immutable Domain result, a dedicated
Application calculation owner, append-only SQLite history and command receipts,
production UUID identity, and the thin Opportunity-scoped production API.
Exact acquisition, receipt, and sale source snapshots are frozen in the
manifest; replay and reads return persisted historical results without current
source recalculation. Variance v2 and calibration remain unimplemented.

## Context

HYB now has separate immutable authorities for one real-money commerce path:

- `PurchaseExecutionRecord` proves one exact external purchase and executed
  quantity;
- terminal COMPLETE `ActualAcquisitionSettlement` proves the final acquisition
  batch cost, canonical components, actual FX, and per-executed-unit basis;
- `GoodsReceiptRecord` proves received, inspected sellable, and damaged physical
  quantities;
- terminal COMPLETE `ActualSaleSettlement` proves fulfilled outbound quantity,
  realized sale-side money, finality, and explicit windows;
- `OwnedInventoryPosition` v2 derives current sellable on-hand from committed
  receipt and COMPLETE sale events.

None of these authorities answers what economic result has been realized. The
legacy mutable `ActualEconomics` lacks exact product, quantity, purchase,
receipt, and sale-window lineage and cannot be reinterpreted. Conservative
Economics is predicted unit economics and cannot supply actual values.

The remaining decision must distinguish realized sold economics from unsold,
damaged, returned, and not-yet-received capital. Charging the entire purchase
batch to a partial sale would understate the remaining asset. Redistributing
damaged cost over sellable units would change ADR-0051's per-executed-unit
meaning. Ignoring damaged or unreceived basis would hide real capital exposure.

## Current actual fact matrix

| Source | Authoritative facts available | Facts not supplied by that source |
| --- | --- | --- |
| Purchase Execution | exact O2/Supplier/Product/Quote lineage, executed quantity/unit, committed amount, external order | final acquisition cost, receipt, sale, profitability |
| COMPLETE Actual Acquisition Settlement | six acquisition categories, original and target-currency batch amounts, actual FX, total batch cost, per-executed-unit cost | physical condition, sold quantity, revenue |
| Goods Receipt | exact purchase/product lineage, received, sellable, damaged quantities, inspection evidence/times | financial recovery for damage, delivery exception, revenue |
| COMPLETE Actual Sale Settlement | fulfilled/cancelled/refunded/returned quantities, gross merchandise, shipping/support, discounts/tax, fees/refunds/advertising/fulfillment/storage/handling/other costs, payout reconciliation, currency, exact window | COGS, acquisition attribution, statutory seller tax, profit/ROI |
| Owned Inventory v2 | receipt totals, COMPLETE outbound, sellable on-hand, exact receipt/sale source IDs | money, lot allocation, damaged recovery, returned-stock condition |

Still unavailable are multi-purchase lot attribution, supplier recovery for
damaged goods, delivery-exception resolution for unreceived goods, returned-
stock inspection/re-entry, post-COMPLETE corrections, and authoritative seller-
side tax liability. Actual Outcome v1 must expose or block those gaps; it must
not infer them.

## Decision

### Authority meaning

`ActualOutcome` is an immutable, persisted, exact-source economic assessment of
realized commerce results for one O2, one complete
`OwnedInventoryProductKey`, one exact Purchase Execution, and an explicit
cumulative set of COMPLETE sale windows.

It derives quantities and money only from persisted authorities. It is not a
manual profit entry, planned estimate, acquisition or sale settlement,
inventory balance, payout alias, accounting ledger, statutory tax return,
profitability PASS/FAIL decision, or mutable dashboard calculation.

### Exact source prerequisites

A future command names:

- one exact Actual Acquisition Settlement ID;
- one non-empty ordered tuple of exact Actual Sale Settlement IDs;
- caller `requested_at` and supported policy/schema identifiers only where the
  established command pattern requires them.

The owner reconstructs and freezes:

- the terminal COMPLETE acquisition settlement and its exact Purchase Execution;
- O2, Supplier/Product/Quote and full `OwnedInventoryProductKey` lineage;
- every Goods Receipt for that Purchase Execution whose `inspected_at` is
  strictly before the explicit `evaluation_through` boundary;
- the complete committed COMPLETE-sale prefix for that exact product key through
  the selected terminal sale boundary;
- all component facts, currencies, quantities, windows, evidence references,
  and source policy/schema versions.

The caller cannot restate product identity, quantities, costs, revenue, COGS,
profit, margin, ROI, inventory, state, or blocking reasons. A transient
`OwnedInventoryPosition` is not a source ID.

No latest acquisition or sale source is selected. The terminal named sale and
explicit ordered set define the boundary. For a CALCULABLE result, the supplied
sale IDs must equal the complete committed COMPLETE-sale prefix for the key
through the maximum `period_end`; omission, duplication, reordering, or addition
of a later window is rejected. A named non-terminal revision produces BLOCKED
and contributes no tentative quantity or money. This prevents cherry-picked
cumulative outcomes.

### One-purchase v1 boundary

Actual Outcome v1 supports exactly one Purchase Execution and one terminal
COMPLETE Actual Acquisition Settlement. Every selected sale manifest must name
that same single Purchase Execution as its complete contributing purchase set.

If the exact product key has pooled receipts or selected sales from multiple
Purchase Executions, Outcome is BLOCKED with
`MULTI_PURCHASE_ALLOCATION_UNSUPPORTED`. v1 does not invent FIFO, LIFO,
weighted-average, or marketplace-order lot matching. A later ADR may add a
pool/lot allocation authority without changing this historical policy.

### Quantity basis and physical decomposition

ADR-0051's executed quantity remains the acquisition denominator. Actual
Outcome never redefines acquisition per-unit cost using received, sellable, or
sold quantity.

For the one exact purchase, all quantities use its exact unit:

```text
acquired_quantity = executed_quantity
received_quantity = sum(selected Goods Receipt received_quantity)
sellable_received_quantity = sum(selected Goods Receipt sellable_quantity)
damaged_quantity = sum(selected Goods Receipt damaged_quantity)
sold_quantity = sum(selected COMPLETE sale fulfilled_outbound_quantity)
remaining_sellable_quantity = sellable_received_quantity - sold_quantity
unreceived_quantity = acquired_quantity - received_quantity

acquired_quantity
= sold_quantity
+ remaining_sellable_quantity
+ damaged_quantity
+ unreceived_quantity
```

Negative values, unit mismatch, sales beyond sellable receipts, receipts beyond
executed quantity, or failure of this identity are source integrity conflicts.
The outcome does not re-run sale admission policy, clamp values, or repair
history.

### Cost-basis allocation and conservation

Each normalized acquisition category is allocated over ADR-0051's executed
quantity into four explicit buckets:

- recognized sold COGS;
- remaining sellable inventory cost basis;
- recognized damaged acquisition loss;
- unreceived acquisition cost exposure.

Preliminary bucket values use the authoritative per-executed-unit/category
basis multiplied by each integer quantity under the common Decimal policy. A
finite Decimal cannot exactly represent every integer division. Therefore the
calculation preserves exact batch conservation by assigning the final Decimal
allocation residual to the first non-zero bucket in this fixed order:

1. remaining sellable inventory;
2. unreceived exposure;
3. damaged loss;
4. sold COGS.

This order keeps rounding residue out of realized sold COGS while inventory or
unreceived exposure remains, and makes fully sold COGS equal the exact batch
total. The rule applies independently to every normalized category. Total
bucket amounts are then the sums of their category bucket amounts; they are not
separately divided a second time. Component and total traceability therefore
remain identical and reproducible.

For every category, and consequently for their summed total:

```text
acquisition batch amount
= sold COGS
+ remaining sellable basis
+ damaged loss basis
+ unreceived exposure basis
```

The allocation is accounting-policy arithmetic, not evidence that a specific
physical unit carried a different supplier price.

### Partial receipt and damaged goods

Full receipt is not required for calculability. Sold-unit economics can be
calculated from exact fulfilled outbound while unreceived purchased units remain
an explicit acquisition cost exposure. Unreceived cost is neither COGS nor a
loss; v1 has no delivery-exception or supplier-claim authority.

An inspected damaged unit has no sellable asset value under Goods Receipt v1.
Its allocated acquisition basis is recognized as damaged acquisition loss in
Actual Outcome v1. No supplier refund, reimbursement, replacement, salvage, or
return is inferred. If later evidence establishes recovery, downstream
processing stops until an accepted correction/recovery authority can represent
it; this outcome is not mutated.

Damaged cost is never redistributed across sellable units.

### Cumulative sale scope

v1 produces a cumulative outcome through one exact terminal COMPLETE sale
window. The source manifest contains all selected COMPLETE settlement IDs in
ascending UTC `period_end`, then settlement-ID order. Windows remain the
immutable non-overlapping scopes accepted by ADR-0054; Outcome does not merge or
rewrite them.

Adding a later COMPLETE window creates a new independent cumulative
ActualOutcome with a larger exact source set. Earlier outcomes remain unchanged.
One-window and zero-sale cumulative outcomes are valid.

### Realized revenue and sale-side component mapping

Outcome preserves every raw sale component total across the selected windows.
The calculation defines:

```text
gross realized merchandise revenue
= sum(gross_completed_merchandise_amount)

recognized sale credits
= gross realized merchandise revenue
+ buyer shipping credited to HYB
+ marketplace-funded discount support credited to HYB

recognized sale-side costs
= refunds
+ marketplace fee
+ payment fee
+ fixed fee
+ return-related fee
+ advertising
+ fulfillment
+ storage
+ distinct sale-side inbound/handling
+ ordered other sale-side costs

net realized sale contribution
= recognized sale credits - recognized sale-side costs
```

Seller-funded discount is already reflected in gross and is not deducted again.
Cancellation reversal for never-fulfilled sales is already excluded from gross
and is not deducted again. Both remain traceable explanatory facts. Acquisition
domestic inbound remains exclusively in Actual Acquisition Settlement and is
not copied into sale handling.

Refund and return monetary facts are used exactly as admitted; quantities and
money are not inferred from each other. Returned units do not become inventory
without a future inspected return/adjustment authority.

### Tax and payout

ADR-0054's customer tax/VAT collected fact is preserved but excluded from
recognized revenue and cost. The implemented source does not establish an
authoritative seller-side tax liability or whether HYB may retain a collected
amount. Actual Outcome v1 therefore reports realized operating economics before
unadmitted seller-side/statutory tax rather than inventing tax.

Payout amount and reconciliation state are preserved as source facts and
integrity evidence. Profit uses canonical components, never payout as a net-
revenue substitute. `NOT_SCOPE_COMPARABLE` payout remains valid because the
sale settlement already established component completeness.

### Actual realized profit

The authoritative v1 metric is scoped operating profit:

```text
actual_realized_profit
= net_realized_sale_contribution
- recognized sold COGS
- recognized damaged acquisition loss
```

It may be negative or zero and remains CALCULABLE. Remaining sellable and
unreceived cost basis are preserved capital exposures, not current expenses,
and are not arbitrarily charged to partial sales.

This is not statutory net income. It excludes unadmitted seller-side tax,
financing, general overhead, Founder labor, inventory adjustments, supplier
recoveries, and other scopes for which no current actual authority exists.

### Margin and actual acquisition ROI

`actual_margin` uses gross completed merchandise revenue as the denominator:

```text
actual_margin
= actual_realized_profit / gross_realized_merchandise_revenue * 100
```

It is explicitly unavailable when gross merchandise revenue is zero. No
Infinity, zero substitute, or exception invalidates the outcome.

`recognized_acquisition_basis` is sold COGS plus damaged acquisition loss.
`actual_acquisition_roi` is:

```text
actual_acquisition_roi
= actual_realized_profit / recognized_acquisition_basis * 100
```

It is explicitly unavailable when that basis is zero. When damaged loss is
non-zero, future comparison to Conservative Economics must mark the scope
difference rather than claim direct sold-unit symmetry.

### Zero sales and partial sales

A COMPLETE zero-sale window can produce a CALCULABLE ActualOutcome:

- sold quantity and sold COGS are zero;
- gross revenue may be evidenced zero;
- actual sale-side costs may be positive;
- damaged loss may be positive;
- profit may be zero or negative;
- margin is unavailable for zero gross;
- acquisition ROI is unavailable when recognized acquisition basis is zero;
- remaining and unreceived acquisition basis remain explicit.

Partial sale is equally valid. Remaining inventory does not BLOCK arithmetic and
the outcome does not claim full batch liquidation.

### Calculability and inventory resolution

Financial calculability and physical/batch resolution are separate dimensions.
Outcome state is derived:

- `CALCULABLE`: exact compatible sources make every v1 quantity and monetary
  result deterministic;
- `BLOCKED`: named sources are non-terminal, incompatible, incomplete, or need
  an unsupported allocation/correction policy. BLOCKED carries ordered reasons
  and no derived profitability metrics.

Negative economics and unavailable ratios do not cause BLOCKED.

A CALCULABLE outcome separately reports:

- `PARTIAL`: sellable on-hand, unreceived quantity, or returned-but-not-
  readmitted quantity remains;
- `FULLY_RESOLVED`: cumulative received equals executed, sellable on-hand is
  zero, and no selected settlement reports returned quantity awaiting a future
  physical-resolution source.

Damaged quantity is resolved as v1 damaged loss and does not by itself prevent
`FULLY_RESOLVED`.

BLOCKED reasons use this deterministic minimum order:

1. `ACQUISITION_NOT_COMPLETE`;
2. `SALE_SET_NOT_COMPLETE`;
3. `MULTI_PURCHASE_ALLOCATION_UNSUPPORTED`;
4. `CURRENCY_MISMATCH`;
5. `CORRECTION_REQUIRED`.

Missing source IDs, prefix/ordering omission, lineage mismatch, quantity
contradiction, and malformed persisted history remain not-found, conflict, or
source-integrity errors rather than business BLOCKED facts. Future implementation
may add a reason only when a newly accepted authority introduces a distinct
deterministic incompleteness.

### Currency contract

The COMPLETE acquisition settlement target currency and every selected sale
settlement currency must be identical. v1 performs no FX conversion and never
uses planned, provider, current, or latest FX. Currency mismatch is BLOCKED and
produces no profitability metrics.

### Source manifest and scope identity

The immutable source manifest preserves at least:

- O2 and complete `OwnedInventoryProductKey`;
- exact Purchase Execution and COMPLETE Actual Acquisition Settlement IDs;
- exact ordered Goods Receipt IDs included through the outcome boundary;
- exact ordered COMPLETE Actual Sale Settlement IDs and their windows;
- executed, received, sellable, damaged, sold, remaining, returned, and
  unreceived quantities plus exact unit;
- every acquisition and sale component/state, actual FX, payout/reconciliation,
  evidence, and source policy/schema version;
- `evaluation_start` as the minimum selected `period_start`,
  `evaluation_through` as the maximum selected `period_end`, outcome
  policy/schema, and all caller/server times.

The scope identity is the exact acquisition settlement ID, exact ordered sale
settlement set, reconstructed exact receipt set, product key, and outcome policy
version. Wall-clock calculation time and a transient current inventory response
are not identity inputs.

### Historical persistence, replay, identity, and time

ActualOutcome is a persisted immutable result, not a pure current read. Future
Variance and calibration must bind the exact historical policy, source set, and
values even after later sales or receipts exist.

The implementation uses an opaque server-owned outcome ID, append-only
result history, and command receipts. Replay is checked before source reads,
calculation, identity, or clocks. Same command ID and payload returns the exact
historical result. A changed payload conflicts. An equivalent exact source
manifest under the same policy owns at most one outcome; a different command may
receive an alias receipt for that same result rather than duplicate it.

There is no revision chain. A later sale window, newly reconstructed receipt, or
new policy creates a distinct outcome source manifest and result. Existing
outcomes are never updated.

`requested_at` is caller factual command time. `calculated_at` and
`committed_at` are server UTC times. Exact replay preserves original times.

### Decimal policy

All money and ratios use Decimal with precision 34 and `ROUND_HALF_EVEN`, with
no float and no intermediate presentation quantization. Quantities are strict
integers. Ratio unavailability is explicit rather than represented by NaN or
Infinity.

### Conservative Economics and legacy separation

ActualOutcome has no Conservative Economics dependency. It never copies an
expected sale price, planned fee, planned acquisition cost, planned FX, or
Conservative result. Future Variance v2 binds one exact Conservative Economics
result and one exact ActualOutcome result.

Legacy `ActualEconomics` and legacy Economics Variance remain historical
authorities with their current lifecycle and fields. They are not aliases,
fallbacks, migration sources, or write targets for ActualOutcome.

### Variance and calibration handoff

Future Variance v2 may compare semantically compatible exact sources:

- acquisition cost per executed unit;
- gross merchandise revenue per sold unit when sold quantity is positive;
- marketplace, payment, and fixed fees on a compatible unit/scope basis;
- profit, margin, and acquisition ROI only after proving compatible scope.

Actual-only refunds, advertising, fulfillment, storage, damage, shipping/support
credits, tax treatment, and other unmapped costs remain explicit scope
differences rather than being discarded. The outcome preserves sufficient
components and source IDs for later explanation and calibration, but this ADR
does not implement Variance or learning.

### MVP validation cuts

`Real-Money Validated MVP` means at least one genuine chain has:

- one real Purchase Execution;
- one genuine terminal COMPLETE Actual Acquisition Settlement;
- genuine Goods Receipt evidence;
- at least one genuine terminal COMPLETE Actual Sale Settlement;
- one CALCULABLE persisted ActualOutcome;
- exact one-O2/product/purchase lineage and actual money/evidence throughout.

It does not require all inventory to be sold and does not require Variance v2.
It proves the commerce fact loop, not repeatable profitability.

`Closed-Loop Learning MVP` is later and additionally requires one exact
Conservative Economics result and one Variance v2 result bound to that
ActualOutcome for the same lineage. Variance closes the learning loop; it is not
required to prove that the transaction itself happened and was measured.

The first controlled validation should use one O2, one exact purchase, preferably
full undamaged receipt, and one or more clearly closed manual Coupang settlement
windows. This is an operational risk-control shape, not a universal Domain
restriction or a product/spend selection.

### Future API direction

The implemented thin boundary is:

```text
POST /api/v1/opportunities/{opportunity_id}/actual-outcomes
```

The request supplies exact acquisition settlement ID, ordered exact sale
settlement IDs, command ID, and requested time. It accepts no manually supplied
financial result, COGS, inventory value, ratio, state, or reason. Fresh
CALCULABLE/BLOCKED results return 201, exact replay returns 200, and bounded
not-found/conflict/structural/persistence failures return 404/409/422/503.

## Arithmetic examples

For a full undamaged purchase of 10 units with a 100,000 KRW acquisition batch,
four units sold, 60,000 KRW recognized sale credits, and 10,000 KRW sale-side
costs:

```text
sold COGS = 40,000
remaining sellable basis = 60,000
actual realized profit = 60,000 - 10,000 - 40,000 = 10,000
actual margin = 10,000 / 60,000 * 100
actual acquisition ROI = 10,000 / 40,000 * 100 = 25
inventory resolution = PARTIAL
```

For the same purchase with nine sellable, one damaged, four sold, and five
remaining, cost-basis conservation is 40,000 sold COGS + 50,000 remaining basis
+ 10,000 damaged loss = 100,000. If only six units have been received as five
sellable plus one damaged, four sold, the same conservation includes 10,000
remaining basis, 10,000 damaged loss, and 40,000 unreceived exposure.

## Consequences

- Realized sold economics and unsold/unreceived capital are visible together
  without mixing their meanings.
- Damaged basis is not hidden or redistributed over sellable units.
- Partial receipt, partial sale, negative profit, and zero sales remain honest
  calculable outcomes.
- Exact cumulative source prefixes prevent latest selection and cherry-picking.
- The single-purchase boundary refuses unsupported lot attribution rather than
  guessing.
- Persisted immutable outcomes give Variance and calibration a stable source.
- Actual, Conservative, legacy ActualEconomics, inventory, and payout authorities
  remain separate.

## Deferred Work

1. Conservative-vs-Actual Variance v2 and calibration data products.
2. Multi-purchase lot/pool allocation policy.
3. Seller-side tax, damaged-goods recovery, delivery exception, returned-stock,
   correction, and inventory-adjustment authorities.
4. Coupang automation, authentication, UI, and generalized accounting exports.
