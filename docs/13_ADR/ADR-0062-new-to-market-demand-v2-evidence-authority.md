# ADR-0062: New-to-Market Demand v2 Evidence Authority

## Status

Accepted

## Implementation Status

ADR-0063 supplies the distinct Competition observation identity required by
this ADR's future source reference. Demand must pin that identity and
`cohort_id` to the same one-to-one Competition publication; this clarification
does not implement or admit Demand v2.

CR-1B7D4G implements this decision as an additive Demand v2 foundation. The
domain model, deterministic assessment, admission service, exact v2 POST route,
and dedicated SQLite publication/current/receipt namespace are implemented.
This status does not assert genuine Demand admission, provider availability,
Decision Composition v2, or DMV v2.

CR-1B7D4H corrects the implemented Market Intent envelope to preserve the
Founder-entered `query` separately from an optional exact
`provider_returned_query`. It also implements the ADR's exclusive period
authority variants: either exact `period_started_at` plus `period_ended_at`, or
one exact non-empty `provider_period_label`. HYB neither normalizes the
provider-returned text nor derives dates from a provider label. These fields are
persisted, fingerprinted, replayed, reconstructed, and returned as immutable
evidence. Existing exact-period payloads retain their prior serialized shape
and meaning; genuine Demand remains not admitted.

Demand v1 remains implemented and unchanged. ADR-0064 and its implementation
PRs subsequently implement Domestic Market Validation v2 source preview,
persistence, replay, and final validation POST. Provider integration, Decision
Composition v2, and genuine Demand admission remain unimplemented or unexecuted
as applicable.

The official NAVER advertising customer-center clarification for the current
candidate evidence is `해외검색수 포함`. NAVER/ItemScout total search volume may
include overseas searches and is not Korea-only demand evidence. It therefore
cannot be labeled as the explicit KR query/search count required by this ADR's
current genuine-collection contract. The clarification does not clear the STOP;
an authoritative Korea-only field or a separately approved contract change is
still required.

This ADR architecture-resolves FR-015, the missing authoritative pre-listing
Demand semantics for a genuine new-to-market target. It does not admit genuine
Demand or close the operational blocker. The genuine O2 remains stopped with
Competition v2 verified, Demand not admitted, and Domestic Market Validation
blocked.

## Context

Demand v1 accepts `search_volume`, `review_count`, `rating`,
`coupang_popularity_rank`, `itemscout_popularity_rank`, `sales_proxy`, and
`observed_result_position`. It validates numeric shape and applies analyzer
thresholds, but does not authoritatively define the observation unit, exact
subject, provider population, provider scope, aggregation rule, or whether a
fact is target-specific or contextual.

That ambiguity is unsafe for an ADR-0060 target. Before a KR listing exists, the
target cannot truthfully have KR reviews, a KR rating, KR sales, or a KR search
position. Comparable listing facts cannot be copied into target fields, visible
search order is not a popularity rank, and provider values cannot be treated as
one common scale without an explicit contract.

The business question is narrower than a BUY decision:

> For this new-to-market product, is there sufficient observable evidence of
> Korean market intent and comparable-market engagement to justify deeper
> commercial validation?

Demand remains evidence and assessment. It does not establish verified sales,
profitability, safety, capital readiness, or permission to spend money.

## Decision

Introduce a separate Demand v2 authority with two mandatory pre-listing core
families:

1. `MARKET_INTENT`: one exact provider-scoped count of consumer searches for an
   exact KR query over an explicit observation period.
2. `COMPARABLE_MARKET_RESPONSE`: listing-level review counts from one immutable
   bounded cohort of comparable organic KR marketplace listings.

The following are optional and never make an incomplete core complete:

- comparable listing ratings;
- provider-specific rank, index, or estimated-sales signals;
- sponsored-result engagement context;
- post-listing target traction.

Demand v2 does not retain generic v1 `search_volume`, `review_count`, `rating`,
`coupang_popularity_rank`, `itemscout_popularity_rank`, `sales_proxy`, or
`observed_result_position` fields. Equivalent-looking v2 facts have new,
explicit names and versioned meanings.

## Market Intent Core Authority

The observation unit is one provider field observation. A Demand v2 observation
has exactly one core `market_intent_fact`; additional provider facts belong to
optional provider-signal envelopes or a later Demand observation.

The core fact must preserve:

- opaque fact ID;
- exact assessment subject;
- market `KR`;
- provider name;
- provider field name;
- provider field/schema version or an explicit `unknown` version outcome;
- exact query as entered and normalized query when supplied by the provider;
- geography and locale;
- exact, related, broad, or provider-specific match semantics;
- observation-period start and end, or an explicit provider period label;
- count value and count unit;
- category, device, and result-surface scope when applicable;
- source reference and artifact or response content hash;
- collection method and optional collector name/version;
- observed time;
- raw outcome, status, and factual confidence.

The value must be a non-negative integer count of provider-reported searches or
queries for the named provider field and period. A result count, listing count,
popularity index, rank, trend score, or undocumented UI number is not a core
market-intent count.

Provider values remain provider-scoped. HYB does not add, average, rescale, or
compare counts across providers. A future provider adapter may normalize raw
payload shape into this envelope, but may not claim cross-provider numeric
equivalence.

Coupang, ItemScout, Naver, or another source can supply the core only when the
captured field is truthfully a query/search count and all required semantics are
available. No provider is mandatory. A provider rank or index remains optional
even when that provider also supplies the core count.

The core market-intent family is:

- `COMPLETE` when the one fact has `OBSERVED_VALUE` or `OBSERVED_ZERO`, supported
  count semantics, complete required provenance, and a valid immutable source;
- `UNAVAILABLE` otherwise.

`OBSERVED_ZERO` is complete evidence of a provider-reported zero for the exact
scope. It is not missing evidence and is not silently classified as low demand.

## Comparable Market Response Core Authority

The observation unit is one visible comparable listing card in one immutable
bounded cohort. The business question is:

> What is the typical depth and prevalence of visible consumer review
> engagement among the bounded comparable organic listings?

The core authority is the raw per-listing displayed review count. Callers do not
submit cohort aggregates. The server derives them from the pinned manifest.

Each cohort must preserve:

- opaque cohort ID and exact assessment subject;
- market, marketplace, query/category, locale, and result surface;
- observation window and declared finite result bounds;
- product-use, form-factor, condition, and comparability-policy version;
- artifact reference and SHA-256 content hash;
- every encountered card in result order;
- organic or sponsored placement;
- inclusion, comparability, and exclusion reason;
- stable marketplace item ID when visible, otherwise artifact reference plus
  result ordinal;
- raw title and listing reference;
- per-card review count value or explicit raw outcome;
- per-card evidence reference, observed time, collection method, and factual
  confidence;
- optional rating facts under the separate rating rule below.

The core cohort contains included comparable organic cards only. It must contain
at least one included card. Non-comparable, duplicate, sponsored, and malformed
cards remain in the manifest but do not contribute to the core aggregates.

For every included core card, the review region must be completely observed and
must produce `OBSERVED_VALUE` or `OBSERVED_ZERO` for the family to be complete.
Absence of a visible count is zero only when the selected provider contract
explicitly defines a completely observed absent count as zero. Otherwise it is
`NOT_OBSERVED`.

## Comparable Review Aggregates

The server derives exactly these core values:

- `comparable_listing_count`;
- `review_observable_listing_count`;
- `review_coverage`;
- `review_counts_sorted` in non-decreasing order;
- `median_review_count` using the ordinary median, with the arithmetic mean of
  the two center integers represented as an exact Decimal for an even count;
- `engaged_listing_count`, the number of observable listings with review count
  greater than zero;
- `engaged_listing_share`, using `review_observable_listing_count` as the
  denominator.

Demand v2 does not derive total reviews or mean reviews. A total exaggerates
larger or duplicated marketplace coverage, and a mean is overly sensitive to a
single established listing. Raw per-card facts and the sorted distribution
remain available for inspection.

The family is:

- `COMPLETE` when the cohort is valid, non-empty, and review coverage is 1;
- `PARTIAL` when the cohort is valid and at least one but not every included
  card has an observable review count;
- `UNAVAILABLE` when the cohort is invalid, empty, or has no observable review
  facts.

Partial comparable response is representable but is not usable core evidence
for the first Demand v2 policy.

## Rating Enrichment

Comparable rating is optional enrichment, not core Demand.

Each rating fact is tied to one included comparable listing and preserves its
displayed Decimal value, explicit provider scale and maximum, review-count
relationship, source reference, outcome, time, method, and confidence. A rating
without an observable positive review count is preserved but excluded from the
cohort rating aggregate.

When all aggregate-eligible ratings use the same explicit scale, the server may
derive:

- `rating_observable_listing_count`;
- `rating_coverage` over included comparable listings;
- `ratings_sorted`;
- exact unweighted `median_rating`.

No weighted rating is derived because a displayed review count is not proven to
be the exact population used by the displayed rating. No comparable rating is
called a target rating.

## Bounded Cohort Relationship to Competition v2

Demand v2 may reference an exact immutable Competition v2 cohort rather than
copying it when all of the following match the Demand purpose:

- assessment subject;
- KR market and marketplace;
- query/category and locale;
- observation window and result surface;
- declared finite bounds;
- comparability policy and included organic cards;
- artifact and cohort integrity fingerprint.

The reference must pin the Competition v2 observation ID, observation identity
kind/version, cohort ID, cohort schema/policy version, and integrity fingerprint.
Demand resolves both issued and legacy-compatibility observation identities
through Competition authority, validates the exact observation/cohort pair, and
must not derive an observation ID or select the latest cohort.

Demand then supplies separate review/rating facts tied to the pinned cards and
derives only Demand aggregates. It may not copy `competition_level`, price
pressure, Rocket signals, price metrics, or `comparable_listing_count` as a
Demand assertion. The server may mechanically verify the source card count,
but Demand owns its own derived response manifest.

If the Competition artifact does not expose complete review regions, the cohort
identity remains reusable but new review evidence and artifacts are required.
If the cohort scope is unsuitable, Demand uses a separate cohort under the same
rigorous bounded-manifest rules.

## Sponsored Results, Duplicates, and Variants

Sponsored cards are excluded from core comparable response. Their review and
rating facts may be retained as a separate optional sponsored context and never
affect core aggregates or confidence.

Duplicate and variant rules are:

- one visible listing card is one observation unit, not one seller;
- the same explicit marketplace item ID is included once, with later cards
  recorded as duplicate exclusions;
- distinct item IDs are distinct cards even if titles or seller text match;
- variants within one card are one observation;
- variants rendered as distinct cards with distinct IDs are distinct;
- title similarity never deduplicates cards;
- without an item ID, artifact reference plus result ordinal is the stable card
  reference.

When Demand references Competition v2, it inherits the exact pinned card
membership and duplicate/variant decisions. It does not recompute them.

## Target Traction

Target traction is an optional post-listing family. Its absence before listing
is the explicit `TARGET_LISTING_ABSENT` outcome and does not reduce pre-listing
core availability.

Target traction requires an authoritative append-only listing attachment to the
ADR-0060 target. Only then may a future Demand v2 version preserve exact target
review count, target rating, query/surface-specific target placement, traffic,
or conversion facts.

Observed sales, fulfilled units, refunds, and revenue remain owned by Actual
Sale Settlement and Actual Outcome. Demand may reference those exact sources
for post-launch analysis but must not duplicate them as caller-entered traction.
Provider traffic or conversion remains provider-scoped and cannot be relabeled
as actual sales.

## Provider-Specific Signals

Generic popularity ranks are not part of Demand v2 core. Optional provider
signal envelopes replace `coupang_popularity_rank` and
`itemscout_popularity_rank`.

A rank envelope must preserve provider, exact field, population, surface,
query/category, geography, locale, period/time, directionality, tie semantics,
value, unit, provider/schema version, reference, artifact hash, method, outcome,
and confidence. Ranks with different populations are never averaged or compared
as one generic rank.

Demand v2 has no generic `sales_proxy`. A provider-estimated sales value may be
an optional `PROVIDER_ESTIMATED_SALES` signal only when the provider field,
unit, period, method/version, and estimated status are explicit. Observed sales,
provider estimates, HYB model estimates, and heuristic proxies remain separate.

Demand v2 has no generic `observed_result_position`. Comparable organic ordinal
is card provenance. Sponsored placement is separate. Exact target placement is
optional target traction only after a real listing exists and must identify the
query, surface, placement type, observation bound, and time.

## Raw Fact Outcomes

Every raw fact uses one explicit outcome:

- `OBSERVED_VALUE`: a supported non-zero value was observed;
- `OBSERVED_ZERO`: a supported factual zero was observed;
- `NOT_OBSERVED`: the relevant region or field was not completely observed;
- `SEMANTICS_UNSUPPORTED`: a value or label exists but its meaning is not
  supported by the selected provider contract;
- `EXTRACTION_FAILED`: the source should be readable but extraction failed;
- `PROVIDER_UNAVAILABLE`: the provider or source could not be reached or used;
- `NOT_APPLICABLE`: the fact does not apply to the selected source/scope;
- `TARGET_LISTING_ABSENT`: target traction cannot apply because no target
  listing attachment exists.

The first two require a value and complete observation provenance. The latter
six require no value and preserve a reason. Unknown, missing, unavailable, and
not applicable never become zero or a low-demand classification.

## Confidence and Coverage

Confidence measures factual capture/extraction confidence, not probability of
commercial success.

Demand v2 keeps separate values:

- `market_intent_confidence`, equal to the exact core intent fact confidence;
- `review_coverage`, observable review cards divided by included core cards;
- `comparable_response_confidence`, the minimum confidence of observable core
  review facts multiplied by review coverage;
- optional `rating_coverage` and `rating_confidence`;
- one confidence per optional provider signal;
- one coverage/confidence pair per future target-traction group when relevant.

There is no averaged overall confidence. Optional evidence cannot increase or
reduce core confidence. Consumers must propagate family confidence and coverage
separately.

## Assessment Availability and Output

The overall assessment availability is:

- `COMPLETE_CORE`: Market Intent is complete and Comparable Market Response is
  complete;
- `PARTIAL_CORE`: at least one core family contains observable evidence but the
  two-family core is not complete;
- `UNAVAILABLE`: neither core family contains usable observable evidence or a
  required source invariant fails.

The assessment exposes:

- exact subject and source IDs;
- market-intent family status, provider-scoped fact, presence, and confidence;
- comparable-response status, derived review aggregates, coverage, and
  confidence;
- optional rating aggregates and coverage;
- ordered optional provider signals;
- target-traction status and exact references when applicable;
- overall availability;
- an evidence conclusion;
- ordered reasons and a factual summary;
- generated time and schema/policy versions.

The evidence conclusion is deterministic:

- `SUPPORTS_DEEPER_COMMERCIAL_VALIDATION` only when overall availability is
  `COMPLETE_CORE`, the market-intent count is greater than zero, and
  `median_review_count` is greater than zero;
- `DOES_NOT_SUPPORT_DEEPER_COMMERCIAL_VALIDATION` when overall availability is
  `COMPLETE_CORE` but either the market-intent count or median review count is
  zero;
- `INCONCLUSIVE` when overall availability is not `COMPLETE_CORE`.

This conclusion means only that the two minimum observable pre-listing signal
families do or do not support continuing commercial validation. It is not proof
of verified demand, a forecast, a recommendation, Capital validation, or a BUY
decision. No high/medium/low demand level is emitted because the repository has
no calibrated cross-provider strength thresholds.

## Provider Evidence Envelope

Founder-assisted and automated collection use the same immutable factual
envelope. The caller or collector supplies raw provider facts, provider labels,
scope, source references, artifact/response hashes, observed times, collection
metadata, and outcomes. The server owns observation/cohort/assessment IDs,
supported contract and policy versions, validation, derived aggregates,
availability, conclusion, receipt, and commit time.

OCR output is never automatically authoritative. OCR may create an extraction
candidate or raw outcome, but Founder verification or a future trusted collector
contract must admit the factual value under the same provider envelope.

## Artifact Authority

Demand v2 reuses the ADR-0030 and Competition v2 external-byte pattern, not
their business semantics.

Manual evidence requires a stable external/local artifact reference and SHA-256
of the exact captured bytes. Automated collection requires an immutable response
or artifact reference and content hash. HYB need not store binary bytes.

The envelope also preserves capture time, MIME/source type where applicable,
provider and collector versions, and per-fact source location. A reference
without a content hash cannot satisfy a mandatory core family.

Replay reconstructs persisted manifests and never calls a provider, recollects
data, runs OCR, or fetches a live page.

## Assessment Subject Compatibility

Demand v2 natively supports exactly one of:

- historical `MarketObservationIdentity`;
- ADR-0060 `NewToMarketDomesticSellingTargetIdentity`.

For a target subject, the opaque target remains the assessment subject while
marketplace, query, category, cohort, card, and provider identifiers remain
evidence provenance. No KR listing ID, canonical-product ID, review history,
rating, or placement is fabricated.

Historical Market subjects retain their exact Market identity checks. The two
subject variants use one discriminated union and never alias each other.

## Versioning and Persistence Direction

Demand v2 reserves:

- policy: `demand-policy-v2`;
- observation: `demand-observation-v2`;
- assessment: `demand-assessment-v2`;
- comparable cohort: `demand-comparable-cohort-v1`;
- provider envelope: `demand-provider-evidence-v1`;
- artifact envelope: `demand-artifact-reference-v1`.

Implementation requires dedicated additive Demand v2 observation/cohort,
assessment, current-projection, and receipt persistence. It must not write v2
payloads into v1 rows or advance v1 current pointers. Existing shared source
tables may be referenced by immutable ID; they are not copied or mutated.

The API direction is a distinct:

`POST /api/v2/opportunities/{opportunity_id}/demand-observations`

Clients submit raw manifests and command metadata. They never submit aggregates,
family availability, confidence results, conclusions, reasons, or assessment
outputs. Demand v1 remains at its existing v1 route.

V1 and v2 have separate command fingerprints, receipt schemas, replay
namespaces, current projections, and conflict rules. A v1 observation cannot
replay or alias into v2. V2 replay returns committed evidence without provider
access or new identity/time issuance. A convergent alias is allowed only when
the complete canonical v2 evidence manifest and exact subject are identical.

## Historical Demand v1 Preservation

Demand v1 remains unchanged in all respects:

- Domain names and existing unresolved historical meaning;
- analyzer thresholds and partial/complete behavior;
- observation and assessment rows;
- current projections and history;
- receipts and fingerprints;
- API request/response contracts;
- Decision Composition behavior;
- ADR-0044 DMV v1 requirements.

There is no migration, backfill, reinterpretation, renaming, or v1/v2 alias.
ADR-0060 target identity and ADR-0061 Competition v2 authority also remain
unchanged.

## Future Collector Boundary

Demand v2 foundation precedes provider integration. The first implementation
must support truthful Founder-assisted envelopes and deterministic analysis
without network calls. It must not claim that Coupang, ItemScout, Naver, or
another provider is integrated.

A future adapter owns provider access and raw extraction. It must preserve
request/response or artifact hashes, provider schema and field versions,
collector/selector versions, per-fact raw references, and explicit failure
outcomes. Automation targets the same envelope and cannot change field semantics
without a new provider-contract version.

## Future Domestic Market Validation Boundary

ADR-0044 DMV v1 is unchanged and cannot consume Demand v2, an ADR-0060 target,
or Competition v2. No DMV v2 exists under this ADR.

A future DMV policy may consume Demand v2 only by exact persisted observation
and assessment IDs. It must be able to require:

- `COMPLETE_CORE` availability;
- the exact Market Intent and Comparable Market Response manifests;
- supported Demand schema/policy versions;
- complete mandatory provenance and artifact hashes;
- separate family confidence and review coverage;
- an explicit operator trust/current-use verification event;
- a policy decision about whether
  `SUPPORTS_DEEPER_COMMERCIAL_VALIDATION` is required;
- optional provider signals only when that future policy explicitly names them.

It must not translate Demand v2 back into the five Demand v1 fields. Competition
v2 remains an independent future DMV input and blocker.

## Genuine Collection Plan

For target `cd050cd4f8734a71a61a219de9281a5f`, the future Founder-assisted plan is:

1. Preserve the exact query `차량용 시트백 수납함`.
2. Select one genuinely available provider field that is explicitly a KR query
   or search count, not a rank/index/result count.
3. Capture provider, field name, geography, locale, match semantics, period,
   count unit, provider schema/version, observed time, source reference,
   artifact reference, and SHA-256. If any semantic item is unknown, record
   `SEMANTICS_UNSUPPORTED` and do not use it as core.
4. Evaluate Competition cohort
   `5237034f-371f-4517-8648-51d4e42dd062` for exact source reuse after the v2
   implementation can reconstruct it. Reuse is permitted only under the cohort
   matching rules above.
5. Capture a complete review-count region for every included comparable organic
   card. Preserve explicit zero separately from not observed. Capture ratings
   only as optional per-card facts with scale and review relationship.
6. Create new artifacts and hashes when the existing Competition capture does
   not expose those review/rating regions. Do not modify the Competition cohort.
7. Do not collect target traction until an authoritative KR listing attachment
   exists.

No value is supplied by this ADR. No provider is claimed to be currently
integrated or externally callable by HYB.

## Alternatives Evaluated

### Demand v1 cleanup

Rejected. Defining the old five fields now would retrofit meaning into historical
rows, fingerprints, snapshots, and DMV v1.

### Provider-centric Demand v2

Rejected as the core architecture. It creates provider lock-in and can confuse
incomparable ranks or indices with generic demand. One provider-scoped count is
retained as Market Intent, while provider-specific signals remain optional.

### Cohort-centric Demand v2

Rejected as the only core. Comparable engagement is reproducible but does not
show that Korean consumers seek the target query or use.

### Two-core-family Demand v2

Accepted. Market Intent plus Comparable Market Response supplies independent,
collectable evidence of search behavior and engagement without requiring target
history.

### One mandatory family with an optional second family

Rejected for the initial policy. Either family alone is too easy to overread:
query counts lack product-response evidence, while review-rich comparables may
reflect a neighboring market with weak intent for the exact query.

## Consequences

- A new-to-market target can be assessed before it has a KR listing or history.
- Mandatory facts are observable and reproducible rather than synthetic.
- Provider counts remain provider-scoped and incomparable values are not fused.
- Comparable engagement uses raw cards, complete coverage, and robust median
  rather than caller aggregates or review totals.
- Optional ratings, ranks, estimates, sponsored context, and target traction
  cannot inflate core completeness.
- Founder-assisted evidence can precede network integration.
- The implementation cost includes new versioned Domain, analysis, persistence,
  API, replay, artifact, and subject contracts.
- Genuine Demand remains blocked until implementation and truthful evidence
  collection complete.
- Future DMV remains separately blocked by target-subject, Competition v2, and
  Demand v2 consumption policy.

## Smallest Implementation PR

`CR-1B7D4G - Demand v2 Evidence Foundation` should implement only:

- Demand v2 raw Market Intent and Comparable Market Response contracts;
- optional rating/provider/target-traction envelope structure without external
  provider integration;
- bounded cohort validation and exact Competition cohort reference validation;
- pure server-derived aggregates, availability, confidence/coverage, conclusion,
  reasons, and summary;
- historical Market and ADR-0060 target subject support;
- immutable artifact reference/hash handling;
- dedicated additive SQLite v2 persistence and replay namespace;
- the dedicated API v2/OpenAPI contract;
- focused v2 and v1-preservation tests and synchronized docs.

It must not implement provider network access, OCR authority promotion,
Competition changes, Decision Composition v2, DMV v2, UI, or genuine writes.

## Genuine-Run Status

```text
O1: c2d4479a7f32437b9b0aefa614ae85c1
KR target: cd050cd4f8734a71a61a219de9281a5f
O2: fcdb01d411fd46d5bd07020634e5b74c
Competition v2: VERIFIED
Competition cohort: 5237034f-371f-4517-8648-51d4e42dd062
Demand: NOT ADMITTED
DMV: BLOCKED
Server: STOPPED
```

This decision creates or changes no genuine fact.
