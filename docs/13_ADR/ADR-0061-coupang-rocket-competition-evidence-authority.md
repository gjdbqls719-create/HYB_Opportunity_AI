# ADR-0061: Coupang Rocket Competition Evidence Authority

## Status

Accepted

## Implementation Status

Implemented in CR-1B7D4E at the Domain, Application, additive SQLite, and
dedicated API v2/OpenAPI boundaries. The implementation derives core and
Coupang signal facts from an immutable bounded card manifest, supports both
historical Market and ADR-0060 target subjects, and preserves receipt-first
replay, aliases, corruption detection, and current-schema read stability.

Competition v1, Demand, Decision Composition, and Domestic Market Validation v1
remain unchanged. Automated Coupang collection, UI entry, DMV v2, and genuine
Competition/Demand admission remain unimplemented or unexecuted as applicable.
The genuine run remains stopped before Competition and Demand.

## Context

Competition v1 requires `competitor_count`, `rocket_seller_count`,
`price_spread`, and `median_price`. Its analyzer validates
`rocket_seller_count` as a non-negative integer no greater than
`competitor_count`, assigns an absolute Rocket level, and derives
`rocket_seller_count / competitor_count` as a concentration proxy.

FR-014 established that the repository has no authoritative production
observation semantics for that field. It defines no counted unit, qualifying
Coupang state, seller identity, seller deduplication, listing-to-seller
relationship, badge normalization, or bounded sampling rule. Historical tests
prove only arithmetic. No Coupang adapter owns this normalization.

The Founder has a bounded Coupang search-result capture for
`차량용 시트백 수납함`, with visible comparable listings, prices, ordering, and
several Rocket-related or delivery labels. The capture does not establish
seller identity or an authoritative equivalence among those labels. Requiring a
seller count would therefore force an invented identity or semantic rule.

## Existing Metric Intent

Actual consumers use the metric only to express visible Rocket presence as an
absolute level and as a share of a competitive count. No analyzer, snapshot,
Decision Composition consumer, or Domestic Market Validation consumer uses a
seller identifier, seller cardinality, or seller relationship.

The narrow business question supported by those consumers is:

> How prevalent is an explicitly observed Coupang Rocket-related
> program/fulfillment signal in the bounded visible comparable result set, and
> therefore what contextual logistics/fulfillment pressure is visible?

The current system does not support the stronger questions "how many distinct
sellers participate in a Rocket program" or "how difficult will delivery
expectations make entry." The first requires seller identity; the second would
require a separate policy relating observed labels to an entry decision.

## Decision

Introduce a versioned Competition v2 contract with two layers:

1. A marketplace-independent, mandatory core derived from one immutable bounded
   cohort of comparable organic listing cards.
2. Optional marketplace-specific signal envelopes. Coupang Rocket evidence is
   one such envelope and never becomes a universal marketplace taxonomy.

Competition v1 remains immutable. Its metric names, values, analyzer,
assessments, snapshots, receipts, fingerprints, and Domestic Market Validation
v1 use are not migrated, backfilled, or reinterpreted.

The v2 versions are:

- policy: `competition-policy-v2`
- observation: `competition-observation-v2`
- assessment: `competition-assessment-v2`
- Coupang signal: `coupang-rocket-signal-v1`
- Coupang taxonomy: `coupang-rocket-taxonomy-v1`

## Competition v2 Core

The required v2 core metrics are:

1. `comparable_listing_count`
2. `price_spread`
3. `median_price`

`comparable_listing_count` is the number of included, unique organic listing
cards in the exact bounded cohort. It is not a distinct seller count and does
not replace or reinterpret historical `competitor_count` values.

Competition v2 applies the existing numerical Competition-level thresholds to
`comparable_listing_count` under the new policy version. It applies the existing
price-pressure calculation to the v2 price metrics. The v2 assessment does not
emit v1 `rocket_competition` or `market_concentration`; marketplace signal
results are exposed separately.

## Immutable Bounded Cohort

One `cohort_id` owns all v2 core facts and optional signal observations. Its
immutable provenance must include market, marketplace, target subject, exact
query/category, locale, result surface, observation time/window, capture
artifact reference, declared finite result bounds, cohort policy version, and
every encountered card in order with its inclusion decision and reason.

The bound must be declared by the capture, not selected after examining prices
or Rocket labels. A cohort with zero included comparable organic listings is
insufficient for a complete v2 assessment.

## Comparable and Sponsored Results

The core cohort contains organic results that match the target's declared
product use, category/form factor, condition, and cohort-policy comparability
rules. Non-comparable cards remain in the capture manifest with an explicit
exclusion reason.

Sponsored cards are excluded from the core cohort because paid placement is a
different observation from organic competitive presence. They are preserved in
an ordered sponsored-result manifest and may produce a separate
`sponsored_listing_count`. Their prices and Rocket labels do not contribute to
core or Coupang signal aggregates.

## Duplicate and Variant Rules

- The observation unit is one visible listing card, not one seller.
- A repeated card with the same explicit marketplace item ID is included once;
  later occurrences are recorded as duplicate exclusions.
- Distinct listing IDs are distinct observations even when seller text appears
  equal. No seller deduplication occurs.
- Variants shown within one card count as one listing observation.
- Variants shown as distinct cards with distinct item IDs count separately.
- When no marketplace item ID is visible, `(capture reference, result ordinal)`
  is the observation reference. Title similarity must not deduplicate it.

## Price Cohort Integrity

`price_spread` and `median_price` are derived from the displayed comparable
price of every included core listing in the same immutable cohort. They may not
use a different query, larger result set, or selectively priced subset.

If any included core listing lacks a valid comparable price or uses an
unresolved currency/unit basis, the price evidence is unavailable and the core
assessment is unavailable. The listing must not be silently excluded because
its price is missing.

## Coupang Rocket Taxonomy

Each included core listing carries raw visible label text and a set of zero or
more explicit normalized label states. States are not assumed to be mutually
exclusive:

- `SELLER_ROCKET`: only explicit visible `판매자로켓` text;
- `ROCKET_DELIVERY`: only explicit visible `로켓배송` text;
- `ROCKET_GROWTH`: only explicit visible `로켓그로스` text;
- `OTHER_EXPLICIT_ROCKET_LABEL`: other visible text explicitly containing a
  Rocket program/fulfillment label, with the raw text preserved;
- `NO_EXPLICIT_ROCKET_LABEL`: the relevant visible label region was completely
  observed and contained none of the supported or other explicit Rocket labels.

The first four states are not equivalent and their counts may overlap. Badge
color, icon shape, placement, title text, seller text, and mere arrival-speed or
delivery-promise text do not imply any state. Arrival-speed text may be retained
as contextual raw evidence but is excluded from Rocket aggregates.

`NO_EXPLICIT_ROCKET_LABEL` is an observed-negative card fact for this capture
and taxonomy only. It does not prove that a seller or listing is not enrolled in
any Coupang program outside the visible result surface.

## Coupang Signal Aggregates

`coupang-rocket-signal-v1` contains `observable_listing_count`, one
`explicit_label_count` for each explicit taxonomy state,
`no_explicit_rocket_label_count`, `status_not_observed_count`,
`semantics_unsupported_count`, `extraction_failed_count`, and one derived share
per explicit state.

`observable_listing_count` is the number of included core listings whose
relevant label region was completely observed, whose taxonomy is supported, and
whose extraction succeeded. It includes `NO_EXPLICIT_ROCKET_LABEL` listings.
Each explicit-state share uses `observable_listing_count` as its denominator.
Unknown/error cards remain in `comparable_listing_count` but not in that
denominator. Aggregate counts must reconcile to the per-card manifest; explicit
state counts may overlap and are not summed as a partition.

## Unknown and Failure Semantics

The following are distinct and immutable:

- `NO_EXPLICIT_ROCKET_LABEL`: complete relevant region observed, no explicit
  taxonomy label present;
- `STATUS_NOT_OBSERVED`: the capture does not expose enough of the relevant
  label region for a positive or negative observation;
- `SEMANTICS_UNSUPPORTED`: visible text/state exists but the selected taxonomy
  cannot normalize it;
- `EXTRACTION_FAILED`: the artifact should be readable under the selected
  extraction contract, but extraction failed.

The latter three never equal false, zero, or `NO_EXPLICIT_ROCKET_LABEL`. A zero
explicit-label count is authoritative only when every included listing is
observable and the reconciled manifest contains zero instances of that state.

## Founder-Assisted Evidence Contract

Manual evidence must preserve:

- `KR` market, `coupang` marketplace, and exact target subject;
- query/category, locale, result surface, observation time/window, and operator;
- finite bounds and ordered per-card references or visible URLs/item IDs;
- organic/sponsored classification and inclusion/exclusion reason;
- raw title, displayed price/currency, raw labels, and delivery-promise text;
- screenshot/evidence artifact reference and content hash;
- per-card observation outcome;
- cohort, Competition policy, signal, and taxonomy versions.

The operator records visible facts and comparability decisions. The operator
does not infer seller identity, hidden program enrollment, or label
equivalence. The server derives counts, shares, prices, availability, and
confidence from the immutable manifest.

## Automated Collector Contract

A future Coupang adapter owns extraction into the same evidence envelope. It
also preserves collector name/version, request/capture reference, response or
artifact hash, source schema/selector version, per-card raw payload reference,
extraction outcome, and normalized taxonomy version.

Replay uses persisted artifacts and manifests; it must not call Coupang again.
Selector failure, absent markup, unsupported text, and observed-negative state
remain distinct. Automation cannot change the taxonomy or cohort policy without
a new version.

## Assessment Availability and Confidence

Competition v2 has these assessment availability values:

- `COMPLETE_WITH_MARKETPLACE_SIGNAL`: core complete and the applicable Coupang
  signal is complete for every included listing;
- `COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL`: core complete and at least
  one, but not every, included listing is observable for the Coupang signal;
- `COMPLETE_CORE_ONLY`: core complete and the signal is unavailable,
  unsupported, omitted, or not applicable;
- `UNAVAILABLE`: any required core metric or cohort invariant is unavailable.

The v2 core analyzer requires only the three core metrics. Coupang signal
evidence is optional enrichment and cannot make an unavailable core complete.

The assessment preserves separate confidence values:

- `core_confidence` is the minimum confidence of the three required core facts;
- `marketplace_signal_coverage` is
  `observable_listing_count / comparable_listing_count`;
- `marketplace_signal_confidence` is the minimum confidence of observable
  per-card label facts multiplied by that coverage, and is absent when no card
  is observable.

There is no blended "full assessment confidence." Consumers must display and
propagate availability, core confidence, and signal coverage separately. A
core-only assessment may be operationally usable but is not Rocket-enriched.

## Decision Composition

Historical Decision Composition behavior for Competition v1 is unchanged. A
future v2-aware composition may treat all three `COMPLETE_*` v2 states as a
ready Competition core source, but it must propagate the exact availability,
core confidence, and signal coverage. A consumer that explicitly requires the
Coupang signal must require `COMPLETE_WITH_MARKETPLACE_SIGNAL`.

## Domestic Market Validation

ADR-0044 DMV v1 remains unchanged and accepts only its existing complete
Competition v1 source with all four historical metrics. Competition v2 cannot
be submitted to DMV v1.

A future DMV policy/version must explicitly admit Competition v2. Its minimum
direction is to require a complete v2 core and exact cohort manifest; Coupang
enrichment remains optional unless that future policy explicitly requires it.
This ADR does not implement or accept that DMV version.

## API Versioning

The existing
`POST /api/v1/opportunities/{opportunity_id}/competition-observations` remains
Competition v1.

Competition v2 requires a distinct
`POST /api/v2/opportunities/{opportunity_id}/competition-observations` contract.
It submits the immutable cohort manifest, raw core facts, optional Coupang
signal facts, subject binding, and command metadata. The server owns versions
and derived values. V1 and v2 have separate fingerprints and replay namespaces.

## Target and Demand Compatibility

The CR-1B7D4 operational subject union remains unchanged. Competition v2 must
support exactly one historical Market binding or ADR-0060 target binding and
must preserve marketplace/query/category/listing detail as evidence provenance,
not target identity.

Demand observations, analysis, policy, API, snapshots, and admissions are
unchanged. This decision introduces no Demand coupling.

## Historical Compatibility

Competition v1 remains supported for reads, reconstruction, replay, and its
existing API. Existing rows remain under their original policy and must never
be relabeled as listing-based or normalized with the Coupang taxonomy.

No migration or backfill changes historical observations, assessments,
snapshots, current pointers, receipts, fingerprints, or DMV manifests. A new KR
Coupang Founder-assisted admission lacking authoritative seller identity must
use Competition v2 after implementation, not manufacture a v1 count.

## Alternatives Evaluated

### Preserve a true seller-based count

Rejected for the current path because it requires unavailable seller identity
and deduplication. A separate future authority may add it if authoritative
seller IDs become available.

### Use one Rocket-qualified listing count

Rejected as the sole signal. Listing is the authoritative unit, but one combined
count would merge distinct labels and program meanings.

### Model explicit program/fulfillment states

Accepted for Coupang enrichment. It preserves visible observations and permits
taxonomy evolution without fabricating equivalence.

### Make the existing Rocket metric optional

Rejected. Optionality does not repair ambiguous seller semantics or the cohort.

### Separate generic core from marketplace-specific signals

Accepted as the primary architecture. It avoids forcing Coupang concepts into
every marketplace.

### Keep `competitor_count` as the v2 core name

Rejected. `comparable_listing_count` makes the bounded listing-card unit
explicit while preserving historical `competitor_count` meaning.

## Genuine-Run Status and FR-014

This ADR resolves the FR-014 authority decision. It does not implement the new
contract or authorize a production write.

The genuine O2 `fcdb01d411fd46d5bd07020634e5b74c` and target
`cd050cd4f8734a71a61a219de9281a5f` remain stopped with Competition and Demand
not admitted. Captured evidence may be used only after Competition v2 persists
the exact cohort and truthful label states.

## Smallest Implementation PR

One implementation PR should add only Competition v2 core and Coupang signal
domain contracts; cohort/per-card validation; v2 analyzer availability and
confidence; subject-compatible snapshots and SQLite persistence; the API v2
admission/read contract and OpenAPI schemas; Founder-assisted artifact-reference
support; focused domain, persistence, replay, API, compatibility, and production
DB-isolation tests; and synchronized directly affected docs.

It must not add automated Coupang scraping, DMV v2, Demand changes, Decision
Composition v2 support, UI redesign, historical migration, or genuine writes.

## Consequences

- Founder-assisted evidence can be represented truthfully after implementation.
- Future automation targets the same immutable contract.
- Seller identity is neither required nor fabricated.
- Explicit Coupang labels remain distinct and versioned.
- Core Competition can complete without marketplace enrichment while clearly
  disclosing that limitation.
- V1 compatibility is retained at the cost of parallel policy/API support.

## MVP Impact

This is an MVP blocker for truthful genuine Coupang Competition admission, but
not for Demand semantics. The ADR closes the authority decision only. The
genuine run remains stopped until Competition v2 is implemented and validated;
DMV and later stages remain separately blocked.
