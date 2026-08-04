# ADR-0009: Discovery Identity Issuance and Snapshot Ownership Timing

## Status

Accepted as a contract foundation; production propagation is pending

## Context

The current production orchestrator collects Products, groups them, evaluates
PriceIntelligence and Economics, executes the legacy Safety path, and returns an
OpportunityResult before Validation Admission. Opportunity ID is optional on the
admission command and otherwise generated while the admission lifecycle is
built. The authoritative Market Observation identity is likewise supplied and
bound at admission. OpportunityResult has neither identity.

PR29–PR31 snapshots require both identities at their owner boundaries. Creating
those snapshots in the current flow would therefore require inferred identities,
downstream ownership, or premature lifecycle creation.

## Options

### A. Pre-issued OpportunityIdentity

This is mechanically simple and minimally changes snapshot contracts. It also
creates an ambiguous state: an object named Opportunity exists before the only
authoritative lifecycle and admission transaction. Never-admitted and failed
candidates would need new Opportunity lifecycle semantics.

### B. OpportunityCandidateIdentity with admission promotion

A ProductGroup candidate receives a distinct immutable identity. It remains a
candidate until Validation Admission explicitly binds it to an
OpportunityIdentity. This preserves existing lifecycle creation semantics and
makes abandoned candidates truthful. It requires a deliberate later alignment
of PR29–PR31 pre-admission references and persistence wiring.

### C. Unbound source identity with later binding

This maximizes source reuse but separates every downstream lineage from its
evaluation subject. It requires the largest PR29–PR31 redesign and increases the
risk of binding unrelated sources during admission.

## Decision

Choose option B.

`OpportunityCandidateIdentity` identifies exactly one ProductGroup candidate in
one discovery execution. The Discovery Orchestration boundary owns issuance
after grouping is finalized and before any candidate-owned Snapshot is created.
Issuance is not lifecycle creation, queue admission, or Opportunity promotion.
The contract does not generate IDs; command idempotency and durable issuance
receipts belong to the persistence PR.

`DiscoveryOpportunityContext` explicitly carries candidate identity, an explicit
listing or canonical-product MarketObservationIdentity, discovery execution ID,
command/correlation ID, timezone-aware request time, and schema version.

The context must be passed as an argument through collection result capture,
Product Observation ownership, Price analysis, Economics calculation,
OpportunityResult, and admission handoff. Global state, thread-local context,
title/item/query-derived identity, and implicit defaults are prohibited.

## Market Identity

SEARCH_QUERY and CATEGORY identities describe collection scope, not the market
subject of one candidate Snapshot. A candidate context therefore accepts only
an explicitly supplied LISTING or CANONICAL_PRODUCT identity. The existing
collector currently returns Product alone and cannot provide the full identity
window. Production propagation remains blocked until the collection boundary
returns or is supplied an authoritative identity envelope. Callers must not
derive it from Product text, item ID, query, or category.

Within a candidate chain the Market identity is invariant. A discovery execution
may contain many ProductGroups and therefore many candidate identities and
candidate Market identities. Current grouping assigns each Product to one group;
cross-candidate source reuse is not introduced by this ADR.

## Admission Handoff

`AdmissionSnapshotChainHandoff` records an explicit candidate-to-Opportunity
promotion and carries the candidate and resulting Opportunity identities, exact
Market identity, ordered Product Observation Snapshot IDs, PriceIntelligence
Snapshot ID, EconomicsCalculation Snapshot ID, admission command ID, handoff
time, and schema version.

Candidate and Opportunity discovery references must match. Admission must later
validate exact Market identity and complete Snapshot lineage. The legacy
ProductionSafetyAssessment is not part of this new handoff and is unchanged.

## Retry, Concurrency, and Failure Semantics

The same committed discovery command and candidate payload must replay the same
candidate identity and context. A changed payload under the same command must
conflict. Concurrent execution requires a future durable issuance receipt; this
PR intentionally provides no process-local generator or registry.

Collection failure, zero Products, or zero groups creates no candidate. A failed
group analysis, Economics failure, rejected candidate, failed admission, or
response-loss retry does not silently create an Opportunity. Issued candidates
and their source lineage must be retained append-only until an explicit future
retention policy marks them rejected or abandoned. Deletion, expiry, and cleanup
semantics are intentionally not invented here.

Admission failure must leave already committed owner Snapshots intact; admission
is a later binding transaction, not a transaction spanning separately executed
collection, analysis, and calculation stages.

## Legacy Compatibility

Existing Opportunities have no candidate identity and are not backfilled.
Existing Validation Admission continues to create or accept Opportunity IDs.
Existing orchestrator, grouping, formulas, legacy Safety execution, Decision,
Dashboard, and APIs are unchanged. Candidate-aware production wiring must be an
explicit later entry point and cannot silently alter the legacy flow.

## Consequences

- Pre-admission subjects are named without pretending they are admitted Opportunities.
- Existing Opportunity lifecycle states and creation timing remain unchanged.
- Snapshot ownership can become explicit once collection supplies authoritative Market identity.
- Automatic discovery can retain and audit rejected or abandoned candidates later.
- Durable retry, persistence, retention, and PR29–PR31 identity alignment remain follow-up work.

## Out of Scope

- SQLite repositories, tables, schemas, migrations, transactions, or receipts
- Snapshot creation, persistence, or production orchestrator wiring
- Safety execution, assessment persistence, API, or UI
- Decision, Dashboard, formula, grouping, or lifecycle changes
- Identity inference, legacy migration, or backfill
