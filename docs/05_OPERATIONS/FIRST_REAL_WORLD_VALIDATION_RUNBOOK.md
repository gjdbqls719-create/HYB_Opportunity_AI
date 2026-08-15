# First Real-World Validation Runbook

## Current target-bound Genuine-run gate

The target-bound path is technically implemented through Capital Gate:

```text
ADR-0060 target
-> Competition v2
-> Demand v2
-> DMV v2
-> target-aware Founder Sourcing
-> Verified Economics
-> Economics Source Composition
-> Conservative Economics
-> Critical Cost
-> Capital Readiness
-> Capital Gate
```

Repository implementation does not authorize a genuine run. Keep the HYB
server stopped and do not call the production API or open the genuine SQLite
database during documentation verification.

The first Genuine-run blocker is external evidence qualification: the official
NAVER geography clarification required for Demand v2 has not arrived. Do not
infer that answer. Consequently Genuine Demand v2 is not admitted, and Genuine
DMV v2, Capital Readiness, and Capital Gate have not been executed.

### Current Genuine authority ledger

| Authority fact | Current exact value/status |
|---|---|
| O1 Opportunity | `c2d4479a7f32437b9b0aefa614ae85c1` |
| O2 Opportunity | `fcdb01d411fd46d5bd07020634e5b74c` |
| ADR-0060 target | `cd050cd4f8734a71a61a219de9281a5f` |
| ADR-0060 admission ID | **RECOVER FROM ARCHIVED PRODUCTION RESPONSE** |
| Competition v2 cohort | `5237034f-371f-4517-8648-51d4e42dd062` |
| Competition v2 observation ID | **RECOVER FROM ARCHIVED PRODUCTION RESPONSE** |
| Competition v2 authority fingerprint | **RECOVER FROM ARCHIVED PRODUCTION RESPONSE** |
| Demand v2 | **NOT ADMITTED — pending official NAVER geography clarification** |
| DMV v2 / Capital Readiness / Capital Gate | **NOT EXECUTED** |

Do not recreate an authority merely because an exact ID was not copied into
this document. Recover it from the archived request/response artifacts first.

Demand v2 requires independently preserved provider query-count authority, a
bounded comparable cohort, one explicit review outcome per included organic
listing, artifact hashes/references, and operational target eligibility.
Archive the Founder-entered query separately from the exact provider-returned
query, if present. For the period, submit either both exact boundaries or the
exact provider-native label; never invent boundaries from a label, and never
submit both forms. Preserve all text verbatim in the evidence archive.

## 1. Purpose and milestone

This runbook is the operational contract for one private Founder to execute one
controlled, genuine O2 commerce loop through production HTTP interfaces. Use a
new production SQLite database, Swagger/OpenAPI, one product/SKU, one Supplier,
and genuine external evidence. Do not read or edit SQLite.

This run proves a **Real-Money Validated MVP** only when genuine purchase,
acquisition, receipt, sale, and a `calculable` Actual Outcome exist for the same
O2 lineage. Swagger success, tests, READY, or Purchase Execution alone do not
prove that milestone.

Closed-loop operational validation additionally requires the exact
pre-purchase Conservative result, the genuine Actual Outcome, and Variance v2.
It does not perform automatic calibration, learning, or policy changes.

> Candidate Promotion v2 is the required genuine-run contract. Submit
> `contract_version: "2.0.0"` and copy the exact Candidate, finalized Group, and
> representative Product Snapshot IDs from archived production responses. Never
> use legacy v1 admission signal fields for a genuine run.

### Historical checkpoint: FR-013

At the FR-013 checkpoint, the Genuine run had reached O1
`c2d4479a7f32437b9b0aefa614ae85c1` for the exact persisted eBay/US source
product. KR investigation found category and comparable Coupang evidence but did
not establish an exact-equivalent KR listing or authoritative KR canonical-
product identity. Therefore the existing step 7 ADR-0049 route cannot be used:
`product_equivalence_confirmed=true`, a fake Coupang item ID, the eBay item ID as
a KR ID, a comparable listing, and an invented canonical ID are all prohibited.

CR-1B7D3 implemented ADR-0060's separate new-to-market KR selling-target
admission foundation. At the FR-013 checkpoint no O2 existed and downstream
target-subject contracts were not yet complete. That historical STOP is now
superseded by the exact O2 and target recorded in the current ledger above.

### Historical checkpoint: FR-014

At the FR-014 checkpoint, the genuine run had O2
`fcdb01d411fd46d5bd07020634e5b74c` bound to new-to-market KR target
`cd050cd4f8734a71a61a219de9281a5f`, while Competition and Demand were not yet
admitted. FR-014 proved that Competition v1
`rocket_seller_count` has arithmetic behavior but no authoritative Coupang
observation semantics. Do not submit a guessed count, substitute zero, treat a
listing as a seller, or equate `판매자로켓`, `로켓배송`, `로켓그로스`,
arrival-speed text, badge colors, or icons.

ADR-0061 resolved the Competition authority and CR-1B7D4E implemented its v2
foundation. One immutable bounded cohort of comparable organic listing cards
supplies the core count and prices, while explicit Coupang Rocket labels remain
optional, separate, versioned marketplace enrichment.

The Genuine Competition v2 step has since been verified and persisted with
cohort `5237034f-371f-4517-8648-51d4e42dd062`. ADR-0062 and CR-1B7D4G/4H
implemented Demand v2 evidence admission, and ADR-0064 through ADR-0066
implemented the downstream target-bound path. The active STOP is now the
pending official NAVER geography clarification, not missing software.

## 2. Non-goals and external prerequisites

This procedure does not automate ItemScout, Coupang, supplier checkout,
payments, evidence storage, authentication, or workflow chaining. Before the
run, the Founder needs:

- eBay Discovery credentials/source availability used by the current collector;
- ItemScout/manual domestic market evidence and Coupang listing investigation;
- a Coupang seller account capable of producing genuine sale/settlement facts;
- a 1688/supplier account, exact product option/SKU, valid Quote, and checkout;
- shipping, customs/duty, payment/FX, receipt, and inspection evidence;
- enough Founder-declared deployable capital for the approved acquisition cap.

## 3. Evidence folder and response archive

Create this folder outside the production database:

```text
first_real_world_run/
  00_run_manifest/
  01_market/
  02_sourcing/
  03_economics/
  04_capital/
  05_purchase/
  06_acquisition/
  07_receipt/
  08_coupang_sale/
  09_outcome_variance/
  api_responses/
```

HYB stores opaque evidence references, not binary evidence. A reference may be
a stable relative filename, screenshot ID, CSV plus row/cycle, supplier order
reference, or external document reference. Never use a temporary download URL
or clipboard-only value.

### Mandatory archival rule

Immediately save every production request and response JSON. Use a stable pair
such as `NN_step.request.json` and `NN_step.response.json`; record timestamp,
method/route, command ID, HTTP status, business state, and returned IDs in the
run manifest. Do not rely on Swagger history, browser history, memory, or the
copy buffer. A response is not considered safely completed until both files and
its manifest IDs are saved.

## 4. Non-authoritative run manifest template

This file is an operational index only; never insert it into HYB tables.

```yaml
RUN: {run_id: run-001, started_at: null, founder_id: null, database_reference: null}
MARKET:
  discovery_execution_id: null
  finalized_group_id: null
  candidate_id: null
  product_snapshot_ids: []
  o1_opportunity_id: null
  o1_market_binding_id: null
  domestic_selling_admission_id: null
  new_to_market_domestic_selling_admission_id: null
  o2_opportunity_id: null
  competition_observation_id: null
  competition_assessment_id: null
  competition_authority_fingerprint: null
  demand_observation_id: null
  demand_assessment_id: null
  demand_authority_fingerprint: null
  domestic_market_validation_assessment_id: null
  domestic_market_validation_source_manifest_fingerprint: null
SOURCING:
  sourcing_admission_id: null
  sourcing_admission_revision: null
  supplier_id: null
  sourcing_product_id: null
  match_verification_id: null
  quote_id: null
  quote_revision: null
ECONOMICS:
  verified_economics_opportunity_id: null
  sourcing_economics_binding_id: null
  landed_cost_composition_id: null
  shipping_allocation_authority_ids: []
  fx_observation_ids: []
  acquisition_normalization_id: null
  economics_source_composition_id: null
  conservative_economics_result_id: null
  critical_cost_assessment_id: null
  capital_readiness_assessment_id: null
CAPITAL:
  intended_order_quantity_id: null
  deployable_capital_snapshot_a_id: null
  planned_capital_requirement_id: null
  capital_gate_id: null
  founder_capital_approval_id: null
  deployable_capital_snapshot_b_id: null
  real_money_execution_intent_id: null
PURCHASE: {purchase_execution_record_id: null, external_order_reference: null}
ACQUISITION: {actual_acquisition_settlement_ids: [], complete_settlement_id: null}
RECEIPT: {goods_receipt_ids: []}
SALE: {actual_sale_settlement_ids: [], ordered_complete_prefix: []}
OUTCOME: {actual_outcome_id: null}
VARIANCE: {variance_id: null}
EVIDENCE_FILES: []
API_RESPONSE_FILES: []
```

## 5. Command IDs and timestamps

- Use a unique, stable command ID for each fresh business attempt; a readable
  run-prefixed opaque string is accepted by current contracts.
- Exact replay means the same command ID and byte-equivalent business payload.
  Never reuse a command ID with changed facts; that is a conflict.
- Preserve every command ID in the request archive and manifest.
- Capital-facing target commands must name exact source IDs. Never select a
  latest/current target, admission, observation, economics result, or
  assessment as a substitute for a missing archived reference.
- All caller timestamps must be timezone-aware and factual. Never backdate.
- `observed_at` records evidence observation; `verified_at` verification;
  `approved_at` Founder approval; `confirmed_at` checkout confirmation;
  `executed_at` external commitment; `received_at` arrival; `inspected_at`
  inspection; settlement/window times describe the actual external period.
- `requested_at` is the caller command time. Server `admitted_at`,
  `evaluated_at`, `calculated_at`, and `committed_at` are returned authority.

Money and rates are JSON strings containing finite Decimal text. Never send a
JSON floating-point number for a Decimal field.

## 6. Exact production route order and ID handoff

Every row means: archive the response, copy the exact returned ID(s), inspect
the business state, then continue. Human inputs are genuine facts/evidence.
For the current run, first qualify the official NAVER geography response when
it arrives, then resume at step 9. Steps 1–8 are retained as exact historical
lineage and recovery context; do not recreate them.

| # | Method and route | Human input and prior IDs | Returned manifest key | Continue only when / next consumer |
|---|---|---|---|---|
| 1 | `POST /api/v1/discovery/executions` | collector command and factual Discovery parameters | `discovery_execution_id` | execution succeeds; GET steps 2–3 |
| 2 | `GET /api/v1/discovery/executions/{discovery_execution_id}` | exact execution ID | archived result | finalized result exists |
| 3 | `GET /api/v1/discovery/executions/{discovery_execution_id}/finalized-groups` | exact execution ID | `finalized_group_id`, representative `candidate_handoff` | handoff is available; Candidate |
| 4 | `POST /api/v1/candidates` | chosen group plus representative handoff copied verbatim | `candidate_id` | issuance succeeds; Snapshot |
| 5 | `POST /api/v1/product-snapshots/capture` | Candidate ID and exact returned observation bindings | `product_snapshot_ids[]` | capture succeeds; Promotion |
| 6 | `POST /api/v1/candidate-promotions` | `contract_version=2.0.0`, exact Candidate/Group/representative Snapshot, unique command ID, Founder/operator, factual selection reason and time | `opportunity_id` as O1, `binding_id`, `admission_id`, exact capture/Snapshot lineage | lifecycle is `discovered`; archive response, then Domestic Admission |
| 7a | `POST /api/v1/opportunities/{source_opportunity_id}/domestic-selling-admissions` | O1, exact existing KR listing/canonical identity, genuine equivalence evidence, source snapshot, operator/time | `admission_id`, `domestic_opportunity_identity.opportunity_id` as O2 | ADR-0049 existing-product path only; not applicable to the current ADR-0060 target and must not be used as compatibility |
| 7b | `POST /api/v1/opportunities/{source_opportunity_id}/new-to-market-domestic-selling-admissions` | exact ADR-0059 v2 O1/source Snapshot, Founder reason, bounded KR query/category search and evidence, operator/time | `admission_id`, opaque `target_identity`, target-bound `domestic_opportunity_identity.opportunity_id` as O2 | mutually exclusive with 7a; current authority exists—recover its exact admission ID from the archived response before Sourcing |
| 8 | `POST /api/v2/opportunities/{o2}/competition-observations` | Founder-reviewed bounded Competition v2 cohort and pinned artifacts/hashes | `observation_id`, `cohort.cohort_id` and exact committed response | current Genuine step is already verified/persisted; recover exact response pins before Demand |
| 9 | `POST /api/v2/opportunities/{o2}/demand-observations` (**current Genuine run: STOP pending official NAVER geography clarification**) | ADR-0062 exact Market Intent, exact bounded Comparable Market Response/reference, per-card review outcomes, artifacts/hashes; preserve original/provider-returned queries and exactly one period authority | `observation.observation_id`, `assessment.assessment_id` | archive response; do not use Demand v1; continue only after a factual admitted response |
| 10a | `GET /api/v2/opportunities/{o2}/domestic-market-validations/source-manifest` | exact `competition_observation_id` and `demand_observation_id` query parameters | exact manifest and `source_manifest_fingerprint` | preview only; Founder reviews every exact source pin; no verification or assessment is created |
| 10b | `POST /api/v2/opportunities/{o2}/domestic-market-validations` | exact Competition/Demand observation IDs, operator/current-use confirmation, reviewed fingerprint, factual times | `assessment_id`, exact source manifest/fingerprint | continue only on `validated_for_capital`; do not use DMV v1 compatibility |
| 11 | `POST /api/v1/sourcing/admissions` | `kind=new_to_market_domestic_selling_admission` plus exact ADR-0060 admission ID; Supplier/Product/option/SKU, independent verified Product Match, Quote, shipping scope, evidence | `admission_id`, `revision`, `supplier.supplier_id`, `sourcing_product.sourcing_product_id`, `match_verification.verification_id`, `quote.quote_id/revision` | exact target-aware lineage, Product Match, and valid Quote |
| 12 | `POST /api/v1/opportunities/{o2}/verified-economics` | Founder-verified sale/cost/fee/tax facts and evidence | O2-keyed verified snapshot response | every required fact verified; Binding |
| 13 | `POST /api/v1/opportunities/{o2}/sourcing-economics-bindings` | Sourcing Admission/revision, Quote/revision, verified economics O2 | `binding_id` | exact lineage; Landed Cost |
| 14 | `POST /api/v1/opportunities/{o2}/landed-cost-compositions` | Binding and explicit cost components/evidence | `composition_id` | no unresolved shipping scope; Allocation |
| 15 | `POST /api/v1/opportunities/{o2}/shipping-allocation-authorities` | Landed Cost ID, scope, denominator/basis and evidence | `authority_id` per scope | required allocations known; FX/Normalization |
| 16 | `POST /api/v1/fx-observations` | exact source/target pair, rate, source, observation time | `observation_id` per required pair | required planned FX exists; Normalization |
| 17 | `POST /api/v1/opportunities/{o2}/acquisition-cost-normalizations` | Landed Cost, allocation IDs, exact FX IDs, target currency | `normalization_id` | normalization calculable; Composition |
| 18 | `POST /api/v1/opportunities/{o2}/economics-source-compositions` | normalization ID plus verified economics source | `composition_id` | state supports Conservative |
| 19 | `POST /api/v1/opportunities/{o2}/conservative-economics` | exact source composition | `result_id` | state `calculable`; **freeze this pre-purchase ID** |
| 20 | `POST /api/v1/opportunities/{o2}/critical-cost-assessments` | exact normalization/composition chain | `assessment_id` | state `complete`; Readiness |
| 21 | `POST /api/v1/opportunities/{o2}/capital-readiness-assessments` | command v2: exact Conservative and Critical Cost IDs plus `domestic_market_validation_source.kind=domestic_market_validation_v2` and exact DMV v2 `assessment_id` | `assessment_id`, server-derived DMV source fingerprint | continue only on `ready_for_capital_review` |
| 22 | `POST /api/v1/opportunities/{o2}/intended-order-quantities` | Admission/revision, Quote/revision, intended quantity/unit | `intent_id` | quantity satisfies genuine commercial constraints |
| 23 | `POST /api/v1/deployable-capital-snapshots` | factual reserve-adjusted capital before Gate | `snapshot_id` as A | currency matches Requirement plan |
| 24 | `POST /api/v1/opportunities/{o2}/planned-acquisition-capital-requirements` | Intended Quantity, normalization, complete upfront scope evidence | `requirement_id` | state `calculable` |
| 25 | `POST /api/v1/opportunities/{o2}/capital-gate-assessments` | Readiness, Requirement, Snapshot A | `gate_id` | state `pass` |
| 26 | `POST /api/v1/opportunities/{o2}/founder-capital-approvals` | Gate, exact approved cap/currency, Founder/time | `approval_id` | approval response archived |
| 27 | `POST /api/v1/deployable-capital-snapshots` | current post-Approval capital declaration | `snapshot_id` as B | current contract accepts it |
| 28 | `POST /api/v1/opportunities/{o2}/real-money-execution-intents` | `contract_version=2.0.0`, Approval, Quote, Snapshot B, quantity, proposed checkout money, evidence, confirmation | `intent_id` | state `ready_for_manual_execution` |
| 29 | external supplier checkout | compare the READY purchase sheet below | external order reference/evidence | exact match only; otherwise STOP |
| 30 | `POST /api/v1/opportunities/{o2}/purchase-execution-records` | v2 READY Intent, exact actual supplier commitment, order reference/evidence/time | `record_id` | records the already completed external commitment; it does not place an order |
| 31 | `POST /api/v1/opportunities/{o2}/actual-acquisition-settlements` | Purchase ID, canonical acquisition facts/actual FX; exact predecessor for revision | `settlement_id` | downstream only from state `complete` |
| 32 | `POST /api/v1/opportunities/{o2}/goods-receipts` | Purchase ID, receipt/inspection quantities and evidence | `record_id` | factual inspection complete enough for next step |
| 33 | `GET /api/v1/opportunities/{o2}/owned-inventory` | O2 | archived product key/position | select exact receipt-backed product key |
| 34 | `POST /api/v1/opportunities/{o2}/actual-sale-settlements` | anchor receipt, one bounded window, canonical facts, payout/finality/evidence | `settlement_id` | Outcome prefix contains only ordered `complete` IDs |
| 35 | `POST /api/v1/opportunities/{o2}/actual-outcomes` | COMPLETE acquisition ID and ordered COMPLETE sale IDs | `outcome_id` | state `calculable` achieves real-money evidence loop |
| 36 | `POST /api/v1/opportunities/{o2}/economics-variances` | frozen pre-purchase Conservative result ID and Actual Outcome ID | `variance_id` | archive comparability and calibration eligibility |

Swagger is authoritative for each exact request body. This table supplies order
and safety meaning; it does not replace the generated schema.

For target-bound DMV v2, the Capital Readiness request must use the strict
command-v2 source reference:

```json
{
  "domestic_market_validation_source": {
    "kind": "domestic_market_validation_v2",
    "assessment_id": "exact DMV v2 assessment ID"
  }
}
```

The caller supplies no target identity, `MarketObservationIdentity`, or DMV v2
source-manifest fingerprint. The server reconstructs the exact target and
fingerprint from the named assessment. Historical DMV v1 remains supported by
its own exact contract; it is never a compatibility path for a target-bound O2.

## 7. Market, sourcing, economics, and capital checklists

### Market evidence

- Preserve ItemScout/manual date, market scope, search/query/category, observed
  competition count/quality and demand metrics using the exact API fields.
- Preserve Coupang listing references/screenshots used for the selected O2.
- Do not treat a title, URL, or displayed value as an identity.
- For future Competition v2 evidence, preserve the declared finite result
  bounds, ordered cards, organic/sponsored classification, comparability
  decisions, displayed prices, raw labels, per-card observation outcomes,
  operator/time, and screenshot artifact references. Do not calculate or submit
  a v1 `rocket_seller_count` from this evidence.
- For Demand v2 Market Intent, capture one exact provider field that is
  explicitly a KR query/search count, including the exact query, provider/field,
  optional exact provider-returned query, geography, locale, match semantics,
  either both exact period boundaries or one exact provider period label, unit,
  observed time, reference, artifact, and hash. Do not normalize either query
  or derive dates from a label. An undocumented number, result count, rank, or
  index is unsupported.
- For Demand v2 Comparable Market Response, preserve raw review-count
  outcomes for every included organic card in the exact bounded cohort. The
  existing Competition cohort may be referenced, but new artifacts are required
  when its capture does not expose complete review regions. Ratings are optional
  and never become a target rating.

### Sourcing

- One Supplier and exact sourcing product, option, SKU, external references.
- Verified Supplier Product Match; domestic equivalence is not a substitute.
- Exact Quote revision, unit price/currency, MOQ, quoted quantity, validity,
  shipping terms, lead time, and evidence.

### Economics

- Verified sale price, purchase/shipping scope, marketplace/payment/fixed fees,
  duty, tax, and other costs under their exact contracts.
- Explicit zero evidence for applicable known-zero facts. Unknown is never zero.
- Allocation denominator/evidence and exact planned FX observation IDs.
- Source Composition, Conservative, Critical Cost, and Readiness responses.

### Capital

- Exact intended quantity/unit, Snapshot A, calculable Requirement, Gate pass,
  Founder Approval, and distinct current Snapshot B.
- Approval currency/cap is not the supplier checkout currency/amount.

## 8. Essential pre-purchase freeze

Before leaving HYB for external checkout, save the full responses and mark these
manifest values:

**Essential:** O2 ID; Sourcing Admission ID/revision; Quote ID/revision;
Conservative result ID; Planned Requirement ID; Gate ID; Approval ID; Snapshot B
ID; READY Execution Intent ID.

Also archive Market Validation, Economics Source Composition, allocation, FX,
normalization, Critical Cost, and Capital Readiness responses. The Conservative
result later sent to Variance must satisfy:

```text
ConservativeEconomics.calculated_at < PurchaseExecution.executed_at
```

Never replace it post hoc with a later result.

## 9. READY purchase sheet

Copy these values from archived Sourcing and READY responses and compare them
visually with the supplier checkout immediately before clicking purchase:

| Fact | Archived authority | Checkout comparison |
|---|---|---|
| Supplier and sourcing product | Sourcing Admission | exact seller/product |
| external product, option, SKU | Sourcing Admission | exact option/SKU |
| Quote ID/revision and validity | Sourcing Admission/READY | exact current commercial terms |
| quantity/unit | Intended Quantity/READY | exact checkout quantity |
| proposed supplier amount/currency | READY v2 | exact checkout gross commitment |
| authorized acquisition capital amount/currency | READY v2 | separate cap; no numeric equality expected |
| Approval ID | READY v2 | must be the frozen Approval |
| Execution Intent ID/state | READY v2 | exact ID and `ready_for_manual_execution` |

Example: authorized capital `110000 KRW` and proposed checkout `500 CNY` are
different authorities. Purchase Execution records the actual `500 CNY`-scope
commitment. Actual Acquisition Settlement later records the final
category-complete acquisition cost. Planned FX is never actual FX.

If amount, currency, quantity, product, option/SKU, Quote, validity, or terms
differ: **STOP. Do not purchase and do not force the later record.** Admit the
new factual source and rebuild every affected downstream decision.

## 10. Business state and HTTP guide

HTTP 200/201 proves admission/replay, not business readiness. Inspect state:

- Market Validation: require `validated_for_capital`, not `blocked`.
- Conservative: require `calculable`, not `blocked`.
- Critical Cost: require `complete`, not incomplete/blocked output.
- Capital Readiness: require `ready_for_capital_review`.
- Requirement: require `calculable`.
- Gate: require `pass`, not `rejected` or `blocked`.
- Execution Intent: require `ready_for_manual_execution`, not `blocked`.
- Actual Acquisition/Sale: `blocked` revisions are valid evidence-progress
  records but cannot be consumed as COMPLETE sources.
- Actual Outcome: require `calculable` for the Real-Money Validated MVP.

HTTP 404 means an exact source is missing; 409 means replay/lineage/cardinality
conflict; 422 means structurally invalid facts; 503 means persistence is
unavailable. Never change genuine evidence merely to clear an error.

`BLOCKED` is an authoritative business result rather than a transport error,
but it stops progression. Capital Gate `rejected` is a business rejection and
must never be bypassed. Persistence corruption or unavailable exact authority
is **STOP / INVESTIGATE**; never backfill, recreate, or substitute an authority
to make the run continue.

## 11. Pre-purchase STOP checklist

Do not spend money unless all are true:

- exact KR O2 selected; Market Validation `validated_for_capital`;
- Supplier Product Match verified; exact Quote exists and is unexpired;
- Conservative `calculable`; Critical Cost `complete`;
- Capital Readiness `ready_for_capital_review`; Requirement `calculable`;
- Gate `pass`; Founder Approval and current Snapshot B accepted;
- Execution Intent v2 `ready_for_manual_execution`;
- external checkout exactly matches the proposed supplier action;
- exact pre-purchase Conservative result and every response are archived;
- no duty/tax/other/acquisition scope is silently assumed.

## 12. Purchase recording

After external purchase, submit only genuine facts: READY v2 Intent ID, Quote
revision, actual quantity/unit, actual supplier commitment amount/currency,
external order reference, Founder ID, factual `executed_at`, and evidence. A
record does not prove payment settlement, delivery, receipt, or final cost.

## 13. Actual acquisition worksheet

Submit the five fixed facts in the listed order and the separately scoped other
cost collection. Monetary inputs are batch totals; HYB derives normalized batch
and per-executed-unit values.

| API category | Availability | Original amount/currency | Actual FX when cross-currency | Evidence/time/operator |
|---|---|---|---|---|
| `unit_purchase` | known / not_applicable / unknown | ____ | source/target, original/target or rate, provider/channel, reference | ____ |
| `supplier_side_shipping` | known / not_applicable / unknown | ____ | ____ | ____ |
| `international_freight` | known / not_applicable / unknown | ____ | ____ | ____ |
| `domestic_inbound` | known / not_applicable / unknown | ____ | ____ | ____ |
| `duty_customs` | known / not_applicable / unknown | ____ | ____ | ____ |
| `other_mandatory_acquisition` | scoped items / evidenced N-A / unknown scope | item scope + amount/currency | per item when required | scope and item evidence |

`known` zero means checked, applicable factual zero with currency/time/evidence.
`not_applicable` has no money and requires evidence. `unknown` has no money,
requires an unresolved reason, is never zero, and blocks `complete`. Cross-
currency facts require actual payment/settlement FX; planned FX is forbidden.
Facts may legitimately become available after delay, so use an exact
predecessor-bound `blocked` revision until final.

## 14. Goods receipt checklist

Submit exact Purchase Execution ID, received quantity, executed quantity unit,
sellable quantity, damaged quantity, receipt evidence, optional delivery
reference, operator, factual `received_at`, `inspected_at`, and `requested_at`.
For the first run a complete undamaged receipt is preferable, but never report
it unless factual. Receipt does not change acquisition settlement facts.

## 15. Coupang sale worksheet

The repository does not prove a Coupang menu or report name. For every external
source below, locate and confirm it in the real seller account and preserve the
report/screenshot/CSV reference. Label unresolved source location:
**TO CONFIRM IN REAL COUPANG SELLER ACCOUNT**.

Common inputs: anchor Goods Receipt ID; marketplace `COUPANG`; seller, product,
option/SKU references; report/cycle and transaction references; closed
`period_start`/`period_end`; fulfilled, cancelled, refunded, and returned
quantities; exact quantity unit and one settlement currency.

| Exact `fixed_monetary_facts.category` | Meaning | Source location | zero / N-A / unknown |
|---|---|---|---|
| `gross_completed_merchandise` | completed merchandise proceeds | TO CONFIRM | must be known for COMPLETE |
| `buyer_shipping` | buyer-paid shipping credit | TO CONFIRM | all three states; unknown blocks |
| `marketplace_funded_discount_support` | marketplace-funded support | TO CONFIRM | all three states |
| `seller_funded_discount` | seller-funded discount | TO CONFIRM | all three states |
| `tax_collected` | tax collected in sale scope | TO CONFIRM | all three states |
| `marketplace_fee` | marketplace commission/fee | TO CONFIRM | all three states |
| `payment_fee` | payment processing fee | TO CONFIRM | evidenced N-A allowed |
| `fixed_fee` | fixed sale fee | TO CONFIRM | evidenced N-A allowed |
| `refund` | monetary refund scope | TO CONFIRM | unknown blocks |
| `cancellation_reversal` | cancellation reversal amount | TO CONFIRM | unknown blocks |
| `return_related_fee` | return-related fee | TO CONFIRM | all three states |
| `advertising` | attributed advertising spend | TO CONFIRM | all three states |
| `fulfillment` | fulfillment cost | TO CONFIRM | all three states |
| `storage` | storage cost | TO CONFIRM | all three states |
| `sale_side_inbound_handling` | sale-side inbound/handling cost | TO CONFIRM | all three states |

For `other_sale_side_costs`, submit an ordered scoped item list when known,
evidenced empty N-A when none apply, or unresolved scope. Every known/N-A fact
needs the evidence required by Swagger; unknown needs an honest reason.

### Payout and finality

Payout is an independent reconciliation fact. It never replaces gross revenue,
fees, other components, or profit and does not prove category completeness.

- `reconciled`: payout equals the implemented canonical component net and has
  explanation plus reconciliation evidence;
- `not_scope_comparable`: payout is known but timing/scope differs; preserve it
  with explanation/evidence rather than forcing equality;
- `unresolved`: reconciliation is not final and blocks COMPLETE.

Return finality `confirmed=true` requires evidence observed no earlier than the
window end. Otherwise provide the unresolved reason and retain a `blocked`
revision. For the first run use one product/SKU, one clearly bounded,
non-overlapping window, one report/cycle reference, and sufficiently final
refund/return scope. Avoid multiple windows unless genuine evidence requires
them; this is guidance, not a universal Domain invariant.

## 16. Actual Outcome and Variance

Actual Outcome input is only `command_id`, exact COMPLETE Actual Acquisition
Settlement ID, ordered COMPLETE Actual Sale Settlement IDs, and `requested_at`.
Founder does not supply profit, COGS, margin, or ROI; HYB derives them and
reconstructs Goods Receipt lineage.

Variance input is only `command_id`, the exact **pre-purchase**
`conservative_economics_result_id`, exact `actual_outcome_id`, and
`requested_at`. Confirm Conservative `calculated_at` is earlier than Purchase
`executed_at`. A numerical comparison can exist otherwise, but calibration
eligibility is hindsight-ineligible.

## 17. Post-purchase STOP checklist

Stop terminalization and preserve honest `blocked` facts if:

- Purchase Execution cannot represent the external action exactly;
- any acquisition category or required actual FX remains unresolved;
- received/sellable/damaged quantities are uncertain;
- sale category scope, payout reconciliation, or return finality is unresolved;
- Actual Outcome is `blocked` or sources do not form one exact product lineage;
- the intended Variance source is not the archived pre-purchase Conservative ID.

Never invent zero, N-A, evidence, timestamp, payout equality, or finality to
reach COMPLETE.

## 18. Lost-response recovery classification

| Class | Current first-run sources | Rule |
|---|---|---|
| A — directly recoverable | Discovery execution/result/groups; validation queue items; Owned Inventory projection | use the exact existing GET and archive again |
| B — indirectly recoverable | lineage IDs repeated in later Sourcing, Capital, Purchase, Settlement, Outcome, or Variance responses | use only an already archived later response; do not select latest |
| C — no dedicated production recovery read | Candidate/snapshot/promotion receipts and most Market, Economics, Capital, Purchase, Acquisition, Receipt, Sale, Outcome, Variance command results | mandatory request/response archive is the operational recovery source |

No broad GET/list endpoints are added for this run. With mandatory immediate
archival, a single private controlled run remains safe; recovery APIs are P2.
If any Class C response was not saved and the exact ID cannot be proven from an
already archived later response, **STOP the run**. Do not inspect SQLite or
guess an ID; restart before spending money or obtain a narrowly scoped recovery
change before continuing.

## 19. First-run completion and post-run review

At completion retain:

- every request/response JSON and the completed run manifest;
- the complete external evidence folder;
- final `calculable` Actual Outcome response and Variance response;
- the exact frozen Conservative response;
- a list of manual friction, repeated submissions, ambiguous external facts,
  and actual data unavailable from the real Coupang/supplier accounts.

Review whether market, sourcing, acquisition, receipt, sale, payout, and
finality evidence was practically obtainable. Improve only observed friction.
Do not resume broad architecture work or claim automated learning.
