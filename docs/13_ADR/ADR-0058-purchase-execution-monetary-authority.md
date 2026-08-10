# ADR-0058: Purchase Execution Monetary Authority

## Status

Accepted

## Implementation Status

Decision only. CR-1B7B2 defines the monetary authority and forward v2
contracts. Current production Real-Money Execution Intent and Purchase
Execution remain v1 and are not safe for the supported cross-currency first
purchase until the implementation PR completes.

## Context

The supported O2 production chain can start with a CNY Supplier Quote, normalize
the complete planned acquisition scope into KRW, calculate a KRW Planned
Acquisition Capital Requirement, and obtain a KRW Founder Capital Approval.

The current v1 chain then requires:

```text
Planned Requirement amount/currency
== Founder Approval amount/currency
== Execution Intent planned amount/currency
== Purchase Execution actual committed amount/currency
```

The first three values describe one approved planned acquisition-capital
envelope. The final value is named as an actual external monetary event. For a
500 CNY supplier checkout under a 110,000 KRW acquisition plan, v1 can admit
only a fabricated 110,000 KRW "actual" purchase or reject the genuine 500 CNY
fact. Same-currency numerical equality does not make these authorities
semantically identical.

ADR-0051 already keeps execution-time commitment separate from final actual
acquisition settlement and forbids planned or execution values as settlement
fallbacks. This decision preserves that separation.

## Current Monetary Chain

| Authority | Question answered | Planned/actual | Basis and scope | Currency | Known/owner |
| --- | --- | --- | --- | --- | --- |
| Supplier Quote | What unit price and commercial/shipping terms were observed? | observed offer | per-unit plus separately scoped terms | source currencies | before purchase; supplier evidence admitted by Founder/operator |
| Acquisition Normalization | What is the planned acquisition cost per unit across the four normalized components? | planned calculation | per-unit total acquisition scope defined by ADR-0041 | explicit target capital currency | before Capital; HYB-derived from exact allocation/FX sources |
| Intended Order Quantity | What exact quantity does the Founder intend to buy? | planned intent | batch quantity/unit | none | before Capital; Founder-owned |
| Planned Requirement | What planned acquisition capital does that quantity require? | planned calculation | normalized per-unit cost times intended quantity | normalization target currency | before Gate; HYB-derived |
| Deployable Capital Snapshot | What reserve-adjusted capital is deliberately available? | current factual declaration | capital envelope | Requirement currency | Gate/Execution time; Founder-owned |
| Founder Approval | What maximum capital envelope did the Founder authorize? | authorization | full planned acquisition requirement | Requirement currency | before execution; Founder-owned |
| Execution Intent v1 | Is the exact approved manual action safe now? | proposed action and safety assessment | currently repeats approved capital | Approval currency | immediately before purchase; Founder input plus HYB assessment |
| Purchase Execution v1 | What external amount was reportedly committed? | actual event-time fact | currently overloaded with the approved envelope | forced to Approval currency | after external order; Founder/operator evidence |
| Actual Acquisition Settlement | What finally settled across the complete acquisition boundary? | final actual revision | batch and per-unit canonical acquisition categories | original currencies plus explicit settlement target | after costs settle; Founder evidence plus HYB derivation |

## Decision

### 1. Planned Acquisition Capital Requirement

`PlannedAcquisitionCapitalRequirement` remains the expected full acquisition
capital envelope for one exact Intended Order Quantity:

```text
normalized acquisition cost per unit * intended quantity
```

It contains only the acquisition scopes explicitly admitted by ADR-0046 and
its exact upfront-cost scope verification. It is not the supplier checkout
charge, a payment event, or the final settled total.

### 2. Founder Capital Approval

`FounderCapitalApproval.approved_capital` remains equal to the complete v1
Requirement and is a hard maximum authorization cap in the Requirement target
currency. It is not a prediction that one external supplier transaction will
have the same amount or currency. Partial approval and staged release remain
unsupported.

### 3. Real-Money Execution Intent v2

Choose the two-fact form of Option C. A v2 intent preserves both:

- `authorized_acquisition_capital_amount` and
  `authorized_acquisition_capital_currency`, reconstructed from the exact
  Approval/Requirement; and
- `proposed_supplier_order_committed_amount` and
  `proposed_supplier_order_currency`, supplied and explicitly confirmed by the
  Founder from the current external checkout/offer immediately before purchase.

The proposed supplier-order fact also requires a non-empty opaque checkout or
offer evidence reference. It is not an external order reference because an
order does not yet exist.

The authorized capital fields are not duplicate caller claims. The server
reconstructs them. The proposed supplier-order fields are caller-owned factual
inputs to the exact proposed action. Both are retained in the immutable source
manifest and response.

Policy v2 is:

```text
domestic-commerce-real-money-execution-safety / 2.0.0
```

It requires the proposed supplier-order currency to equal the exact Supplier
Quote unit-price currency for the first MVP. A checkout that commits multiple
currencies, a staged/deposit payment, or a currency different from the exact
Quote is unsupported and must not become READY.

### 4. Purchase Execution v2

The v2 Purchase Execution monetary fact means:

> The exact gross amount and currency the Founder became committed to pay at
> supplier-order execution for this external order, as shown by genuine
> execution evidence.

Use the explicit fields:

- `supplier_order_committed_amount`;
- `supplier_order_currency`.

They replace the ambiguous v1 request/record meaning of
`actual_total_committed_amount` and `currency` for new records. The gross
supplier-order amount may include checkout-level item, supplier shipping,
discount, or platform effects evidenced by the external order. It is not
silently decomposed into Actual Acquisition Settlement categories.

The Purchase Execution source manifest also preserves the reconstructed
authorized acquisition capital amount/currency and the exact proposed supplier
order amount/currency. The actual supplier-order fact must equal the proposed
supplier-order fact exactly.

Purchase Execution policy v2 is:

```text
exact-ready-intent-purchase-execution / 2.0.0
```

### 5. Exact-match policy

V2 exact match continues for:

- exact READY intent and Approval lineage;
- exact Quote ID/revision;
- exact intended/executed quantity and unit;
- exact Supplier/Product/option/SKU lineage reconstructed by HYB;
- Founder identity;
- proposed versus actual supplier-order committed amount and currency;
- required external order reference and execution evidence.

V2 does not require:

```text
supplier-order committed money
== approved acquisition capital money
```

Those facts have different scope and may have different currencies.

### 6. Quote relationship

The exact Quote revision, quantity, currency, validity, and current Founder
confirmation remain mandatory. Quote unit price multiplied by executed quantity
is not universally the supplier checkout total because shipping, discounts,
and platform/payment components may be separately represented or appear at
checkout. V2 therefore does not invent unsafe arithmetic equality.

If the checkout no longer reflects the exact persisted Quote terms, the Founder
must STOP before purchase, admit a new Quote revision, and rebuild every affected
normalization, Requirement, Gate, Approval, and Execution Intent. V2 does not
offer a deviation override.

### 7. Capital-cap safety

Removing false monetary equality does not remove the capital guard. READY v2
still requires:

- one exact, valid Quote revision and exact quantity/unit;
- a complete planned acquisition scope normalized into one target currency;
- Requirement equal to the approved hard cap;
- Gate PASS;
- a distinct current Deployable Capital snapshot in the approved currency with
  at least the full approved amount;
- exact Founder identity and current confirmation;
- the explicit proposed supplier-order amount/currency and checkout evidence.

Purchase Execution performs no cross-currency cap comparison. A CNY checkout
cannot be compared to a KRW cap without a distinct actual/pre-authorization FX
authority, and planned FX must not be reused as actual FX. For the controlled
manual MVP, cap safety is provided by the exact Quote/quantity/planned-cost
chain plus current Founder confirmation. A changed checkout term requires a new
chain before money is spent.

This contract does not claim to prevent a Founder from disregarding HYB and
clicking an unsafe external order. HYB admits only the exact supported action.
An intentional supplier-order amount different from the READY proposal cannot
be admitted as compliant. FX or later acquisition-cost drift is also not
silently treated as within cap: it must remain unresolved/BLOCKED until the
Actual Acquisition Settlement records the genuine evidence-backed deviation.

### 8. Actual FX boundary

No planned FX observation is applied to the supplier-order committed amount.
Purchase Execution preserves the source-currency fact exactly. Actual payment
FX, provider target charge, fees, and settlement provenance remain owned by
`ActualAcquisitionSettlement` under ADR-0051.

### 9. Actual Acquisition Settlement

Purchase Execution remains an event-time commitment fact. Actual Acquisition
Settlement remains the final category-complete acquisition authority. Its item
or other category may equal some or all of the supplier-order committed amount
only when evidence proves that relationship. It never copies the committed
amount as fallback.

The final target-currency acquisition total may legitimately be greater than,
less than, or equal to the planned Requirement because actual item settlement,
shipping, duty/customs, other costs, or actual FX differ. Such deviation is
valuable actual evidence, not an admission failure.

### 10. Cross-currency example

Illustrative only:

| Stage | Fact |
| --- | --- |
| Supplier Quote | 100 CNY per unit |
| Intended quantity | 5 units |
| Proposed supplier checkout | 500 CNY with checkout evidence |
| Planned acquisition envelope | 110,000 KRW, including the approved normalized acquisition scope |
| Founder Approval | maximum 110,000 KRW acquisition capital |
| Execution Intent v2 | authorized 110,000 KRW plus proposed 500 CNY |
| Purchase Execution v2 | actual supplier-order commitment 500 CNY |
| Final Actual Acquisition Settlement | for example 114,000 KRW after actual item, logistics, duty/other scope, and actual FX evidence |

No stage relabels 110,000 KRW as the actual supplier charge, and no stage uses
the planned CNY/KRW rate as actual payment FX.

### 11. Same-currency example

For a KRW Quote and KRW normalized plan, the proposed supplier checkout and
approved acquisition capital may happen to be numerically equal. They remain
separate facts:

- the Approval answers how much acquisition capital may be deployed;
- the Purchase Execution answers what external supplier-order amount was
  committed.

V2 preserves both even when amount and currency coincide.

### 12. Historical v1 semantics

Historical v1 intents and Purchase Execution Records retain their exact stored
meaning: the recorded committed amount was required to equal the READY planned
capital amount. They are never reinterpreted as v2 supplier-order facts and are
not migrated or backfilled.

After v2 implementation, v1 remains readable and replayable only. New
production execution intents and Purchase Execution Records must use v2,
including same-currency orders, because semantic separation is not conditional
on numerical currency equality.

### 13. Schema and persistence direction

The implementation PR must add versioned v2 Domain/Application command, source
manifest, result, persistence payload, policy, API request, and API response
contracts for both Execution Intent and Purchase Execution. Existing append-only
v1 rows and receipts remain reconstructible exactly.

The smallest safe persistence evolution extends the existing histories; it does
not add a shadow transaction domain. Replay returns originally persisted v1 or
v2 facts and never converts between them.

### 14. API direction

The v2 Execution Intent request adds only Founder-owned proposed supplier-order
money and checkout evidence. Authorized capital is server-reconstructed and
returned explicitly. The v2 Purchase Execution request accepts explicit
supplier-order committed money rather than the ambiguous v1 amount fields.

Swagger must distinguish:

- authorized acquisition capital amount/currency;
- proposed supplier-order committed amount/currency;
- actual supplier-order committed amount/currency;
- later final acquisition settlement amount/currency.

No compatibility alias may make one fact appear to be another.

### 15. First controlled MVP rule

Before the external purchase, the Founder must confirm the exact Quote revision,
quantity/unit, supplier product/option/SKU, checkout amount/currency, checkout
evidence, approved capital envelope, and current capital snapshot. If checkout
terms differ, currency is unsupported, or the transaction requires deposit,
staging, multiple supplier-order currencies, or an unresolved fee, STOP and do
not purchase under v2.

After purchase, record only the genuine supplier-order committed amount/currency,
external order reference, execution time, and evidence. Record final FX and all
final acquisition categories later through Actual Acquisition Settlement.

## Relationship to Existing ADRs

- ADR-0046 remains authoritative for the planned Requirement.
- ADR-0047 remains authoritative for the hard capital cap and is clarified as
  authorization rather than transaction prediction.
- ADR-0048 v1 remains historical; its new-production successor is execution
  safety policy v2 defined here.
- ADR-0050 v1 remains historical; its new-production monetary contract is
  Purchase Execution policy v2 defined here.
- ADR-0051 remains authoritative and unchanged for final settlement and actual
  FX.

## Consequences

- CNY supplier checkout and KRW capital authorization are both representable
  without fabricated equality.
- Exact purchase safety remains tied to Quote, quantity, Founder, capital, and
  one proposed supplier-order action.
- No FX engine or planned-to-actual conversion enters Purchase Execution.
- Planned capital, external commitment, and final settlement remain three
  separate learning stages.
- CR-1B7B2 implementation is a bounded versioned evolution of two existing
  authorities, not a new payment architecture.

## Deferred Work

- staged, deposit, installment, partial, refund, cancellation, or multi-currency
  supplier-order execution;
- automatic checkout verification or supplier/payment integration;
- automated cross-currency available-capital reservation;
- UI, authentication, or workflow orchestration;
- changes to Actual Outcome or Variance.
