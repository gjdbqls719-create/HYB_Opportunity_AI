# ADR-0036: Exact Sourcing Economics Binding

## Status

Accepted (CR-1B2B)

## Implementation Status

CR-1B5D2H exposes the existing owner through an Opportunity-scoped production API.
The entry reconstructs the exact named Sourcing Admission/Quote revision, derives its
Opportunity identity, and delegates binding creation without latest-quote selection or
O2-specific policy.

## Context

An admitted sourcing graph can reconstruct the Supplier, exact Sourcing Product,
quote revision, Human match verification, Opportunity lineage, and quote validity
facts. It did not record which exact admitted revision an Opportunity selected as
the future Economics source. Selecting the latest quote would silently change
provenance when a later revision is admitted.

## Decision

- The Sourcing Application boundary owns `SourcingEconomicsBinding` creation.
- A server-generated opaque UUID-style identity identifies each binding; it is
  never derived from an Opportunity, quote, row sequence, or fingerprint.
- The binding preserves the full `OpportunityIdentity`, exact admission and quote
  revision reference, caller `requested_at`, server `bound_at`, and schema version.
- The repository reconstructs the exact Admission and verifies its Opportunity
  lineage and exact quote reference before an append-only write.
- Multiple explicit commands may bind different revisions for the same
  Opportunity. There is no current projection, overwrite, or automatic latest
  selection.
- The command fingerprint contains only immutable caller facts. Exact replay is
  checked before identity or server clocks and returns the persisted binding and
  receipt after restart.
- Binding history and receipt are committed in one `BEGIN IMMEDIATE` transaction;
  both tables reject UPDATE and DELETE.
- Quote `observed_at` and `valid_until` remain reconstructable from the exact
  Admission. They are facts, not a quote-expiry or Capital Readiness policy.
- `SourcingEconomicsBindingReference` is the narrow future Economics handoff; this
  decision does not change `VerifiedEconomicsInput` or calculate any cost.

## Consequences

A later quote cannot mutate an existing binding or downstream calculation
provenance. Consumers must explicitly choose a binding ID and reconstruct its
authoritative source. Concurrent identical commands converge through the receipt;
changed payloads conflict.

## Deferred

Landed-cost composition, purchase/shipping mapping, UNKNOWN completeness,
conservative Economics, Capital Readiness/Gate, Founder capital approval,
supplier collection, and Snapshot Chain extension remain deferred.
