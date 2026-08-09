# ADR-0051 Actual Acquisition Settlement Authority

## Status

Accepted

## Implementation Status

CR-1B6A2 implements the immutable Domain/Application authority, dedicated
actual evidence and FX-settlement facts, exact-predecessor append-only SQLite
revisions/receipts, production UUID identity, and the thin Opportunity-scoped
API. Goods Receipt, Owned Inventory v2, and Actual Sale Settlement are now
implemented downstream. ADR-0055 defines Actual Outcome, but its implementation,
Variance v2, and external settlement ingestion remain unimplemented.

## Context

ADR-0050 defines `PurchaseExecutionRecord` as the immutable factual handoff
after the Founder reports an exact externally executed purchase. Its committed
amount proves what the Founder committed at execution time. It does not prove
the final settled item amount, shipping, duty/customs, actual FX, physical
receipt, inventory, sale, or profitability.

The planned acquisition authorities preserve four normalized components:
`UNIT_PURCHASE`, `SUPPLIER_SIDE_SHIPPING`, `INTERNATIONAL_FREIGHT`, and
`DOMESTIC_INBOUND`. They use explicit allocation and FX sources to produce
per-unit planned values. They are not actual settlement facts and cannot be
copied or used as fallback.

The legacy `ActualEconomics` aggregate is also not this authority. Its one
`purchase_price` plus one `shipping_cost` has no Purchase Execution,
Supplier/Product/Quote, quantity, category-complete cost, actual FX, or evidence
lineage. Its sale and settlement lifecycle combines concerns that this decision
keeps separate.

HYB therefore needs a new authority that answers only: what did this exact
purchase ultimately cost HYB/the Founder to acquire, up to the defined
acquisition boundary, using actual settled facts?

## Decision

### Authority and exact source

`ActualAcquisitionSettlement` is the append-only factual assessment for the
actual acquisition side of one exact persisted `PurchaseExecutionRecord`.
Only a `COMPLETE` revision is the terminal actual acquisition settlement usable
by downstream authorities.

Every command names the exact Purchase Execution Record ID. The owner loads
that historical record and reconstructs its O2 Opportunity, Real-Money
Execution Intent, Founder Capital Approval, Capital Gate, Planned Requirement,
Intended Order Quantity, Sourcing Admission and revision, Supplier/Product,
exact Quote revision, executed quantity/unit, and external order reference.
There is no latest purchase selection and callers do not restate identities
that can be reconstructed.

The authority does not copy a planned cost, use a planned FX observation as an
actual fact, or infer that the Purchase Execution committed amount equals the
final settled item amount.

### Acquisition boundary and canonical categories

The v1 acquisition boundary ends after goods are brought through domestic
inbound logistics and all mandatory acquisition-side charges are settled. It
preserves these canonical categories independently and in this order:

1. `UNIT_PURCHASE`
2. `SUPPLIER_SIDE_SHIPPING`
3. `INTERNATIONAL_FREIGHT`
4. `DOMESTIC_INBOUND`
5. `DUTY_CUSTOMS`
6. `OTHER_MANDATORY_ACQUISITION`

The first four are the actual realized equivalents of the planned normalized
components. Duty/customs and other mandatory acquisition cost remain separate;
neither is merged into shipping or an undifferentiated total. Taxes or charges
outside this acquisition boundary require a later policy decision.

This authority does not calculate customs. Duty/customs is an observed settled
amount or an evidenced non-applicability fact.

### Batch amounts and quantity basis

Authoritative monetary inputs are batch totals scoped to the exact Purchase
Execution Record. The quantity and unit are reconstructed from
`PurchaseExecutionRecord.actual_quantity` and `actual_quantity_unit` and must
be preserved unchanged. MOQ, quoted quantity, another intent's planned
quantity, and received quantity are not settlement denominators.

The authority preserves every original category batch total. It may derive a
target-currency batch total and per-executed-unit amount for each category, then
sum those derived values. The Founder is never required to manually calculate
per-unit actual costs.

Per-unit division reuses the planned normalization arithmetic policy shape:
Decimal operands, a 34-significant-digit context, and `ROUND_HALF_EVEN`, with no
intermediate money quantization. This permits later category-level comparison
without changing either source. A future variance owner must still prove exact
planned-source lineage, currency, quantity unit, and compatible cost scope; it
must not treat category symmetry alone as comparability.

Received, damaged, and sellable quantities belong to Goods Receipt and may
differ from the executed quantity without changing this settlement basis.

### Category factual state

Each canonical category has exactly one state:

- `KNOWN`: an evidence-backed finite non-negative actual amount exists;
- `NOT_APPLICABLE`: evidence establishes that the category did not apply;
- `UNKNOWN`: the scoped actual fact remains unresolved.

`KNOWN` zero is a real observed zero and retains currency and evidence.
`NOT_APPLICABLE` carries no money and contributes an explicit derived zero only
after preserving its state and evidence. `UNKNOWN` carries no money, never
becomes zero, and blocks a `COMPLETE` revision.

Every known fixed category preserves its original batch amount, original
currency, occurred/settled time, evidence reference, operator, and collection
method. The actual item amount is independently required; equality with
`PurchaseExecutionRecord.actual_total_committed_amount` is allowed only when
evidence establishes that factual outcome.

### Other mandatory acquisition cost

`OTHER_MANDATORY_ACQUISITION` is not one arbitrary miscellaneous amount. In
state `KNOWN`, it preserves an immutable ordered collection of scoped items.
Each item has a non-empty scope name, original batch amount/currency,
occurred/settled time, evidence reference, operator, collection method, and any
required actual FX settlement. Duplicate item identities are rejected and the
source order is retained.

An evidenced zero is represented as a scoped zero item. If no other mandatory
acquisition cost applies, the category is `NOT_APPLICABLE` with scope and
evidence rather than an empty implicit zero. An unresolved possible item makes
the category `UNKNOWN` and blocks completion.

### Actual FX settlement

The settlement declares one explicit comparison/settlement target currency.
It is caller-selected and validated; KRW is not hardcoded even for the domestic
KR MVP.

Every known cross-currency cost has immutable actual FX settlement provenance
that preserves:

- original amount and source currency;
- target currency;
- exact settled/charged target amount when the provider exposes it;
- an explicitly applied actual rate when that is the available settlement fact;
- provider or payment channel, external reference, settled time, operator,
  collection method, and evidence reference;
- whether the normalized target amount is the observed target charge or was
  derived from an explicitly evidenced applied rate.

Completion requires enough actual settlement facts to determine the exact
target-currency amount: either the settled target amount or an explicitly
evidenced applied rate. When both original and target amounts are known, an
effective rate may be derived for comparison. A provider fee that is not
already included in the settled target amount must be preserved as a separate
other mandatory cost item; it cannot disappear into an inferred rate.

An actual FX settlement is payment/charge provenance, not a new external-market
`FXObservation`. Planned `FXObservation` records, live/latest rates, implicit
pair inversion, and default rates are forbidden.

For a cost already denominated in the target currency, the original amount is
the target amount and no FX record is present. The authority does not fabricate
a rate-of-one observation.

All monetary facts use finite non-negative `Decimal` values. Original facts and
derived target/per-unit values are preserved separately. Display or
currency-minor-unit rounding is outside this authority, and Founder-entered
money is never silently quantized.

### Completeness and append-only revisions

Settlement facts can arrive at different times, so v1 uses immutable,
append-only revisions rather than a mutable row or an incomplete value that is
silently overwritten.

Each revision has a server-owned opaque settlement ID, a positive revision
number, and an exact predecessor settlement ID except for revision 1. A
successor must be revision `N + 1`, must refer to the same Purchase Execution
Record, must preserve the initial target currency, and cannot fork an
already-used predecessor. One Purchase Execution Record owns at most one
settlement revision chain. The owner reconstructs the predecessor; it never
selects latest. Revisions preserve all prior known facts unless an explicitly
evidenced replacement is supplied, so history remains auditable.

The state is:

- `BLOCKED` when at least one canonical category is `UNKNOWN`, a required
  actual FX settlement is unresolved, or required evidence/provenance is
  incomplete;
- `COMPLETE` only when all six category scopes are exactly `KNOWN` or evidenced
  `NOT_APPLICABLE` and every cross-currency amount is exactly normalized into
  the target currency.

A `BLOCKED` revision is an authoritative assessment of current factual
incompleteness, not an actual cost usable by downstream decisions. A
`COMPLETE` revision is terminal: it has no successor under policy v1 and there
is at most one COMPLETE settlement per Purchase Execution Record. Downstream
authorities must name its exact settlement ID; they cannot ask for latest.

The Founder must not issue COMPLETE until the defined acquisition scope is
final. If contradictory or late evidence appears after COMPLETE, v1 does not
overwrite or silently supersede the record. Further downstream processing must
stop until a separate correction/amendment authority is accepted.

### Committed amount versus settled amount

`PurchaseExecutionRecord.actual_total_committed_amount` means what the Founder
committed externally when executing the exact READY purchase.
`ActualAcquisitionSettlement` means what ultimately settled across the complete
v1 acquisition scope. The item settlement may equal the committed amount, but
that equality is an evidence-backed actual outcome, never a fallback. The
all-in acquisition total can differ because of final item adjustment, shipping,
duty/customs, other mandatory cost, or actual FX settlement.

### Evidence, identity, and time

Actual money and non-applicability facts require external evidence references;
binary documents remain outside Domain payloads. Each factual source preserves
its external reference, factual occurred/settled timestamp, operator identity,
and collection method. UNKNOWN facts preserve an unresolved reason and the
checked source/reference when one exists.

Future implementation uses server-owned opaque settlement identities.
`requested_at` is the caller command fact, category and FX times are external
facts, `admitted_at` is the server clock, and receipt `committed_at` is the
persistence receipt clock. All times are timezone-aware. Exact replay returns
the historical record and original times.

### Source manifest and historical reconstruction

Each revision's source manifest preserves at least:

- O2 Opportunity identity and exact Purchase Execution Record ID;
- executed quantity/unit and external order reference;
- Supplier/Product and exact Quote/revision reconstructed from ADR-0050 lineage;
- canonical category states and actual category facts;
- actual FX settlement provenance;
- evidence, operator, collection method, policy/schema versions, predecessor,
  and timestamps.

Capital lineage already reconstructable through the exact Purchase Execution
Record is not redundantly accepted from the caller. Persistence must validate
the historical source and retain enough snapshot data to detect lineage drift
or corruption after restart.

### Separation from downstream authorities

Actual Acquisition Settlement does not prove physical receipt and does not
increase inventory. Received, damaged, and sellable quantities belong to a
separate future Goods Receipt authority.

It also excludes listing, sales, marketplace/payment/fixed fees, advertising,
returns/refunds, revenue, profit, margin, ROI, Actual Outcome, and Variance.
Those require separate future actual-sale and outcome authorities.

Legacy `ActualEconomics` remains unchanged and valid for its historical
behavior. Its `purchase_price` and `shipping_cost` are not the closed-loop v2
source of truth and are not populated or mutated by this authority. Future
Actual Outcome/Variance v2 will consume the new authorities additively and bind
one exact COMPLETE settlement.

## Consequences

- The exact executed purchase and its ultimately settled acquisition cost are
  distinct, auditable facts.
- Batch totals remain intact while deterministic per-unit actual values support
  future comparison to the four planned normalized categories.
- UNKNOWN, evidenced zero, and NOT_APPLICABLE cannot collapse into each other.
- Late-arriving facts can advance through exact append-only predecessors without
  mutable settlement data or latest selection.
- Actual FX settlement remains separate from planned market FX observations.
- No inventory, sale economics, profitability, or legacy ActualEconomics state
  changes as a side effect.

## Deferred Work

1. Actual Outcome and Conservative-vs-Actual Variance v2.
2. Post-COMPLETE correction/amendment authority if real evidence requires it.
3. Authentication, UI, payment/FX provider, supplier, or marketplace automation.
