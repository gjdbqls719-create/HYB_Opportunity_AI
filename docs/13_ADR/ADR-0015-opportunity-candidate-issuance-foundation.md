# ADR-0015: Opportunity Candidate Issuance Foundation

## Status

Accepted as a read-only Application foundation; durable issuance is pending

## Context

ADR-0012 through ADR-0014 make Discovery command, observation, finalized Group,
and successful execution completion authoritative after restart. Candidate
identity must now be issued from those facts without accepting caller-supplied
Domain aggregates, inferring identity, or prematurely creating an Opportunity.

The persisted Discovery contracts do not contain an authoritative
`discovery_reference`. Finalized Group ID, Product item ID, representative
Observation, title, query, and fingerprints all have different meanings and
cannot substitute for it.

## Decision

Add an immutable `IssueOpportunityCandidateCommand` with distinct issuance and
Discovery command IDs, execution and finalized Group IDs, an explicit discovery
reference, an explicit Candidate Market identity, request time, and schema
version. The explicit request field is the authoritative discovery-reference
source for this foundation. It is preserved exactly and never reconstructed
from persisted Product or Group content.

`IssueOpportunityCandidate` loads the authoritative persisted Discovery command,
completed result, finalized Group, and representative Observation by ID. It
requires exact command/result/execution lineage, rejects successful zero-result,
requires the Group to be in the ordered completed result, and requires the
representative Observation to belong to the same execution.

Candidate Market identity must be explicitly LISTING or CANONICAL_PRODUCT. Its
marketplace must match the representative Observation source, and LISTING item
identity must match the source item exactly. SEARCH_QUERY, CATEGORY, unresolved,
title-derived, query-derived, and category-derived Candidate identities are
rejected.

After all validation, injected generator and clock dependencies create an opaque
`OpportunityCandidateIdentity` and immutable `DiscoveryOpportunityContext`.
Candidate ID is not derived from command, Group, membership, Market identity, or
fingerprint. Candidate issuance remains pre-admission and creates no Opportunity
or lifecycle state.

## No Write or Durable Replay Claim

This foundation performs no write and defines no Candidate repository, SQLite
table, receipt, registry, or cache. The same invocation may therefore call the
generator and clock again and produce another Candidate. It must not be described
as committed, idempotent, restart-safe, or response-loss safe.

A later persistence PR must atomically store issuance and its replay receipt
under `(discovery command ID, finalized Group ID)` before exact replay can be
claimed. Adding a speculative Repository Protocol without a write use case would
not improve this boundary and is intentionally deferred with the persistence
contract.

## Isolation

The boundary does not invoke Collector, grouping, analysis, Snapshot creation,
Safety, Validation Admission, Opportunity lifecycle, Decision, Dashboard, API,
or UI. Existing Discovery persistence errors remain distinguishable and are not
collapsed into generic Candidate errors.
