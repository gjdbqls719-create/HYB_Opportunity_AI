# ADR-0044 Domestic Market Validation Authority

## Status

Accepted

## Implementation Status

Decision only. Domain/Application implementation, SQLite persistence, production
composition, and Capital Readiness integration are deferred to subsequent PRs.
Existing Competition, Demand, Review, Decision Readiness, and web contracts are
unchanged by this ADR.

## Context

Capital Readiness needs to know whether one exact Opportunity has enough trusted
domestic market evidence to enter a Capital review. The existing operational
market-intelligence path cannot answer that question safely.

The current Competition and Demand APIs accept `status`, `confidence`, `source`,
`reference`, and `collection_method` from the caller. `MarketEvidence` validates
their shape and value consistency, but does not authenticate who assigned a
`VERIFIED` or `HUMAN_VERIFIED` status. Competition analysis requires four values
but does not validate their trust authority. Demand analysis permits a partial
assessment. Decision Readiness selects the latest Competition and Demand
snapshots and checks identity and version, but does not pin an exact source
manifest or enforce Capital-grade trust, completeness, or freshness.

OCR Human Verification and Founder Review create durable human-verified external
signals. Those facts can assist provenance inspection, but approving an OCR
candidate or external signal is not approval of a Competition or Demand
assessment.

The Capital-facing trust boundary therefore must be distinct from raw market
observations, operational analyses, and operational Decision Readiness.

## Decision

Introduce a future immutable Application-owned authority named
`DomesticMarketValidationAssessment`. It answers only:

> Do these exact domestic market sources satisfy the versioned evidence trust
> policy for this Opportunity at this validation event?

Its terminal states are:

- `VALIDATED_FOR_CAPITAL`: the exact source manifest satisfies the selected
  domestic validation policy and has a durable Founder/operator verification
  event;
- `BLOCKED`: one or more deterministic policy requirements are not satisfied.

`VALIDATED_FOR_CAPITAL` does not mean profitable, Capital Ready, Capital Gate
pass, BUY, INVEST, position size, or Founder capital approval.

## Authority Layers

The market evidence flow has three separate layers:

1. Raw Market Observation preserves imported or collected facts and descriptive
   provenance supplied at ingress.
2. Market Analysis derives Competition and Demand assessments from those exact
   observations.
3. Domestic Market Validation admits an exact, reviewed source manifest as
   sufficient for Capital Readiness under a versioned policy.

Raw evidence never becomes Capital-authoritative merely because its caller-set
status is `VERIFIED` or `HUMAN_VERIFIED`. Market Analysis output is analytical
evidence, not a trust admission.

## Validation Owner

The HYB Application owns Domestic Market Validation state, policy resolution,
exact-source reconstruction, deterministic blocking reasons, identity issuance,
replay, and persistence coordination.

For the first Domestic Commerce MVP, the verification boundary is
Founder/operator-assisted. The operator reviews the exact persisted source
manifest and submits verification facts. The Application, not the raw request,
determines whether the committed assessment is `VALIDATED_FOR_CAPITAL` or
`BLOCKED`.

An operator identifier, request timestamp, or caller assertion alone cannot set
Capital validation state. Production exposure must obtain operator identity from
the trusted Founder/operator boundary used by the application; a public raw
request must not self-certify trust.

## Domestic Scope

Policy version 1 is limited to Domestic Commerce:

- the authoritative Opportunity Market identity must be domestic (`KR`);
- every required observation and assessment must carry the exact same
  `MarketObservationIdentity` as that Opportunity binding;
- marketplace and observation scope remain explicit parts of that identity;
- cross-market or foreign-to-domestic product equivalence is not inferred.

An Opportunity bound only to an eBay/US identity is therefore blocked. A future
cross-market selling-product authority may establish a new exact lineage, but
this ADR does not derive domestic identity from title, keyword, canonical ID, or
sourcing facts.

## Competition Requirements

Domestic Market Validation version 1 requires one exact persisted Competition
observation and its exact persisted assessment snapshot. The required raw
metrics are the existing core Competition metrics:

1. `competitor_count`
2. `rocket_seller_count`
3. `price_spread`
4. `median_price`

All four must be present and valid, and the assessment availability must be
`COMPLETE`. `lowest_price`, `highest_price`, `sponsored_result_count`, and
`organic_result_count` may be preserved as optional source facts but are not v1
completeness requirements.

Derived `competition_level`, `price_pressure`, `rocket_competition`,
`market_concentration`, confidence, and summary are preserved analytical output.
They do not independently prove provenance or trust.

## Demand Requirements

Domestic Market Validation version 1 requires one exact persisted Demand
observation and its exact persisted assessment snapshot. The required raw
metrics are the existing core Demand metrics:

1. `search_volume`
2. `review_count`
3. `rating`
4. `coupang_popularity_rank`
5. `itemscout_popularity_rank`

All five must be present and valid. The Demand assessment must be `COMPLETE`.
`PARTIAL` never satisfies v1 Capital market validation. `sales_proxy` and
`observed_result_position` may be preserved as optional facts, but neither is a
v1 completeness requirement or verified actual demand.

Derived demand level, popularity level, review quality, confidence, and summary
remain analytical output rather than trust authority.

## Market Price and Selling Context

The exact Competition observation's `median_price` and `price_spread` provide
market-price context. Domestic Market Validation verifies the quality and
lineage of that evidence; it does not calculate or replace the expected selling
price owned by Economics Source Composition.

No equality between observed median price and the authoritative expected sale
price is inferred. Market Validation does not recompute margin, ROI, or
Conservative Economics.

## Exact Source Manifest

Every assessment fixes an ordered, immutable manifest containing at least:

- Opportunity identity and its exact domestic Market identity binding;
- Competition observation ID and Competition assessment snapshot ID;
- Demand observation ID and Demand assessment snapshot ID;
- the policy identity and version used for each persisted analysis;
- the exact required evidence entries, including source, reference,
  `observed_at`, collection method, status, confidence, and unit;
- any explicitly selected human-verified External Signal IDs;
- validating operator identity and verification event reference;
- Domestic Market Validation policy name and version;
- requested, verified, admitted, and committed timestamps defined by the future
  command/receipt contract.

The Competition and Demand snapshots must reference their named observations,
and all identities must match the Opportunity's authoritative domestic identity.
The validator loads sources by these IDs. It never substitutes latest
Competition, latest Demand, latest External Signal, or an active policy version.

## Provenance Policy

Every required metric must retain a non-empty source, non-empty exact reference,
timezone-aware observation time, and non-empty collection method. Explicit zero
is a present fact where the existing metric contract permits zero; UNKNOWN or an
absent value is not zero.

Required metrics must also use an observation-bearing ingress status:
`OBSERVED`, `VERIFIED`, or `HUMAN_VERIFIED`. `ESTIMATED`, `UNKNOWN`,
`UNAVAILABLE`, `UNSUPPORTED`, and `EXTRACTION_FAILED` cannot satisfy v1. This
status check rejects an explicitly non-observational fact; it still does not
trust an observation-bearing label as proof of who verified the evidence.

Caller-set MarketEvidence status and confidence remain descriptive ingress
facts. They cannot satisfy Capital trust by themselves. The separate validation
event is the authority that records which exact facts the operator inspected.

Human-verified External Signals may be included only by exact signal ID and
matching Market identity. They may strengthen provenance for named facts, but do
not replace the required Competition or Demand observation and assessment.

## Freshness Policy

The existing operational 30-day Decision freshness window is not promoted to
Capital authority. The repository contains no approved Capital freshness window,
so version 1 invents no duration.

For version 1:

- every required source must have an `observed_at` timestamp;
- source observation time cannot be after the operator verification event;
- the operator must explicitly attest that each exact manifest source was
  checked for current use at that verification event;
- missing timestamps or missing freshness verification block validation;
- the assessment means validated *at that event*, not fresh for an implicit
  future interval.

A later Capital review cannot silently reuse an old assessment as a current
check. Current validation requires a new command and new verification event.
Any automatic age window requires a new policy version and an explicit owner.

## Completeness Policy

The initial immutable policy is named
`domestic-market-validation` version `1.0.0`. It requires:

- a domestic Opportunity Market identity and exact identity match throughout;
- one exact complete Competition source pair;
- all four required Competition metrics;
- one exact complete Demand source pair;
- all five required Demand metrics;
- complete required provenance for every required metric;
- explicit operator verification of the exact source manifest and freshness at
  the validation event.

It contains no profitability, ROI, margin, required-capital, position-size, or
investment threshold.

## Blocking Reasons

Version 1 uses deterministic ordered reason codes. The future contract should
define codes equivalent to the following order:

1. `DOMESTIC_MARKET_SCOPE_MISMATCH`
2. `SOURCE_LINEAGE_MISMATCH`
3. `COMPETITION_EVIDENCE_MISSING`
4. `COMPETITION_EVIDENCE_INCOMPLETE`
5. `COMPETITION_PROVENANCE_INSUFFICIENT`
6. `DEMAND_EVIDENCE_MISSING`
7. `DEMAND_ASSESSMENT_PARTIAL`
8. `DEMAND_PROVENANCE_INSUFFICIENT`
9. `MARKET_EVIDENCE_STATUS_UNSUPPORTED`
10. `MARKET_EVIDENCE_TIME_UNKNOWN`
11. `MARKET_EVIDENCE_FRESHNESS_UNVERIFIED`
12. `VERIFICATION_MISSING`

Implementation may use project-consistent enum names, but must preserve these
meanings and deterministic ordering. Malformed commands and unavailable
repositories remain errors, not `BLOCKED` business results.

## Verification Receipt

Domestic Market Validation requires an immutable durable command receipt. It
preserves the command ID and fingerprint, assessment ID, exact source manifest,
operator/verifier, requested and verified times, Application-issued admission
and commit times, policy identity/version, and schema version.

The receipt is a distinct Capital market verification event. Existing OCR
verification, Review completion, or observation-admission receipts cannot be
relabelled as this receipt.

## Identity, Replay, and History

The assessment identity is a server-owned opaque identity issued by a dedicated
UUIDv4-style supplier. It is not derived from Opportunity identity, source IDs,
fingerprint, command ID, or a database row.

Replay is command-based:

- same command plus the same exact source manifest, verification facts, and
  policy produces exact replay;
- same command with changed source, verification, or policy conflicts;
- exact replay returns the persisted assessment and receipt without a new ID,
  clock call, verification event, or latest-source lookup;
- changed sources or a current validation check require a new command;
- assessments and receipts are append-only historical facts.

## Existing Asset Reuse

| Existing asset | Decision | Reason |
| --- | --- | --- |
| `MarketEvidence` | REUSE | Preserve raw values and descriptive provenance only; do not use caller-set status as Capital trust. |
| Competition observation/analysis | REUSE | Exact complete source and analysis are required, but do not own Capital validation. |
| Demand observation/analysis | REUSE | Exact complete source and analysis are required; PARTIAL is blocked. |
| Opportunity Validation / Market binding | REUSE | Supplies exact Opportunity and Market lineage, not evidence trust. |
| External Signal Ledger | ASSISTED ONLY | Exact human-verified signals can strengthen named provenance but cannot replace assessment validation. |
| OCR Human Verification | ASSISTED ONLY | Its immutable verification pattern is reusable; OCR approval is not market validation. |
| Founder Review | ASSISTED ONLY | Its operator, receipt, replay, and atomic persistence patterns are reusable through a distinct workflow. |
| Decision Readiness | DO NOT REUSE | Its latest-source operational interpretation is not the Capital market authority. |

## Capital Readiness Consumer Contract

Capital Readiness will consume one exact persisted
`DomesticMarketValidationAssessment` ID. It validates identity, policy/version,
and `VALIDATED_FOR_CAPITAL` state, but does not reinterpret raw Competition,
Demand, or MarketEvidence fields and does not select latest sources.

Capital Readiness must preserve that exact assessment ID in its own source
manifest. A new market validation assessment is consumed only through a new
explicit Capital Readiness evaluation.

## MVP Operational Path

The first safe path may use manual, CSV, API-assisted, or existing observation
ingress. A Founder/operator then reviews the exact persisted Competition and
Demand sources and submits a distinct Domestic Market Validation command.
Unsupported, foreign-market, partial, unverified, or freshness-unknown
Opportunities remain `BLOCKED`.

No ML prediction, provider reputation system, automated trust scoring,
multi-market fusion, generalized crawler, or multi-country policy is required.

## Consequences

- Existing operational APIs and Decision Readiness remain backward compatible,
  but cannot be used as Capital market validation.
- Caller-declared `VERIFIED` and `HUMAN_VERIFIED` values no longer pose a trust
  shortcut in the future Capital path.
- Complete exact Competition and Demand evidence can support a narrow,
  Founder-assisted Domestic Commerce MVP.
- PARTIAL Demand and foreign Opportunity identities remain blocked rather than
  being filled by assumptions.
- Historical validation is reproducible because exact sources and policy are
  pinned instead of selected as latest.
- Capital Readiness can consume one authoritative assessment rather than
  duplicating raw market trust policy.

## Deferred Work

- Domain/Application assessment, command, policy, identity supplier, and reason
  contracts;
- append-only SQLite assessment and receipt persistence;
- production entry and any API/UI exposure;
- trusted operator authentication/injection at a production boundary;
- automated evidence collection and provider trust scoring;
- any approved numeric Capital freshness window;
- cross-market product equivalence and foreign-to-domestic lineage;
- Capital Readiness, Capital Gate, and Founder capital approval.
