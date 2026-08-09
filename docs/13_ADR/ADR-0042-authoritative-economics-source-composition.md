# ADR-0042 Authoritative Economics Source Composition

## Status

Accepted

## Implementation Status

CR-1B5D2H exposes the existing owner through an Opportunity-scoped production API.
The entry combines one named normalization with the exact same-Opportunity Verified
Economics snapshot time/schema, preserves READY/BLOCKED as successful business states,
and continues to exclude legacy purchase/shipping fields. The existing Conservative
Economics API consumes the committed result without formula changes.

## Context

ADR-0041 provides one exact, persisted per-unit acquisition cost in an explicit
target currency. HYB also persists `VerifiedEconomicsSnapshot`, which contains
expected sale price and fee, tax, duty, and other-cost facts with evidence
status and provenance. Existing `VerifiedEconomicsInput` also contains legacy
purchase and shipping values. Combining all of those values would double-count
acquisition cost and could turn missing or weak sources into apparently usable
Capital-facing inputs.

The next Conservative Economics step requires one immutable manifest of facts
it is allowed to consume, but this boundary must not calculate profitability or
introduce assumptions.

## Decision

Create `ComposeEconomicsSources` as the dedicated Application owner and
`EconomicsSourceComposition` as its immutable result. The command names exactly:

- Opportunity identity;
- Acquisition Cost Normalization ID;
- Verified Economics Opportunity, snapshot time, and schema version;
- caller request time;
- composition policy name/version.

No latest/current source lookup is permitted. The result uses the acquisition
normalization target currency as its explicit Economics currency.

## Source Ownership Matrix

| Fact | Authority and decision |
|---|---|
| Acquisition cost per unit | Exact Acquisition Cost Normalization; reusable now |
| Legacy purchase cost | Excluded; overlaps normalized acquisition |
| Legacy shipping cost | Excluded; overlaps normalized acquisition |
| Expected sale price | Exact Verified Economics fact; `ESTIMATED` remains estimated |
| Marketplace/payment rates | Exact Verified Economics facts; verified evidence required for READY |
| Fixed fee | Exact Verified Economics fact; verified evidence required for READY |
| Tax rate | Exact Verified Economics fact; preserved as a rate, no tax calculation here |
| Duty cost | Exact Verified Economics money fact; outside ADR-0041's four acquisition components |
| Other cost | Preserved exactly, but non-zero is BLOCKED because current contract has no structured scope |

Duty and other cost are not folded into the normalized acquisition total. The
future calculator must consume each named fact at most once. This ADR does not
decide the future duty formula.

## Double-Count Prevention

`EconomicsSourceComposition` intentionally has no `purchase_cost` or
`shipping_cost` fields. It carries only:

- exact normalization identity, policy, currency, and total acquisition cost;
- exact non-overlapping Verified Economics facts listed above.

No adapter to legacy `VerifiedEconomicsInput` is created in this change.

## Evidence and Blocking Contract

The state is `READY` or `BLOCKED`; it is source readiness only and never means
Capital Ready or profitable.

- expected sale price permits existing `VERIFIED` or `ESTIMATED` status;
- marketplace fee, payment fee, fixed fee, tax, duty, and other cost require
  `VERIFIED` evidence for READY;
- every required source requires its existing evidence reference;
- `MISSING` and `UNSUPPORTED` remain absent and block;
- explicit verified zero remains zero;
- current evidence has no `NOT_APPLICABLE` state, so absence is not converted
  to an N/A zero;
- non-zero `other_cost` blocks as `OTHER_COST_SCOPE_UNRESOLVED` until a scoped
  authoritative contract prevents overlap;
- sale-money currency differing from the acquisition target blocks as
  `CURRENCY_MISMATCH`; this owner performs no FX.

Blocking reason order is deterministic and persisted. No default fee, tax,
duty, other-cost value, Conservative allowance, or fallback is introduced.

## Identity, Time, Persistence, and Replay

The composition identity is a dedicated server-owned opaque UUIDv4 value.
`requested_at` belongs to the caller; `composed_at` and `committed_at` use
separate server clocks.

Two dedicated append-only SQLite tables persist composition and receipt in one
`BEGIN IMMEDIATE` transaction. They preserve the exact source manifest, copied
evidence facts, state, ordered blockers, policy, and timestamps. Existing source
tables are read without migration or mutation; no current/latest projection is
added.

- same command and source manifest returns exact persisted replay;
- changed normalization, Verified source, request facts, or policy conflicts;
- replay occurs before identity and clocks;
- restart reconstructs persisted facts rather than selecting or recomputing;
- UPDATE and DELETE are forbidden;
- partial history or receipt writes roll back.

## Relationship to Existing Boundaries

Critical Cost Completeness remains unchanged. This owner independently validates
the exact normalization and Verified Economics sources and exposes a narrower,
non-duplicating future calculation manifest.

`VerifiedEconomicsInput` remains an existing operational/compatibility contract
and is not overwritten. Conservative Economics must receive this new
composition through a separate future input contract.

Actual Economics remains unchanged. Sale price, fee, tax, duty, and other-cost
facts have corresponding or partial Actual fields, but actual normalized
acquisition components, allocation denominators, exact FX provenance, and a
scoped replacement for `other_cost` remain follow-up gaps.

## Deferred Work

- Conservative Economics and scenario assumptions;
- exact future duty treatment;
- scoped non-zero other-cost admission;
- currency conversion beyond the acquisition normalization;
- Capital Readiness, Capital Gate, Founder approval, API, and UI.
