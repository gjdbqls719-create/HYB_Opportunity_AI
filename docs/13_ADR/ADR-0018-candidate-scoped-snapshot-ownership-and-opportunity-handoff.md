# ADR-0018: Candidate-Scoped Snapshot Ownership and Opportunity Handoff

## Status

Accepted

## Context and options

Marketplace collection and Price Intelligence run before Validation Admission,
when an `OpportunityCandidateIdentity` exists but an `OpportunityIdentity` does
not. The previous foundation contracts nevertheless required Opportunity identity.
Persisting them would therefore require a fake or prematurely issued Opportunity.

Four models were considered: use Candidate directly (A), introduce a generic
Snapshot subject union (B), store optional Candidate/Opportunity fields (C), or
retain Opportunity scope (D). A is selected. B adds abstraction without a second
real owner, C permits ambiguous states, and D violates owner timing.

## Decision

Product Observation and PriceIntelligence snapshots are Candidate-scoped schema
v2 facts. They retain exact Market Observation identity; Price additionally
retains ordered Product snapshot IDs and requires cohort size equality. Candidate
identity, Market evidence identity, and eventual Opportunity lifecycle identity
remain distinct.

Verified Economics is different: its authoritative persistence is created during
Opportunity admission and keyed by Opportunity ID. EconomicsCalculation therefore
remains Opportunity-scoped and may only be captured after promotion. Candidate ID
must never substitute for the Verified Economics Opportunity key.

Production Safety context explicitly carries the immutable Candidate/Opportunity
promotion binding. It validates Product/Price Candidate equality, all Market
identity equality, and Economics/Verified Economics Opportunity equality through
that binding. Runtime reconstruction remains scalar-identical and does not invoke
Collector, analyzer, calculator, or Safety engine.

`AdmissionSnapshotChainHandoff` schema v2 is complete-only and now includes the
promotion binding ID. Empty, optional, inferred, or Discovery-observation-as-
Snapshot references are forbidden. Persistence and owner wiring remain later PRs;
there are no rows to migrate or backfill.
