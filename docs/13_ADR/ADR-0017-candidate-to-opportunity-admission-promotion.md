# ADR-0017: Candidate-to-Opportunity Admission Promotion

## Status

Accepted

## Decision

An immutable Discovery Candidate remains a pre-admission fact. Validation
Admission creates a separate opaque Opportunity identity and records a one-to-one
`CandidateOpportunityBinding`; Candidate identity is never reused as Opportunity
identity and neither Group identity nor discovery provenance is transformed into
an Opportunity ID.

The Application boundary accepts only Candidate ID plus existing Validation
Admission facts. It reloads Candidate, Context, and issuance provenance from
persistence. Discovery reference and Market identity are never accepted again
from the caller. The persisted Candidate Market identity must exactly equal the
Opportunity market binding.

## Atomicity and replay

The SQLite promotion repository owns one `BEGIN IMMEDIATE` transaction containing
lifecycle current/history, Validation admission snapshot, Opportunity market
binding, Candidate/Opportunity binding, and promotion receipt. Any failure rolls
back the complete admission. Binding and receipt tables are append-only.

One Candidate maps to at most one Opportunity and one Opportunity maps to at most
one Candidate. Exact command replay returns persisted facts without invoking ID
generators, clocks, or admission again. A changed payload under the same command
conflicts. A different command for the same unchanged Candidate subject may add
an alias receipt, following ADR-0016; it cannot change the Opportunity or admission
facts. Separate SQLite connections serialize through the database, not a
process-local lock.

## Snapshot handoff and legacy policy

Promotion is allowed without an `AdmissionSnapshotChainHandoff`. Product,
PriceIntelligence, and EconomicsCalculation snapshots are not yet persisted, so
inventing their IDs or blocking the existing market-identity-only MVP admission
would both violate current contracts. Snapshot-chain readiness remains explicitly
missing and is a later owner-wiring concern.

No existing Opportunity or Candidate is inferred, matched, promoted, or backfilled.
Collector, grouping, Snapshot owners, Production Safety, Review, Decision,
Dashboard, API, and CLI behavior remain outside this decision.

## Relationship to ADR-0059

This decision remains the historical Candidate Promotion v1 contract. ADR-0059
defines an additive v2 admission authority now that Candidate-owned Product
Snapshot capture is persisted. V1 rows, commands, fingerprints, receipts, and
replay retain this ADR's exact meaning and are never migrated or aliased to v2.
