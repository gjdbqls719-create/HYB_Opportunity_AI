# ADR-0049: Domestic Selling Opportunity and Cross-Market Lineage Authority

## Status

Accepted (CR-1B5D2A)

## Implementation Status

CR-1B5D2B implements the immutable Domain/Application admission foundation,
versioned KR-only policy, exact O1 lifecycle/Promotion/Product Snapshot/Market
reconstruction port, replay-first owner, O2 lifecycle and Market-binding
construction, receipt contract, and dedicated UUIDv4-style O2/admission identity
suppliers. CR-1B5D2B1 implements the shared-connection SQLite boundary that
atomically persists O2 lifecycle creation, its initial transition, immutable KR
Market binding, admission history and command receipt with append-only replay,
restart, rollback, corruption detection and one-O1-to-one-O2 cardinality.
Sourcing domestic-lineage handoff, production composition, API/UI, and trusted
operator injection remain deferred.

CR-1B5D2C implements the deferred additive Sourcing handoff. The legacy
Candidate-Promotion `SellingProductLineage` remains unchanged, while the new
`DomesticSellingProductLineage` pins the exact persisted admission, O1 and O2
identities, source Product Snapshot, KR Market identity and embedded product-
equivalence evidence reference. The existing Founder Sourcing owner validates
that manifest before issuing identities, still requires a separate verified
Supplier Product Match, and persists the O2-owned admission without copying O1
quotes or Economics.

CR-1B5D2D implements the thin production wiring. The Opportunity-scoped
Domestic Selling admission route composes the existing owner, SQLite authority,
dedicated identity suppliers and UTC clocks per request. The existing Sourcing
route accepts an explicit domestic admission-ID reference while preserving the
legacy Candidate payload; the Application reconstructs the full persisted
lineage and retains the independent verified Product Match requirement. The
private Founder/operator boundary remains caller-identified and does not claim
authentication or authorization.

## Context

The production Founder Discovery profile currently creates eBay/US Candidate
and Opportunity lineage. Candidate Promotion fixes that source lineage in one
immutable Candidate-Opportunity binding and one immutable Opportunity Market
identity binding. Domestic Market Validation policy version 1, by contrast,
requires the exact Opportunity Market identity to be `KR` and rejects an
Opportunity bound only to eBay/US.

The current model has no persisted fact that says a product represented by a
foreign source Opportunity is the product that the Founder intends to evaluate
and sell in Korea. Direct Validation Queue admission does not establish that
relationship, Review requires an existing Opportunity Market binding, and
Sourcing `ProductMatchVerification` proves a selling-product-to-supplier-product
match rather than a foreign-source-to-domestic-selling match.

An implicit US-to-KR conversion would rewrite the meaning of historical source
facts. Reusing one Opportunity with two market roles would also conflict with
the current one-Opportunity/one-immutable-Market-binding repository and with
Sourcing, Economics, Domestic Market Validation, and Capital Readiness, all of
which require one exact Opportunity lineage.

## Decision

Introduce an immutable Application-owned authority named
`DomesticSellingOpportunityAdmission`.

For Domestic Commerce policy version 1, the authority preserves the original
foreign/source Opportunity and creates a distinct KR domestic-selling
Opportunity:

```text
source Opportunity O1 (eBay/US)
  -> DomesticSellingOpportunityAdmission
  -> domestic-selling Opportunity O2 (KR)
```

O1 is never mutated, re-bound, archived to make room for O2, or reinterpreted as
domestic. O2 is the Opportunity consumed by KR market evidence and every new
Capital-facing Sourcing and Economics fact.

The admission is a valid immutable fact; it does not add `PENDING`, `APPROVED`,
or `REJECTED` lifecycle states. Missing or invalid admission means that no
domestic-selling lineage exists.

## Why a New Opportunity Is Required

`OpportunityIdentity` does not embed market or country, but the persisted
architecture gives each Opportunity exactly one immutable
`OpportunityMarketIdentityBinding`. Candidate Promotion also gives each
Candidate and promoted Opportunity exactly one immutable binding. Domestic
Market Validation, Competition and Demand admission, Sourcing Economics,
Conservative Economics, Capital Readiness, Capital Gate, Founder Approval, and
Real-Money Execution all compare exact Opportunity identities.

Adding a second target-market role to O1 would make the meaning of its single
Market binding ambiguous and require broad reinterpretation of accepted
contracts. A new O2 preserves those contracts: each Opportunity still has one
Market identity and one downstream economic meaning.

O2 uses a new server-owned opaque `opportunity_id`. Its required
`discovery_reference` is a distinct namespace-qualified reference to the
immutable domestic-selling admission, not O1's discovery reference. This
avoids the active-lifecycle uniqueness conflict and makes the non-Discovery
origin explicit. It is never derived from O1, product text, Market identity,
command fingerprint, or a database row.

## Authority Owner and Trust Boundary

The HYB Application owns:

- exact reconstruction of O1 and its immutable Market binding;
- reconstruction and validation of exact Candidate Promotion and Product
  Observation Snapshot lineage;
- KR target-market policy validation;
- product-equivalence verification requirements;
- O2 Opportunity identity and admission/binding identity issuance;
- O2 lifecycle creation and immutable KR Market binding;
- final admission state, server timestamps, persistence, and replay.

The first MVP boundary is Founder/operator-assisted. The caller may select exact
persisted source references, submit the target KR listing or canonical-product
Market identity, and identify the evidence inspected. The caller cannot supply
O2's authoritative Opportunity ID, admission/binding ID, server timestamps, or
final admission state.

Production wiring must obtain the operator identity from a trusted
Founder/operator boundary. A raw caller assertion, title match, similarity
score, or canonical-looking string cannot admit the relationship by itself.

## Product Equivalence Authority

The `DomesticSellingOpportunityAdmission` is the v1 authority that records the
Founder's verified intent that the exact source product is the product to be
evaluated for domestic sale. It must pin at least:

- O1 `OpportunityIdentity` and exact source Market identity binding;
- the exact Candidate ID and Candidate-Opportunity Promotion binding;
- the exact Product Observation Snapshot selected as the source product;
- the exact O2 `OpportunityIdentity` and immutable KR Market identity binding;
- an operator verification event and non-empty evidence/reference identifying
  what was inspected;
- requested, verified, admitted, and committed times defined by the future
  command and receipt contract;
- policy and schema versions.

The Application must reconstruct those source records and verify their
Candidate, Opportunity, discovery reference, Market identity, and Product
Snapshot lineage. It must not accept caller-assembled lineage without source
validation.

The target identity must use the existing listing or canonical-product Market
scope and `market=KR`. Search-query and category identities do not identify the
commercial product for this admission.

Existing Sourcing `ProductMatchVerification` is not reused for this decision.
It verifies a selling product against a supplier product after a selling
lineage exists. Watchlist strong identity and `canonical_product_id` are also
not cross-market equivalence authorities. They may be inspected as evidence,
but neither title nor identifier equality creates this admission.

## Source Provenance and Historical Immutability

The admission preserves exact O1 provenance. O1's Candidate Promotion, Market
binding, Product Observation Snapshot, existing Verified Economics, Sourcing,
and other historical facts remain unchanged and continue to mean eBay/US source
facts.

O2 does not reuse O1's `discovery_reference`, Candidate-Opportunity binding, or
Market binding. The admission is the explicit bridge through which O2 can trace
back to O1. No existing row is updated or migrated.

## KR Policy Version 1

The initial policy is limited to a domestic selling target:

- target market is exactly `KR`;
- target Market scope is listing or canonical product;
- O2 receives exactly one immutable KR Opportunity Market binding;
- no arbitrary country-to-country graph or automatic market mapper is created;
- no product equivalence is inferred from title, keyword, score, source
  marketplace, sourcing facts, or shared identifier text.

A later target-market policy requires a new policy version and an explicit
decision. It cannot reinterpret an existing admission.

## Downstream Consumer Contract

Domestic Market Validation, Competition, and Demand must consume O2 and O2's
exact KR Market identity. They must not reinterpret O1 or look up a latest
cross-market mapping.

All Capital-facing sources must converge on O2:

```text
O2 / exact KR Market binding
  -> Competition and Demand
  -> Domestic Market Validation
  -> O2-bound Founder Sourcing Admission
  -> O2-bound Sourcing Economics Binding
  -> Landed Cost / Allocation / FX / Normalization
  -> O2-bound Verified Economics and Economics Source Composition
  -> Conservative Economics
  -> Capital Readiness / Gate / Approval / Execution Intent
```

Capital Readiness's exact Opportunity and Market-lineage comparisons remain
unchanged. O1 and O2 sources cannot be mixed in one Capital manifest.

## Sourcing Relationship

Sourcing exists to supply the domestic-selling Opportunity, so new
Capital-facing Sourcing Admissions must be bound to O2.

The legacy `SellingProductLineage` remains Candidate-Promotion-specific and
cannot attach O1's Candidate binding to O2. The additive
`DomesticSellingProductLineage` consumes the exact persisted
`DomesticSellingOpportunityAdmission`, retains O1 provenance, and owns the
normal Founder Sourcing Admission under O2. It does not fabricate a Candidate-O2
promotion binding or weaken the existing Product Match requirement.

Existing O1 Sourcing Admissions remain immutable foreign-source history. They
are not re-keyed to O2. For the first MVP, a new O2-bound Sourcing Admission and
product-to-supplier `ProductMatchVerification` is required. Automatic quote or
match carry-forward is deferred.

## Economics Relationship

Existing Verified Economics and Economics results keyed to O1 remain O1 facts.
They are not silently copied, relabelled, or selected as O2 facts.

The Capital-facing chain must create or admit exact O2-bound Verified Economics,
Sourcing Economics Binding, Landed Cost Composition, Acquisition Cost
Normalization, Economics Source Composition, and Conservative Economics. Their
current exact-Opportunity checks remain authoritative.

## Identity and Cardinality

The Application issues independent opaque identities for O2 and the immutable
domestic-selling admission/binding. UUIDv4-style production suppliers are the
existing project policy. Neither identity is derived from source Opportunity,
Candidate, product, Market identity, title, command ID, fingerprint, or row ID.

Policy version 1 uses the narrow cardinality:

- one source Opportunity may have at most one admitted KR domestic-selling
  Opportunity;
- one domestic-selling Opportunity has exactly one source admission;
- multiple source Opportunities cannot converge into one O2;
- the system does not infer that two separate admissions mentioning equal
  canonical-product text are the same domestic Opportunity.

General many-to-many cross-market identity reconciliation and product
deduplication are deferred.

## Persistence and Replay

Future persistence must be append-only and commit, in one transaction:

1. O2 lifecycle at `DISCOVERED`, version 1, matching the existing fresh
   Opportunity admission convention;
2. O2 immutable KR Market identity binding;
3. immutable domestic-selling admission/binding;
4. command receipt.

The repository must validate exact O1 source records and subject cardinality
under write serialization before issuing fresh server identity and time.

Replay is command-based:

- same command and same exact source, target, product-equivalence, operator, and
  policy payload returns the persisted O2 and admission;
- the same command with changed payload conflicts;
- a different command for the already-admitted source subject converges as a
  subject alias only if the exact payload is equivalent; otherwise it
  conflicts;
- exact replay and subject alias do not call identity suppliers or clocks;
- restart returns the same O2, Market binding, admission, and receipt;
- no latest source, latest target identity, or active policy is substituted.

Generated loser identities from failed or concurrent attempts are never
authoritative. Historical admissions, bindings, and receipts reject UPDATE and
DELETE.

## Direct KR Ingress Alternative

Independent KR Opportunity ingress is valid for a product that originates in a
domestic workflow, but the current public Validation Queue request does not
carry an authoritative Market identity and Review requires a binding that
already exists. Therefore neither is a production KR Opportunity authority.

For the immediate eBay/US Founder flow, the explicit O1-to-O2 admission is the
shortest safe path because it preserves useful Discovery provenance. A future
direct-KR ingress may reuse the O2 lifecycle/Market-binding creation policy but
must use a separate command contract with an explicit domestic source owner. It
must not make O1 provenance optional inside this admission or overload direct
Validation Queue admission.

## Production Ingress Direction

A later thin production boundary may use a project-consistent route equivalent
to:

```text
POST /api/v1/opportunities/{source_opportunity_id}/domestic-selling-admissions
```

The request supplies exact source-selection, KR target Market identity,
verification evidence, operator boundary, command ID, and caller time facts.
The response exposes the persisted O2 identity, KR Market binding, source
admission reference, receipt timestamps, and replay status. The API must not
create Competition, Demand, Sourcing, Economics, Capital, or execution facts
automatically.

## Consequences

- Foreign discovery and domestic selling become separate immutable facts.
- Domestic Market Validation and the Capital chain can keep their exact KR
  Opportunity semantics without weakening ADR-0044.
- Historical O1 records stay valid and reproducible.
- The first implementation requires an O2 creation/admission repository and an
  additive domestic selling-lineage handoff for Sourcing.
- Existing foreign Sourcing and Economics records cannot be reused as domestic
  facts merely because their product data appears equal.

## Deferred

- UI and authenticated/trusted operator injection
- direct KR Opportunity ingress
- automatic cross-market matching and canonical-product reconciliation
- generalized cross-market graphs and non-KR target policies
- automatic Sourcing, Economics, Market Validation, Capital, or execution
  orchestration
