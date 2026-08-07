# ADR-0034: Founder-Assisted Sourcing Authority

## Status

Accepted (CR-0B)

## Context

Capital-Ready Commerce needs authoritative answers for supplier, sourcing
product/option, commercial terms, MOQ, shipping, lead time, evidence, and the
relationship between the selling Product and the sourcing Product. Existing
`Product.seller`, marketplace grouping, Product similarity, Verified Economics,
OCR Review, Decision Readiness, and Founder lifecycle approval own different
meanings and cannot be renamed into this authority.

Runtime Snapshot terminology also does not fit a commercial offer that can be
changed by its supplier. A supplier offer has stable identity and immutable,
append-only revisions.

## Decision

The Founder-assisted Sourcing Application boundary owns manual admission.
Infrastructure will eventually persist facts but does not issue business
identity or interpret sourcing meaning.

### Identity

- `SupplierIdentity` uses a server-issued opaque `supplier_id`. Supplier name,
  platform, and external reference are attributes, never identity derivation.
- `SourcingProductIdentity` uses a server-issued opaque ID and explicitly binds
  Supplier, external product/listing reference, option, SKU, URL, and observed
  time. Product title is not identity.
- `FounderSourcingAdmission` and Product Match Verification use separate opaque
  identities issued only on a fresh, validated command path.

### Quote and revision

`SupplierQuoteRevision` is selected instead of `SupplierQuoteSnapshot`. One
stable quote ID has immutable revisions. Initial admission is revision 1; a
later supplier offer appends revision N+1 while retaining admission, Supplier,
Sourcing Product, quote, selling lineage, and verified match identity.

Money and quantity facts carry explicit `KNOWN`, `UNKNOWN`, or
`NOT_APPLICABLE` availability. Unknown values cannot carry numeric zero.
Shipping is represented independently for supplier-side shipping,
international freight, and domestic inbound; every scope is explicit. Lead time
has the same absence discipline. This contract does not define the complete
Economics cost taxonomy.

### Product match authority

An explicit `ProductMatchVerification` binds exact Opportunity/Candidate/
promotion/Product Snapshot/Market identity lineage to one Sourcing Product.
Only `VERIFIED_MATCH` is admissible. Existing similarity output may be preserved
as optional score/version provenance, but it cannot create verified authority.

### Evidence

`SourcingEvidenceReference` preserves exact external references and may embed
the existing immutable `ArtifactReference`. OCR may extract source material but
is not a Sourcing fact or verification authority. Existing Market Evidence,
Economic Evidence, and External Signals retain their current meanings.

### Replay and failure

Command ID selects an immutable receipt. Canonical payload fingerprint covers
the complete command intent in deterministic order. Same command and payload
replays the committed result before generators or clocks run; changed payload
conflicts. Generated IDs are not authoritative until repository persistence
succeeds. Repository protocols expose initial admission, quote revision,
receipt/replay, current lookup, and exact revision lookup only.

### Economics handoff

`SourcingEconomicsSourceReference` can later bind Verified Economics to an exact
admission and quote revision. Sourcing does not calculate Economics, populate
Verified Economics, or change any formula in this decision.

## Consequences

- Founder-assisted manual sourcing can gain explicit authority without a
  supplier API or fabricated facts.
- Unknown shipping, MOQ, quantity, and lead time cannot silently become zero.
- Supplier offer changes remain auditable revisions rather than mutable rows.
- SQLite durability and restart replay remain unimplemented until a separate PR.
- Supplier identity reconciliation across independent admissions remains a
  future authority decision; this foundation issues a new opaque Supplier for a
  fresh initial admission.

## Explicitly deferred

- SQLite tables, transactions, migrations, triggers, and backfill
- FastAPI, UI, OCR integration, supplier collectors, and external supplier APIs
- Economics formula or existing Snapshot Chain changes
- Conservative Economics, Capital Readiness, Capital Gate, and capital-bound
  Founder approval
- autonomous sourcing, Shadow Mode, and Paper Portfolio
