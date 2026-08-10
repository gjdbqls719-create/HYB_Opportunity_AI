# ADR-0057: Candidate Discovery Handoff Authority

## Status

Accepted

## Implementation Status

Decision only. CR-1B7B1A defines the authority and forward contract. It changes
no Domain, Application, persistence, API, test, or production behavior.

## Context

ADR-0013 persists each `CollectedProductObservation` and each finalized Product
Group as immutable Discovery facts. A finalized Group already fixes one exact
`representative_observation_id`. The representative observation preserves its
source marketplace, source item ID, complete observed Product, observation
time, and Collector provenance/reference.

ADR-0015 requires Candidate issuance to receive an explicit complete
`MarketObservationIdentity` and an explicit `discovery_reference`. It rejects
identity reconstructed from a title, query, category, Product Group, or other
display value. That rule remains correct.

The current production observation assembly nevertheless persists
`candidate_market_identity=None`, and no persisted observation field owns the
Candidate `discovery_reference`. The Finalized Group read can therefore expose
the representative observation but cannot provide the complete authoritative
Candidate request without caller invention or read-time inference. The current
Founder journey test opens the observation repository directly and manually
constructs the missing values. This prevents a clean-database production-only
Discovery-to-O1 journey.

## Decision

### Separate selection authority from identity authority

The Founder owns only the decision to select a returned Finalized Group for
Candidate issuance. The Founder does not own machine-known marketplace site,
market, listing scope, source item identity, observation window, or internal
Discovery reference.

Candidate issuance continues to require the explicit complete values in its
request. A production client obtains them from the persisted representative
observation handoff and copies them verbatim. The request remains auditable;
the server does not substitute latest or hidden values.

### Candidate Market identity owner

Choose Option A: the marketplace collector/adapter owns the source Market
identity semantics.

The adapter is the first boundary that knows the marketplace site used for the
network request, the marketplace-native listing identity, the source condition,
and the exact observation time. A Candidate-capable collector emits an explicit
candidate-ready `MarketObservationIdentity` together with its `CollectionFact`.
The Discovery Application validates and persists that value unchanged; it does
not infer it from the normalized Product, title, URL, query, category, or Group.

Generic collectors are not required to guess a Candidate identity. A collector
without an explicitly supported handoff contract may continue to produce a
valid Discovery observation, but that observation is not Candidate-eligible.

### eBay US Market identity semantics

Candidate handoff policy `discovery-candidate-handoff / 1.0.0` initially
supports only a collection request whose explicit marketplace site is
`EBAY_US`. The eBay adapter owns the following versioned mapping:

- `market`: `US`;
- `marketplace`: `ebay`;
- `scope`: `listing`;
- `marketplace_item_id`: the exact eBay Browse API `itemId` string;
- `condition`: the exact meaningful source condition when supplied, otherwise
  `None`;
- `window_started_at` and `window_ended_at`: the same single timezone-aware
  `observed_at` used by the emitted `CollectionFact`;
- `canonical_product_id`, `normalized_query`, `category`, and
  `variant_identity`: `None` under policy v1.

`EBAY_US -> US` is not a generic string transformation. It is an explicit rule
owned by this eBay policy version. The adapter must retain the exact marketplace
site that was used for collection and must fail closed for a site without an
approved mapping. Existence of an item ID alone never implies listing scope.

A normalized placeholder condition is not source identity. If eBay does not
supply a meaningful condition, the Candidate Market identity carries `None`.

### Candidate discovery reference meaning and owner

The Candidate `discovery_reference` is a dedicated opaque internal reference to
the exact Candidate handoff admitted for one collected observation. It is not:

- the external product URL;
- the marketplace item ID;
- the Collector provenance `source_reference`;
- the observation ID, execution ID, or Group ID;
- a Founder review statement.

Choose Option B: the Discovery Application owns this reference. During new
observation assembly/admission it obtains the reference from an injected opaque
identity supplier and fixes it in the same immutable observation fact as the
Candidate Market identity, execution, observation ID, and external Collector
provenance.

The reference is never computed from those values and does not replace them.
The observation's immutable payload and fingerprint bind them together. This
keeps the external Collector reference available as provenance while giving
Candidate lineage a distinct server-owned identity.

### Issuance time and persistence

Candidate handoff facts are created before the observation is committed:

1. the eBay adapter emits the exact Candidate Market identity with the
   collection fact;
2. the Discovery Application validates the supported handoff policy and issues
   the dedicated Candidate discovery reference;
3. observation assembly creates one immutable observation containing both
   facts and the policy identity/version;
4. the existing observation repository persists that value atomically with the
   rest of the observation.

The smallest persistence shape extends the existing
`CollectedProductObservation`; no shadow table or second Candidate identity
system is introduced. It reuses `candidate_market_identity` and adds:

- `candidate_discovery_reference`;
- `candidate_handoff_policy_name`;
- `candidate_handoff_policy_version`.

These optional fields have an all-or-none invariant. New handoff-capable rows
require the exact policy `discovery-candidate-handoff / 1.0.0`. A new observation
schema version must preserve their historical meaning. Existing observation
schema/history remains readable unchanged.

### Handoff eligibility

Persisted observation does not imply Candidate eligibility. One observation is
Candidate-eligible only when all of the following are true:

- a complete LISTING or CANONICAL_PRODUCT Candidate Market identity is present;
- a non-empty dedicated Candidate discovery reference is present;
- a supported handoff policy name/version is present;
- the Market identity exactly agrees with the observation's source
  marketplace/item and observation-time invariants;
- the Collector/site contract is supported by that policy.

No new state machine is required. Eligibility is a deterministic invariant over
the immutable observation. Missing, partial, or unsupported handoff facts fail
closed.

### Historical rows

Historical observations with `candidate_market_identity=None` remain valid
historical Discovery observations and remain ineligible for new Candidate
issuance. They are not backfilled, migrated, or reinterpreted through current
eBay policy. Existing persisted Candidates and exact Candidate command replays
retain their historical contracts.

### Finalized Group representative relationship

A Finalized Group continues to own its exact representative observation ID.
Future handoff reads load handoff facts only from that observation. They never
select the first member, another eligible member, a latest observation, or a
display-equivalent Product.

The display preview and Candidate handoff must be serialized from the same
persisted representative observation. A missing, malformed, unsupported, or
ineligible representative fails closed; no partial Candidate handoff DTO is
fabricated.

### Candidate request and verification

The Candidate API continues to require the complete explicit
`MarketObservationIdentity` and `discovery_reference`. A client copies them
verbatim from the representative handoff response.

Fresh Candidate issuance must strengthen its existing validation to require:

- the representative observation is Candidate-eligible;
- submitted Market identity equals the complete persisted Candidate Market
  identity, not merely its marketplace/listing subset;
- submitted discovery reference equals the persisted dedicated Candidate
  discovery reference;
- all existing command/result/execution/Group/representative lineage checks.

The current Candidate owner checks scope, marketplace, and LISTING item identity
but does not perform both new exact equalities because the persisted handoff
facts do not yet exist. CR-1B7B1 must add those checks; this ADR adds no code.

ADR-0015's no-reconstruction rule remains valid. Copying an already persisted
authoritative handoff value into an explicit Candidate request is not
reconstruction from Product or Group display data.

### Replay and read purity

Discovery replay and Finalized Group reads return the originally persisted
handoff facts. They never regenerate a reference, rerun the adapter mapping, or
apply the currently deployed policy to historical rows. Reads create no
observation, Candidate, receipt, or other persistence fact.

### Marketplace extensibility

Policy v1 supports only explicit `EBAY_US` listing observations. Other eBay
sites and other marketplace collectors are unsupported until their exact
market, scope, listing identity, condition, and observation-window semantics are
approved under a versioned handoff policy. Unsupported collectors may still
participate in Discovery but cannot silently become Candidate-eligible.

### Future Finalized Group read contract

CR-1B7B1 should extend the existing Finalized Group response additively. A
nested representative handoff DTO should expose, from the exact representative
observation:

- observation ID;
- complete Candidate Market identity;
- dedicated Candidate discovery reference;
- handoff policy name/version;
- observation time;
- external Collector provenance/reference as context.

Display title, image, marketplace, price, currency, URL, Group identifiers,
membership, and statistics remain unchanged. Display fields are never identity.

## Relationship to ADR-0013

ADR-0013's optional explicitly supplied Candidate Market identity remains the
storage foundation. This decision makes that value mandatory only for new
Candidate-eligible production observations and adds the all-or-none reference
and policy manifest. Historical optionality and append-only history remain
unchanged.

## Relationship to ADR-0015

ADR-0015 remains authoritative for explicit Candidate requests and its ban on
late inference. This decision establishes an earlier explicit authority from
which a client can copy those request facts. It does not permit Candidate
identity or reference reconstruction from title, URL, item ID, query, category,
Group membership, or display preview.

## P0 Closure Contract

The production P0 is closed only when a new clean file-backed database can
complete:

```text
EBAY_US Discovery
-> persisted Candidate-eligible observations
-> Finalized Group GET with exact representative handoff
-> Candidate POST copying those values verbatim
-> Product Snapshot capture
-> Candidate Promotion
-> O1
```

The proof must use production HTTP boundaries only between business steps and
must not use raw SQLite, a private repository read, URL/title parsing,
caller-created Market identity, caller-created discovery reference, read-time
mapping, or a hidden fallback.

## Consequences

- Founder selection remains explicit while machine-known identity is
  server/collector-owned.
- Candidate validation becomes stricter without changing its request shape.
- Existing observation persistence is extended rather than duplicated.
- Historical rows are reproducible and never silently upgraded.
- Marketplace support expands only by explicit versioned policy.
- CR-1B7B1 becomes a bounded Domain/Application/persistence/read-contract/API
  implementation rather than a new ingress architecture.

## Out of Scope

- production implementation or tests;
- ItemScout/manual initial ingress;
- new Candidate or Opportunity domains;
- group selection automation;
- UI or authentication;
- O2, Capital, Purchase, Actual Outcome, or Variance behavior.
