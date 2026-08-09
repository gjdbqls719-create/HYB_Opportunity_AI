# ADR-0056 Conservative vs Actual Variance v2 Authority

## Status

Accepted

## Implementation Status

Decision only. CR-1B6E1 defines the future authority, comparison policy, source
contract, and calibration-suitability semantics. Domain, Application, SQLite,
API, UI, calibration, and automatic policy-learning behavior are not
implemented by this change.

The first supported comparison policy will be
`conservative-actual-variance / 2.0.0` with a schema identity that is distinct
from legacy Economics Variance.

## Context

HYB now persists two different, authoritative views of one commerce path:

- `ConservativeEconomicsResult` is a pre-action, per-unit prediction over one
  exact READY Economics Source Composition and one named scenario;
- `ActualOutcome` is a cumulative realized assessment over one exact O2,
  complete product key, Purchase Execution, acquisition settlement, receipt
  set, and ordered sale-window prefix.

They are deliberately not field-symmetric. Conservative Economics v1 models
normalized acquisition, gross merchandise sale price, three fee categories,
and a narrow verified-zero tax/duty/other safe path. Actual Outcome preserves
actual acquisition categories, realized sale components, damaged loss, and
remaining or unreceived capital exposure. A comparison that turns every
missing predicted category into zero would create false evidence. A comparison
that selects latest sources or rebuilds either result would introduce hindsight
bias and destroy historical reproducibility.

Legacy `EstimatedEconomicsSnapshot`, `ActualEconomics`, and Economics Variance
have different identities and scopes. They remain unchanged.

## Source contract audit

### Conservative source

One persisted CALCULABLE `ConservativeEconomicsResult` supplies:

| Meaning | Exact persisted field/source |
| --- | --- |
| sale price per unit | `conservative_sale_price` |
| normalized acquisition per unit | `acquisition_cost_per_unit` |
| marketplace/payment/fixed fee per unit | `marketplace_fee`, `payment_fee`, `fixed_fee` |
| accepted narrow costs | `accepted_tax_cost`, `accepted_duty_cost`, `accepted_other_cost` |
| predicted unit outcome | `conservative_profit_per_unit`, `conservative_margin`, `conservative_acquisition_roi` |
| scenario | `scenario_name`, `scenario_version`, and the one sale-price-factor assumption and owner |
| source identity | `source_composition_id` and its schema version |
| policy and time | currency, policy name/version/precision/rounding, schema, requested/calculated times |

The exact source-composition ID reconstructs the immutable acquisition
normalization. That normalization preserves the four canonical per-unit
components: unit purchase, supplier-side shipping, international freight, and
domestic inbound. It also reconstructs the exact landed-cost composition,
sourcing binding, Sourcing Admission/Quote revision, and O2 identity. No latest
lookup is needed.

### Actual source

One persisted CALCULABLE `ActualOutcome` supplies:

| Meaning | Exact persisted field/source |
| --- | --- |
| realized merchandise | `gross_realized_merchandise_revenue` |
| acquisition | category allocations, batch total, sold COGS, and per-executed-unit values |
| sale fees and costs | canonical `sale_components` and `other_sale_side_costs` |
| physical loss/exposure | damaged loss, remaining sellable basis, unreceived basis |
| realized outcome | actual profit and explicit availability/value for margin and acquisition ROI |
| quantity/scope | sold, executed, received, remaining, damaged, returned, unreceived, unit, windows, resolution |
| source identity | complete product key and exact purchase/acquisition/receipt/sale IDs and snapshots |
| policy and time | currency, policy/schema versions, requested/calculated/committed times |

The frozen acquisition snapshot includes `purchase_executed_at`, exact
Sourcing Admission/Quote/Product references, and capital-chain IDs. The frozen
sale snapshots retain KNOWN versus evidenced NOT_APPLICABLE component state
even where the aggregate Actual Outcome component amount is zero.

## Decision

### Authority meaning

`ConservativeActualVariance` v2 is an immutable historical assessment between
one explicitly selected persisted Conservative Economics result and one
explicitly selected persisted Actual Outcome. It preserves numeric differences,
semantic comparability, structured explanation facts, and future-calibration
suitability.

It is not a prediction, Actual Outcome, recommendation, PASS/FAIL capital
decision, accounting correction, causal ranking, calibration engine, model
training action, or automatic policy update.

### Exact source pair and lineage

The caller supplies exactly one Conservative result ID and one Actual Outcome
ID. The owner never selects latest, closest, terminal, or most favorable
sources.

The future Application owner must reconstruct and prove all of the following:

1. both results have the route O2 `OpportunityIdentity`;
2. the Conservative result points to its exact source composition,
   normalization, landed-cost composition, sourcing binding, and Sourcing
   Admission/Quote revision;
3. the Actual Outcome product key and frozen acquisition source point to the
   same O2, Sourcing Admission/Quote revision, supplier, and sourcing product;
4. the Actual purchase/capital requirement names the same acquisition
   normalization and operational quantity unit used by the executed purchase;
5. source policy/schema combinations are explicitly supported.

This exact immutable chain proves product, economic, and unit lineage even
though the Conservative result itself does not duplicate the full product key
or quantity-unit text. Reconstructing named append-only sources is allowed;
selecting current/latest sources or substituting an equivalent-looking product
is forbidden.

### Source prerequisites and structural errors

The first policy accepts only:

- CALCULABLE `conservative-unit-economics / 1.0.0`;
- CALCULABLE `actual-outcome / 1.0.0`;
- exact equal currency with no Variance-owned FX;
- the exact compatible O2/product/economic/unit lineage above.

A BLOCKED source cannot produce numeric financial variance. Missing IDs are
not-found errors. Non-calculable sources, lineage mismatch, currency mismatch,
unsupported policy/schema, or unit contradiction are conflicts. Malformed or
unreadable persisted authorities are source/persistence failures. The first
policy does not persist these meaningless attempts as NOT_COMPARABLE results.

`NOT_COMPARABLE` remains a valid Domain state for a future explicitly supported
source combination where sources are structurally valid but policy determines
that no core metric is safely comparable. It is not a replacement for input or
persistence errors.

### Currency, quantity, and normalization

Variance performs no FX. All comparison money uses the shared source currency.
Conservative money is per operational unit. Actual sale totals are normalized
only by the exact positive `sold_quantity`; acquisition values use the persisted
per-executed-unit allocation, never sold COGS divided by sold units.

When sold quantity is zero, no sale price, fee, profit-per-sold-unit, margin, or
ROI value is fabricated. Acquisition cost comparison and actual/exposure
context remain useful.

The comparison policy uses Decimal precision 34 and `ROUND_HALF_EVEN`, no float,
NaN, Infinity, or intermediate presentation quantization. It does not alter
either source value.

## Core metric set

The v2 core set is exactly:

1. comparable acquisition cost per executed unit;
2. gross sale price per sold unit;
3. marketplace fee per sold unit;
4. payment fee per sold unit;
5. fixed fee per sold unit;
6. profit, with both actual-sold-scope total and per-sold-unit views;
7. margin percentage-point comparison;
8. acquisition ROI percentage-point comparison.

Actual-only contributors and exposure facts explain these results but are not
silently promoted to additional core metrics.

### Acquisition cost

The direct acquisition metric uses the component-aligned scope:

```text
predicted comparable acquisition per unit
= Conservative normalization:
   unit purchase
 + supplier-side shipping
 + international freight
 + domestic inbound

actual comparable acquisition per executed unit
= Actual Outcome per-executed-unit allocations for the same four categories
```

This avoids comparing Conservative's four-category normalization with Actual
Outcome's broader six-category all-in acquisition total. Actual duty/customs
and other mandatory acquisition cost remain separate structured contributors.
The complete actual acquisition per-executed-unit amount is preserved as scope
context.

Where each of the four component meanings matches, component-level variance is
also allowed using the exact immutable normalization. No current or latest
normalization is read.

### Sale price and fees

For positive sold quantity:

```text
actual gross sale price per sold unit
= gross completed merchandise / sold quantity

actual fee per sold unit
= exact category total / sold quantity
```

Gross merchandise excludes buyer shipping and marketplace-funded support
because Conservative sale price has no equivalent credit scope. Marketplace,
payment, and fixed fees are compared independently only when frozen sale facts
prove matching category meaning.

An evidenced NOT_APPLICABLE payment or fixed fee means the exact marketplace
scope had no distinct category. ADR-0054 permits its preserved state to
contribute derived zero, so it may be compared to the predicted category while
retaining NOT_APPLICABLE source context. UNKNOWN never becomes zero, but a
CALCULABLE Actual Outcome cannot contain such an unresolved COMPLETE source.

If a future source broadens a fee category, that metric is SCOPE_MISMATCH rather
than forced into a numeric comparison.

### Predicted tax, duty, and other

Conservative v1 only admits verified zero for generic tax, duty, and other cost,
and ADR-0043 explicitly says non-zero duty lacks a proven per-unit customs
scope. Therefore v2 does not use these zero values to pretend exact symmetry:

- generic predicted tax is `NO_ACTUAL_EQUIVALENT` because Actual Outcome has no
  admitted seller-side tax authority;
- predicted duty is preserved as predicted-only context, while actual
  duty/customs is an actual acquisition contributor; it is not a direct
  category variance under v2;
- generic predicted other cost is predicted-only scope context, while actual
  other acquisition and sale costs retain their distinct actual categories.

Future non-zero authoritative mappings require a new supported source/policy
combination.

### Actual-only contributors and exposure context

The following are structured `UNMODELED_IN_PREDICTION` contributors, never
represented as predicted zero:

- refund and return-related fees;
- advertising;
- fulfillment, storage, and distinct sale-side inbound/handling;
- ordered other sale-side costs;
- actual duty/customs and other mandatory acquisition costs that lack safe v1
  predicted symmetry;
- damaged acquisition loss;
- buyer shipping and marketplace-funded support as actual-only credits.

Seller-funded discount, cancellation reversal, and customer tax remain source
context according to ADR-0054/0055 and are not double-counted as bridge items.

Remaining sellable quantity/basis and unreceived quantity/basis are exposure
context, not expenses or realized variance. Returned quantity remains unresolved
physical context under the Actual Outcome contract.

### Profit

For positive sold quantity, preserve both representations:

```text
predicted profit for actual sold quantity
= conservative profit per unit * sold quantity

total profit variance
= actual realized profit - predicted profit for actual sold quantity

actual profit per sold unit
= actual realized profit / sold quantity

profit-per-unit variance
= actual profit per sold unit - conservative profit per unit
```

This is an outcome comparison, not a claim that every underlying cost category
is symmetric. Damaged loss and actual-only costs remain explicit contributors
and scope flags. At zero sales, both normalized profit comparisons are
UNAVAILABLE; actual total profit and zero-sale context are still preserved.

No predicted amount is multiplied by acquired quantity for a partial sold-scope
profit comparison.

### Margin and acquisition ROI

Margin is compared in percentage points when both authoritative values are
available. Its gross merchandise denominator matches the selected sale-price
scope; actual-only profit contributors remain explanation context.

Acquisition ROI is comparable in percentage points only when the actual
recognized acquisition denominator contains sold COGS without damaged loss and
without actual duty/other acquisition categories outside the Conservative
normalization. Otherwise both authoritative ratio values are preserved, but
the metric is `SCOPE_MISMATCH` and carries no variance or favorability. Variance
never claims the ADR-0043 and ADR-0055 denominators are universally identical.

## Metric result contract

Each immutable metric result preserves:

- metric identity and deterministic direction (`COST` or `BENEFIT`);
- comparability;
- predicted and actual value where semantically available;
- signed variance, relative variance percent or percentage-point variance as
  applicable;
- favorability;
- unit and currency;
- ordered reason/scope codes.

Comparability values are:

- `COMPARABLE`;
- `UNAVAILABLE`;
- `UNMODELED_IN_PREDICTION`;
- `NO_ACTUAL_EQUIVALENT`;
- `SCOPE_MISMATCH`;
- `NOT_APPLICABLE`.

The signed convention is always:

```text
variance = actual - predicted
relative variance percent = variance / abs(predicted) * 100
```

Relative variance is available only when the predicted value is non-zero and
the metric supports it. Margin and ROI use only
`actual_percent - predicted_percent` percentage points. There is no
percent-of-percent value.

Favorability is `FAVORABLE`, `UNFAVORABLE`, `NEUTRAL`, or `UNAVAILABLE`.
Higher actual acquisition/fee cost is unfavorable; higher actual sale price,
profit, margin, or ROI is favorable. Sign alone is never treated as business
meaning and favorability is not an investment PASS/FAIL.

## Comparison state

Comparison state is independent of actual performance:

- `COMPARABLE`: every core metric applicable to this actual scope is
  COMPARABLE;
- `PARTIALLY_COMPARABLE`: at least one core metric is COMPARABLE, but another
  core metric is unavailable, not applicable, or scope-mismatched;
- `NOT_COMPARABLE`: no core metric is safely comparable for a structurally
  supported pair.

Zero sales normally produces PARTIALLY_COMPARABLE because acquisition remains
comparable while sold-unit metrics are unavailable. Negative profit does not
reduce comparability.

## Actual resolution and calibration eligibility

Comparison state and calibration eligibility are separate persisted facts.
Eligibility values are `ELIGIBLE`, `PROVISIONAL`, and `INELIGIBLE`.

The first policy derives them as follows:

- `INELIGIBLE` when the Conservative result was not calculated strictly before
  Purchase Execution, or comparison state is NOT_COMPARABLE;
- `PROVISIONAL` when sources are pre-action and useful but Actual Outcome is
  PARTIAL, including zero sales with remaining/unreceived exposure;
- `ELIGIBLE` when sources are pre-action, comparison state is not
  NOT_COMPARABLE, Actual Outcome is FULLY_RESOLVED, and at least one core metric
  is comparable.

A fully resolved zero-sale outcome, for example total evidenced damage, can be
ELIGIBLE for the metrics it genuinely supports while sale-normalized metrics
remain unavailable. Eligibility never triggers training or policy changes.

Deterministic reason codes include at least:

- `ACTUAL_OUTCOME_PARTIAL`;
- `ZERO_SALES_SCOPE`;
- `PREDICTION_NOT_BEFORE_EXECUTION`;
- `CORE_METRIC_UNAVAILABLE`;
- `ACTUAL_ONLY_CONTRIBUTORS_PRESENT`;
- `REMAINING_INVENTORY_EXPOSURE`;
- `UNRECEIVED_EXPOSURE`;
- `SOURCE_SCOPE_MISMATCH`.

Actual-only costs do not by themselves make a terminal observation ineligible.
Reasons explain suitability; they are not automatic calibration instructions.

## Hindsight safety

For ELIGIBLE or PROVISIONAL status:

```text
ConservativeEconomicsResult.calculated_at
< frozen PurchaseExecution purchase_executed_at
```

The Purchase Execution time is read from the exact Actual Outcome acquisition
snapshot, not from a current Capital object. A prediction calculated at or
after execution may still produce the same numerical comparison, but its
calibration eligibility is INELIGIBLE with
`PREDICTION_NOT_BEFORE_EXECUTION`.

The first real-world operation must archive/reference the exact Conservative
result before external purchase. After the real loop, the Founder creates an
Actual Outcome and then names those two exact IDs. A better-looking post-outcome
scenario cannot replace the historical prediction.

## Structured explanation and profit bridge

The result preserves metric comparisons, actual-only contributors,
predicted-only context, exposure context, scenario context, actual scope, and
calibration context. It stores no authoritative free-text or LLM explanation.

v2 does not persist a causal or additive profit bridge. Sale-price changes
interact with rate-based predicted fees, while actual-only credits/costs,
damage, and different denominator scopes prevent a single honest attribution
without an additional policy. The raw structured values support later analysis
without inventing causal ranking.

## Source manifest

The future immutable manifest freezes at least:

- O2 identity;
- Conservative result ID and canonical source snapshot;
- Actual Outcome ID and canonical source snapshot;
- exact Conservative source-composition, normalization, landed-cost,
  sourcing-binding, Admission, and Quote IDs/versions used for lineage and
  component reconstruction;
- exact Actual product key, purchase/acquisition/receipt/sale IDs and windows;
- actual sold quantity, quantity unit, resolution, remaining/damaged/returned/
  unreceived context, and purchase execution time;
- source currencies, policies, schemas, scenario, and comparison policy/schema;
- deterministic fingerprints for frozen canonical snapshots.

The comparison trusts the persisted source results. It does not recalculate
Conservative sale/profit/margin/ROI or Actual COGS/profit/margin/ROI. Exact
upstream reconstruction is limited to lineage, availability semantics, and
component detail not duplicated on those results.

## Persistence, identity, replay, and time

Variance v2 is a persisted immutable result with append-only history and
command receipts. A server-owned opaque variance ID identifies the result.
Caller time is `requested_at`; server times are `calculated_at` and
`committed_at`.

Replay is checked before source reads, reconstruction, calculation, identity,
or clocks. Same command ID and payload returns the exact historical result;
changed payload conflicts. One exact Conservative result + Actual Outcome +
comparison policy version owns at most one result. A different command may
receive an alias receipt for that result.

There is no revision chain. An early PARTIAL and a later FULLY_RESOLVED Actual
Outcome create separate Variance results. Multiple named Conservative scenarios
may each be compared to the same Actual Outcome, but the system never chooses
the best scenario after the fact. Earlier results are never updated.

## Future API and Domain direction

The intended thin production boundary is:

```text
POST /api/v1/opportunities/{opportunity_id}/economics-variances
```

The request supplies command ID, Conservative result ID, Actual Outcome ID, and
requested time. It supplies no variance, favorability, state, calibration
eligibility, or explanation values.

The future immutable Domain may use a compact composition of a top-level
assessment, metric results, actual-only contributors, exposure/calibration
context, and source manifest. Repository conventions decide the final number
of types; the semantics in this ADR are mandatory.

## Legacy isolation and MVP boundaries

Legacy Economics Variance remains unchanged. Its estimate snapshots and legacy
ActualEconomics are not aliases, fallbacks, migration sources, or write targets
for v2.

Real-Money Validated MVP remains achieved only operationally when genuine
purchase, acquisition, receipt, sale, and CALCULABLE Actual Outcome evidence
exists for one O2. Variance v2 is not required for that milestone.

Closed-Loop Learning MVP software capability additionally requires an exact
persisted Conservative result, exact persisted Actual Outcome, persisted
Variance v2, structured comparability, and calibration eligibility. Tests can
prove software capability only. Genuine closed-loop validation still requires
real-world source data.

No calibration engine, threshold update, scoring change, Bayesian/ML training,
fine-tuning, or automatic scenario/policy change is authorized here.

## Examples

### Positive sold scope with actual-only costs

Suppose predicted per-unit acquisition is 10,000 KRW, sale price 20,000,
marketplace fee 2,000, payment fee zero, fixed fee 500, and profit 7,500.
Four units sell. Actual aligned acquisition is 11,000 per executed unit, gross
merchandise is 76,000, marketplace fee 8,000, payment fee is evidenced
NOT_APPLICABLE, fixed fee is 2,400, refund is 1,000, advertising is 2,000, and
actual realized profit is 18,600.

```text
acquisition variance per unit = 11,000 - 10,000 = +1,000 UNFAVORABLE
sale price per sold unit = 76,000 / 4 = 19,000
sale price variance = 19,000 - 20,000 = -1,000 UNFAVORABLE
fixed fee per sold unit = 2,400 / 4 = 600
fixed fee variance = 600 - 500 = +100 UNFAVORABLE
predicted profit for sold scope = 7,500 * 4 = 30,000
total profit variance = 18,600 - 30,000 = -11,400 UNFAVORABLE
actual profit per sold unit = 18,600 / 4 = 4,650
profit variance per sold unit = 4,650 - 7,500 = -2,850 UNFAVORABLE
```

Refund and advertising are preserved as UNMODELED_IN_PREDICTION, not as
predicted zero variances.

### Zero sales with remaining inventory

A CALCULABLE PARTIAL outcome with zero sold units still compares predicted and
actual aligned acquisition per executed unit. Sale price, fee-per-sold-unit,
profit-normalized, margin, and ROI comparisons are UNAVAILABLE rather than
zero. Remaining and unreceived basis remain exposure context. The overall
comparison is PARTIALLY_COMPARABLE and calibration is PROVISIONAL when the
prediction preceded purchase.

### Denominator mismatch

If damaged loss is non-zero or actual acquisition includes duty/other categories
outside the Conservative normalization, actual acquisition ROI and
Conservative acquisition ROI are retained but their percentage-point variance
is SCOPE_MISMATCH. Other safe metrics remain available, so the comparison may
be PARTIALLY_COMPARABLE.

### Post-execution prediction

An explicitly selected Conservative result calculated after Purchase Execution
may still yield deterministic numerical metrics. Its calibration eligibility is
INELIGIBLE. The system does not replace it with an earlier or closer prediction.

## Consequences

- HYB can explain prediction misses without erasing category asymmetry.
- Exact per-unit normalization and source lineage are reproducible without
  latest selection.
- Zero sales and partial inventory remain useful without false values.
- Terminality, comparability, and calibration suitability remain distinct.
- Hindsight-biased predictions cannot become calibration-ready merely because
  their numbers compare cleanly.
- Actual-only costs and capital exposures stay visible and correctly scoped.
- Legacy variance and both source authorities remain immutable and unchanged.

## Deferred Work

1. Domain/Application/SQLite/API implementation and production tests.
2. Deterministic attribution or profit-bridge policy, if later justified.
3. Calibration policy and multi-observation learning data products.
4. Seller-side tax, recovery/correction, return re-entry, and broader source
   policy mappings.
5. UI, authentication, marketplace automation, model training, and automatic
   policy changes.
