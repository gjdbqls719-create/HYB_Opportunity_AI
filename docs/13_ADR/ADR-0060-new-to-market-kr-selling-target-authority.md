# ADR-0060: New-to-Market KR Selling Target Authority

## Status

Accepted

## Implementation Status

Decision only. No Domain, Application, SQLite, API, OpenAPI, UI, or runtime
implementation exists. The genuine run remains stopped before O2.

## Context

ADR-0049 admits an existing exact KR commercial product. Its version 1 command
requires a KR `LISTING` or `CANONICAL_PRODUCT` `MarketObservationIdentity`, an
exact source Product Snapshot, and `product_equivalence_confirmed=true`.

The genuine run has reached a different case:

- Candidate `9b047bd45052488a867cd1bcec48633d`;
- finalized Group `44c772c1f42d4e8b9dd93bc929ae2b1b`;
- Product Snapshot `63edc6a8-6d77-45e8-ad06-9f04b8bea282`;
- Product Snapshot Capture `e835d1df-ab9e-43df-a337-efb67c83a858`;
- O1 `c2d4479a7f32437b9b0aefa614ae85c1`;
- Candidate/Opportunity Binding `ff4030797eff47db9a993b30a72f7421`;
- Candidate Promotion v2 Admission `375bcb0ec6df45bba7d49b4f01c1ac85`.

O1 is an eBay/US source Opportunity for the exact persisted source product.
Founder-assisted KR investigation established category and comparable-product
evidence, but did not establish an exact-equivalent KR listing or an
authoritative KR canonical-product identity. A comparable Coupang listing is
not the source product. Consequently neither a marketplace item ID, a canonical
product ID, nor product equivalence can be asserted truthfully.

This is FR-013:

> The exact persisted source product selected at O1 is intended to be evaluated
> as a new domestic-selling product in KR before an exact KR marketplace listing
> exists.

## Existing-Contract Audit

FR-013 is genuinely unsupported.

`MarketObservationIdentity` has four scopes. `LISTING` requires a marketplace
item ID, `CANONICAL_PRODUCT` requires a canonical product ID, `SEARCH_QUERY`
requires a query, and `CATEGORY` requires a category. The existing immutable
Opportunity Market binding accepts only `LISTING` and `CANONICAL_PRODUCT`.
ADR-0049 version 1 applies the same scope restriction and additionally requires
explicit product equivalence.

`SEARCH_QUERY` and `CATEGORY` identify observation scopes, not the exact
commercial product selected at O1. The source eBay item ID is not a KR item ID.
A command fingerprint, database row ID, title, keyword, comparable listing, or
arbitrary canonical-looking string has no authority to fill this gap.

ADR-0044 owns trust admission for exact Competition and Demand evidence, not
commercial-product identity. ADR-0057 owns the collector-originated source
Candidate handoff. ADR-0059 owns O1 admission and its exact source Product
Snapshot lineage. Sourcing Product Match owns a selling-product-to-supplier-
product match only after a selling identity exists. None owns a pre-listing KR
selling target.

## Decision

Choose option B: supplement ADR-0049 with a separate additive authority and
command named `NewToMarketDomesticSellingOpportunityAdmission`.

ADR-0049 remains the version 1 authority for O1 to an already identified exact
KR listing or canonical product. It is not extended, replaced, weakened, or
reinterpreted. The new authority is selected explicitly and never inferred from
missing fields or `product_equivalence_confirmed=false`.

The new authority creates:

1. one server-owned `NewToMarketDomesticSellingTargetIdentity`;
2. one distinct O2 at lifecycle `DISCOVERED`, version 1;
3. one immutable `OpportunityDomesticSellingTargetBinding` from O2 to that
   exact KR target;
4. one immutable admission connecting the exact O1 and Product Snapshot lineage
   to the target and O2; and
5. one command receipt.

These facts commit atomically and append-only. O1 remains unchanged.

## New-to-Market KR Selling Target Meaning

A new-to-market KR selling target means:

> One exact persisted source commercial product, anchored by the O1 Product
> Snapshot lineage, which the Founder has explicitly selected as the product
> subject to evaluate for future sale in KR, before HYB has established an exact
> KR marketplace listing or KR canonical-product identity.

It is a commercial evaluation subject in market `KR`. It is not an observation,
listing, search query, category, supplier product, or assertion that the product
is globally unique.

The target remains the same immutable selling subject if a real listing is
attached later. `pre-listing` describes the facts available when the target was
admitted; it is not mutable lifecycle state.

## Identity Ownership

The HYB Application owns `NewToMarketDomesticSellingTargetIdentity`. Its
identity contains at least:

- an opaque server-issued `domestic_selling_target_id`;
- market exactly `KR`;
- identity kind `new_to_market_domestic_selling_target`; and
- a fixed schema version.

The opaque ID is issued by a dedicated UUIDv4-style supplier after exact source
reconstruction. It is not derived from title, keyword, category, comparable
listing, eBay item ID, command ID, fingerprint, evidence reference, or row ID.
The Founder owns the explicit selection decision, not the opaque identity.

`MarketObservationIdentity` is left unchanged. It truthfully identifies an
observation subject and cannot truthfully represent this pre-listing commercial
target without adding a different semantic meaning to an existing type.

## Admission Authority and Required Source Lineage

The new Application owner must reconstruct and pin:

- O1 identity, lifecycle status/version, and exact eBay/US Market binding;
- the common Candidate/Opportunity binding;
- for ADR-0059 v2, the exact Product Snapshot capture command, ordered Product
  Snapshot cohort, and representative Product Snapshot;
- the exact selected source Product Snapshot and its source observation;
- the server-issued KR target identity;
- the distinct server-issued O2 identity and its target binding;
- Founder/operator decision and evidence provenance;
- policy/schema versions and requested, admitted, and committed times.

The named source Product Snapshot must belong to the exact persisted promotion
source manifest. No latest Snapshot, representative substitution, title match,
or caller-assembled lineage is accepted.

## Pre-listing KR Market-Binding Semantics

`OpportunityDomesticSellingTargetBinding` is the additive O2 Market binding for
this authority. It binds exactly one O2 and discovery reference to exactly one
`NewToMarketDomesticSellingTargetIdentity`, with a server binding time and fixed
schema version.

It does not pretend to be `OpportunityMarketIdentityBinding` version 1 and does
not contain marketplace, marketplace item, canonical product, observation
window, query, or category placeholders. A version-aware resolver may expose
the two binding variants as a discriminated union, but persisted v1 binding
rows and DTOs retain their exact historical shape.

Downstream facts for this O2 are keyed to O2 and the exact target identity.
Individual evidence entries retain their own Coupang listing, query, category,
reference, and observation provenance. Evidence subject and target identity are
not collapsed into one value.

## Evidence Taxonomy

### Product identity evidence

Required identity authority is the exact persisted O1 Product Snapshot and its
ADR-0059 source manifest. The Founder command additionally records a non-empty
factual selection reason. A separate title or comparable is not identity.

### Market, category, and comparable evidence

These facts describe whether and how the KR category appears commercially.
They are not required to issue the target identity and do not prove demand or
low competition. If referenced by the admission, they are contextual evidence
only. Capital-grade use still requires normal Competition, Demand, and
ADR-0044 Domestic Market Validation admission under O2.

### Absence and search evidence

Selection of this mode requires a bounded search manifest that records at
least the searched KR channels/marketplaces, search/query or category scope,
performed-at time, operator, stable evidence references, and the conclusion
`exact_kr_identity_not_established`.

This is authoritative only as an immutable record of what that bounded search
and operator review established at that time. It is evidence, not authoritative
proof that no equivalent product exists anywhere in Korea. A limited search
must never be persisted or displayed as universal absence.

### Operator decision provenance

The command requires operator identity, non-empty decision reason,
timezone-aware verification and request times, the exact search manifest, and
the supported policy version. Caller identity remains an audit fact until a
trusted authentication boundary exists. The Application owns admission state,
identities, and server times.

## Comparable Coupang Products

Comparable products never become the target identity. Their exact listing and
evidence references belong to Competition and Demand observations and may later
be pinned by Domestic Market Validation. Category facts remain category
evidence. A comparable may become an exact target listing only through a later
explicit attachment supported by product-identity evidence; similarity alone
cannot create that attachment.

## O1, Product Snapshot, Target, and O2 Lineage

```text
ADR-0059 O1 (eBay/US)
  -> exact Candidate Promotion v2 source manifest
  -> exact source Product Snapshot
  -> Founder new-market selection + bounded KR search evidence
  -> NewToMarketDomesticSellingOpportunityAdmission
  -> server-owned KR selling target
  -> distinct O2 / immutable target binding
  -> O2-owned Market, Sourcing, Economics, and Capital facts
```

O1 is source provenance only. O2 does not reuse O1's Market binding,
Candidate/Opportunity binding, discovery reference, Economics, Safety, Sourcing,
or Capital facts.

## Later Real KR Listing Attachment

A future real Coupang listing does not mutate the original target binding and
does not rewrite the admission. It creates an append-only
`DomesticSellingTargetListingAttachment` that binds the exact target ID to one
complete real KR `LISTING` or `CANONICAL_PRODUCT` Market identity, exact product-
identity evidence, operator/source provenance, policy version, and attachment
time.

The original O2 remains the Opportunity for that target. Attachment alone does
not create another Opportunity. A distinct Opportunity requires an explicit
decision that the listing is a materially different commercial product or
variant; equality is never inferred.

One target may have zero or more historical listing attachments. Exact replay
returns the committed attachment. A changed assertion conflicts and cannot
overwrite an earlier attachment. An attachment is evidence and relationship
authority, not a mutation of the pre-listing fact.

## Downstream Compatibility and Implementation Blockers

The following current contracts directly assume a listing/canonical
`MarketObservationIdentity` and require implementation changes before the new
O2 can traverse them:

| Area | Current blocker | Required additive change |
| --- | --- | --- |
| Identity and Opportunity binding | `MarketObservationIdentity` has no target scope; `OpportunityMarketIdentityBinding` rejects non-listing/canonical subjects. | Add the target identity and target-binding variant; keep v1 unchanged. |
| SQLite Market binding | `opportunity_market_identity_bindings` stores only observation-scope columns and reconstructs only `MarketObservationIdentity`. | Add separate append-only target/binding tables and a fail-closed version-aware resolver. |
| ADR-0049 admission/API | Domain, Application, SQLite, web DTOs, serializers, and OpenAPI require target Market identity plus equivalence `true`. | Add a separate command/route/publication; do not add nullable mode fields to v1. |
| Operational eligibility | The shared result is typed only as `OpportunityMarketIdentityBinding`. | Return the discriminated binding union. |
| Competition and Demand | Observation subjects and ingress require exact equality with the v1 Market binding; DTOs, fingerprints, snapshots, and SQLite serialize `MarketObservationIdentity`. | Permit the target identity as the O2 assessment subject while keeping comparable listing/query/category details in evidence provenance. |
| Domestic Market Validation | Command, source manifest, Domain assessment, exact-source checks, external-signal lookup, and SQLite serializer require one `MarketObservationIdentity`. | Add target-subject support under a new policy version; continue pinning exact Competition/Demand sources. |
| Founder Sourcing | `DomesticSellingProductLineage` reconstructs only ADR-0049 admission and requires listing/canonical identity plus equivalence evidence. | Add a distinct new-to-market lineage/reference variant that pins the new admission and target identity; retain independent verified Supplier Product Match. |
| Verified Economics | Operational admission requires a non-null v1 Market binding through the shared eligibility contract. | Recognize the target-binding variant; no O1 values may be copied. |
| Capital Readiness | It compares Sourcing lineage Market identity to Domestic Market Validation manifest identity. | Compare the same target identity after both upstream contracts support it. |

Conservative Economics, Sourcing Economics Binding, Landed Cost, Allocation,
FX, Normalization, Critical Cost, Capital Gate, Founder Approval, Real-Money
Execution, Purchase, and Actuals are keyed through exact O2 and upstream source
IDs rather than independently constructing a listing identity. Their business
semantics remain compatible once the listed ingress, Sourcing, Market
Validation, and Capital Readiness blockers are resolved. They require regression
proof against mixed O1/O2 and mixed binding variants, not reinterpretation.

## Cardinality

- One O1 may have at most one KR domestic-selling O2 across ADR-0049 and this
  authority combined.
- One new-to-market target belongs to exactly one O2.
- One O2 has exactly one immutable binding variant.
- Multiple O1s cannot converge into one target.
- A target may have zero or more append-only later listing attachments.
- A later attachment does not create a second O2.
- Existing ADR-0049 admissions retain their existing one-O1-to-one-O2 rule.

Cross-table enforcement under one write serialization boundary is required so
concurrent ADR-0049 and new-to-market commands cannot create two O2s for one O1.

## Replay and Persistence

The new command fingerprint includes the exact O1 and Product Snapshot source,
bounded search manifest, Founder decision provenance, policy, and schema. It
excludes server identities and server times.

- Same command and exact payload replays the persisted target, O2, admission,
  binding, and receipt without clocks, identities, searches, or latest reads.
- Same command with changed payload conflicts.
- A different command for the same O1 and exactly equal subject may append only
  an alias receipt and return the same result.
- A different command for the same O1 with changed source, evidence, decision,
  policy, or authority mode conflicts.
- ADR-0049 and new-to-market commands never alias each other.
- Target, O2 lifecycle, target binding, admission, and receipt commit in one
  `BEGIN IMMEDIATE` transaction.
- History and receipts reject UPDATE and DELETE. Reconstruction validates exact
  schemas, integrity fingerprints, source rows, and cross-table cardinality.
- Reads never attach a listing, select latest evidence, rerun a search, or
  upgrade a historical row.

## Historical Preservation

ADR-0049 remains unchanged for existing exact KR listing/canonical admissions.
All v1 commands, payloads, Market bindings, admissions, O2s, Sourcing lineage,
receipts, fingerprints, replay, and rows keep their original meaning. There is
no migration, backfill, target synthesis, or cross-mode alias.

ADR-0059 remains unchanged. O1 still means only Founder selection of one exact
Candidate/Product lineage for deeper validation. This authority consumes that
lineage; it does not add economics, safety, market validation, or investment
meaning to O1.

## Rejected Alternatives

### Extend ADR-0049 with a nullable mode

Rejected because ADR-0049's single immutable meaning is exact source-to-existing
KR product equivalence. Allowing false equivalence or absent target identity
would make old and new rows semantically conditional and risk cross-mode replay.

### Replace ADR-0049

Rejected because its implemented existing-product path is valid and historical
rows must remain exact.

### Reuse another existing authority

Rejected because Discovery owns source observations, Domestic Market Validation
owns evidence trust, and Sourcing owns supplier matching. None may issue the KR
commercial selling identity.

### Add a universal canonical-product graph

Rejected as unnecessary. One narrow O1-to-KR target authority and optional
listing attachments resolve the genuine case without generalized matching or
deduplication.

### Use a comparable, category, source item, or fabricated identifier

Rejected as semantic fabrication and cross-market reinterpretation.

## This Authority Does Not Mean

- BUY-ready;
- proof of demand;
- proof of low competition;
- verified or conservative economics;
- Production Safety;
- Capital Readiness, Capital Gate pass, or Founder Capital Approval;
- proof that no equivalent product exists anywhere in KR;
- supplier Product Match;
- a real marketplace listing;
- permission for real-money execution.

## Genuine-Run Status

FR-013 is architecture-resolved by this ADR and implementation-open. The
genuine run remains exactly:

```text
O1 c2d4479a7f32437b9b0aefa614ae85c1
-> FR-013
-> no O2 yet
```

No genuine database row is created or changed by this decision.

## Exact Next Implementation PR

The smallest next PR is `CR-1B7D3 - New-to-Market KR Selling Target Admission
Foundation` with this exact scope:

- additive target identity, admission, target-binding, command/publication,
  policy, replay, and error contracts;
- exact ADR-0059 v2 source-manifest reconstruction;
- dedicated server identity suppliers and clocks;
- additive append-only SQLite target/admission/binding/receipt tables with
  cross-authority one-O1-to-one-O2 enforcement;
- a separate strict production route
  `POST /api/v1/opportunities/{source_opportunity_id}/new-to-market-domestic-selling-admissions`;
- response/OpenAPI schemas and Domain/Application/SQLite/API tests for creation,
  replay, alias, conflict, corruption, rollback, restart, concurrency, v1
  preservation, and the genuine lineage shape.

That PR creates no genuine O2 during tests or deployment, does not mutate the
production database, and does not add downstream Competition, Demand, Sourcing,
Economics, Capital, listing attachment, or UI support. Those remain separately
bounded follow-ups after the O2 admission foundation exists.

## MVP Impact

The decision removes the architecture ambiguity blocking the first genuine
new-to-market case. It does not by itself advance the run or prove the Real-
Money Validated MVP. After CR-1B7D3, the run may create O2 only when genuine
operator evidence satisfies the new contract; downstream identity support must
then land before Market Validation and the Capital chain can continue.

The implementation PR requires HIGH reasoning because it introduces a second
immutable Opportunity binding variant, cross-authority cardinality, and
fail-closed historical reconstruction while preserving all v1 rows.
