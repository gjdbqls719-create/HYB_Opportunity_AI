# ADR-0045 Capital Readiness Authority

## Status

Accepted

## Implementation Status

Implemented in CR-1B5A at the Domain/Application and append-only SQLite
persistence boundary. CR-1B5D2J adds a thin request-scoped production entry and
FastAPI route without changing the authority. UI, Capital Gate policy, required-
capital calculation, and Founder capital approval remain separate and deferred.
CR-1B5D2I1 adds an assessment schema v2 for fresh evaluations that requires the
Critical Cost v2 normalization ID to equal the Economics Source Composition's
exact normalization ID. Historical schema v1 replay remains unchanged.

## Context

HYB now has distinct Capital-facing authorities for exact normalized
acquisition costs, Conservative Economics, Critical Cost Completeness, and
Domestic Market Validation. None of those facts alone answers whether one exact
Opportunity has a sufficiently complete and internally consistent evidence set
for investment policy to evaluate.

Existing Decision Readiness and Production Safety serve operational workflows.
They select and interpret different source sets and cannot be relabelled as
Capital evidence authority. Conversely, Capital Readiness must not decide
whether an Opportunity is economically attractive or approved for investment.

## Decision

Introduce an immutable `CapitalReadinessAssessment` owned by the Application.
It answers only:

> Is this exact Opportunity sufficiently evidenced and internally consistent
> to proceed to Capital Gate evaluation?

Its states are:

- `READY_FOR_CAPITAL_REVIEW`: every required exact source is eligible and the
  complete source lineage is internally consistent;
- `BLOCKED`: at least one deterministic prerequisite is absent, unsafe,
  expired, inconsistent, or unsupported.

`READY_FOR_CAPITAL_REVIEW` is evidence admission. It is not profitability,
Capital Gate pass, BUY/INVEST, position sizing, or Founder approval.

## Required Exact Sources

Policy `domestic-commerce-capital-readiness` version `1.0.0` requires:

1. one exact persisted Conservative Economics result with status `CALCULABLE`;
2. one exact persisted Domestic Market Validation assessment with state
   `VALIDATED_FOR_CAPITAL`;
3. one exact persisted Critical Cost Completeness assessment with state
   `COMPLETE`;
4. the exact Founder Sourcing Admission revision, exact Quote revision, exact
   Sourcing Economics Binding, and `VERIFIED_MATCH` fact reconstructed through
   those sources.

The source chain additionally verifies the exact Economics Source Composition,
Acquisition Cost Normalization, Landed Cost Composition, Verified Economics
source tuple, Opportunity identity, discovery reference, and domestic Market
identity. Callers select only the three terminal assessment/result IDs because
the remaining exact IDs are safely reconstructed from their persisted lineage.
No latest-source selection is permitted.

## Conservative Economics Boundary

A negative but `CALCULABLE` Conservative Economics result remains eligible for
Capital review. Capital Readiness does not compare profit, margin, or
`conservative_acquisition_roi` to thresholds and does not copy those values into
its assessment. Economic attractiveness belongs to Capital Gate policy.

A Conservative Economics `BLOCKED` result blocks readiness because its
authoritative numeric result is unavailable, not because of an investment
threshold.

## Domestic Market Validation Boundary

Capital Readiness trusts one exact ADR-0044 assessment and requires
`VALIDATED_FOR_CAPITAL`. It does not reinterpret Competition, Demand, raw market
metrics, evidence confidence, or freshness. It does not authenticate the
operator again and does not select a newer assessment.

## Critical Cost Boundary

Capital Readiness requires one exact `COMPLETE` Critical Cost assessment and
validates that its Landed Cost, Sourcing Binding/Admission, Quote, Verified
Economics, and Opportunity lineage are the same chain consumed by Conservative
Economics. It never reruns Critical Cost policy or converts UNKNOWN to zero.

Fresh schema-v2 readiness additionally requires exact identity equality between
the Acquisition Cost Normalization reconstructed through Conservative Economics
and the normalization named by Critical Cost v2. Opportunity or Landed Cost
equality alone is insufficient. Legacy schema-v1 readiness is historical meaning
and is not rewritten; a fresh evaluation with a legacy Critical Cost assessment
is blocked by source-policy and lineage checks.

## Quote Validity and Historical Time

A fresh assessment compares the exact Quote revision's `valid_until` with the
server-owned `evaluated_at` timestamp. Missing validity or
`valid_until <= evaluated_at` blocks readiness. It never substitutes a newer
Quote revision.

Exact replay is checked before identity or clocks and reconstructs the
historical assessment unchanged. It does not re-evaluate Quote expiry. A
current check requires a new command and produces a new immutable assessment.

## Command, Identity, and Time Authority

The caller supplies command ID, exact Opportunity identity, the three selected
terminal source IDs, `requested_at`, and the supported readiness policy
identity/version. The Application owns exact-source reconstruction, lineage and
prerequisite checks, deterministic reasons, readiness state, and persistence
handoff.

Assessment identity is a dedicated server-owned opaque UUIDv4-style identity.
`evaluated_at` and receipt `committed_at` come from separate server clocks.
Identity and timestamps are not derived from source IDs, command fingerprint,
or SQLite row identity.

## Deterministic Blocking Reasons

Version 1 orders independent blockers as follows:

1. `CONSERVATIVE_ECONOMICS_BLOCKED`
2. `DOMESTIC_MARKET_NOT_VALIDATED`
3. `CRITICAL_COST_INCOMPLETE`
4. `SOURCE_OPPORTUNITY_MISMATCH`
5. `SOURCING_LINEAGE_MISMATCH`
6. `PRODUCT_MATCH_NOT_VERIFIED`
7. `QUOTE_VALIDITY_MISSING`
8. `QUOTE_EXPIRED`
9. `SOURCE_POLICY_UNSUPPORTED`

Malformed commands and missing named persistence rows remain explicit
Application/Infrastructure errors rather than fabricated business results.

## Exact Source Manifest

Every assessment fixes the Opportunity identity and exact IDs for Conservative
Economics, Economics Source Composition, Acquisition Cost Normalization, Landed
Cost Composition, Domestic Market Validation, Critical Cost, Sourcing Binding,
Sourcing Admission/revision, Quote/revision, and Product Match Verification. It
also preserves the exact Quote validity timestamp and readiness policy/version.

The manifest stores references, not profitability numbers or duplicated raw
Competition/Demand facts.

## Persistence and Replay

Two dedicated SQLite tables preserve append-only assessment and receipt
history. `UPDATE` and `DELETE` are rejected. A `BEGIN IMMEDIATE` transaction
performs replay validation, assessment insert, receipt insert, and commit
atomically.

Same command and same payload returns the exact persisted assessment and receipt
without new identity, clocks, rows, source selection, or policy evaluation. The
same command with changed source selection, request time, or policy conflicts.
Multi-connection execution converges on at most one authoritative assessment.
Reads validate exact source integrity and reconstruct historical state without
mutation or re-evaluation.

## Capital Gate and Founder Authority

Capital Readiness contains no minimum profit, margin, ROI, required capital,
available cash, reserve, exposure, concentration, or staged-release rule.
Capital Gate may evaluate those matters only after its own authority audit and
versioned policy decision. Founder capital approval remains a later explicit
human authority and can never be inferred from readiness or Gate output.

## Consequences

- HYB can durably distinguish evidence-ready from evidence-incomplete without
  issuing an investment recommendation.
- Negative but calculable economics reaches Capital Gate, where financial
  thresholds belong.
- Historical readiness remains reproducible across source, Quote, and policy
  changes.
- Existing Decision Readiness, Production Safety, Dashboard, and Founder
  lifecycle semantics remain unchanged.

## Deferred Work

- Capital Gate authority and explicit threshold policy;
- intended order quantity and required-capital authority audit;
- available-capital, reserve, exposure, and concentration ownership;
- Founder capital approval;
- UI exposure.
