# ADR-0038: Critical Cost Completeness Authority

## Status

Accepted (CR-1B3B)

## Context

`LandedCostComposition` preserves acquisition facts without calculating them,
while `VerifiedEconomicsInput` preserves the current non-sourcing Economics
evidence. Neither contract answers whether those sources are sufficiently
complete and trustworthy for a future Capital evaluation. In particular,
unknown shipping can currently reach the typed Economics adapter as numeric
zero, known shipping may lack allocation authority, mixed currencies lack an FX
source, and an expired quote remains valid historical evidence but must not
authorize a new Capital evaluation.

`VerifiedEconomicsInput.is_ready` and Production Safety own existing operational
meanings. Renaming or expanding either into Capital Readiness would mix source
completeness, profitability, operational recommendation safety, and investment
authority.

## Decision

### Ownership and scope

- `CriticalCostCompleteness` is a separate immutable Domain assessment created
  by an Application owner from one exact persisted Landed Cost Composition, its
  exact Sourcing Economics Binding and Admission/Quote revision, and the one
  persisted Verified Economics Snapshot for the same Opportunity.
- The assessment means only complete or incomplete **under its named policy
  version**. It does not mean profitable, conservative, Capital Ready, Capital
  Gate approved, or Founder approved.
- Production Safety, Decision Readiness, Actual Economics, and Snapshot Chain
  retain their existing meanings and sources.

### Domestic Commerce policy v1

The Application-owned immutable policy
`domestic-commerce-critical-cost-completeness` version `1.0.0` requires:

- known unit purchase cost from the Landed Cost Composition;
- an explicit state for every landed shipping scope;
- allocation authority for every positive known shipping amount;
- expected sale price with `VERIFIED` or `ESTIMATED` evidence;
- marketplace fee, payment fee, fixed fee, tax, duty, and aggregate other cost
  with `VERIFIED` evidence;
- a non-empty evidence reference for every accepted non-sourcing Economics fact;
- an explicit unexpired quote validity time; and
- one common currency across every known Landed Cost component and the Verified
  Economics money contract unless a future authoritative FX source is supplied.

`other_cost` is the current aggregate non-sourcing conditional-cost boundary. It
does not create category-level packaging, labeling, inspection, certification,
storage, or fulfillment facts. A later policy may require those separate facts.
Advertising and returns/refunds/loss allowances are explicit warnings deferred
to Conservative Economics; this decision creates no allowance value.

### Availability, evidence, and applicability

- `KNOWN` means a Landed Cost value exists; it is not the same enum or trust
  claim as `VERIFIED` Economics evidence.
- `UNKNOWN` is blocking and never becomes numeric zero.
- Explicit `NOT_APPLICABLE` shipping is accepted because the exact admitted
  quote and its evidence preserve that applicability assertion.
- Known numeric zero remains zero and requires no allocation denominator.
- `MISSING`, `UNSUPPORTED`, `DEFAULT`, and disallowed `ESTIMATED` evidence are
  blocking according to the field's policy rule. Expected sale price is the
  only v1 field that permits `ESTIMATED` evidence.

### Allocation and FX

- `PER_UNIT` is allocation-ready.
- `PER_QUOTED_QUANTITY` is ready only when the exact quoted quantity is known.
- Positive `PER_ORDER`, `PER_WEIGHT`, or `UNSPECIFIED` shipping remains blocked
  because the required denominator authority does not exist.
- The evaluator never divides by MOQ or quoted quantity.
- Same-currency sources require no FX fact. Cross-currency sources remain
  incomplete until a later exact FX observation contract exists; no rate is
  generated or inferred here.

### Freshness and numeric-result safety

- Historical compositions and quotes remain immutable.
- A new evaluation requires an explicit `valid_until` and blocks an expired
  exact quote; it never selects a later quote.
- The existing typed adapter and legacy dict calculator remain operational
  compatibility paths; they are used by Discovery and therefore retain their
  historical missing-shipping fallback. They are not Capital-facing authority.
- Future Capital-facing calculation must use the completeness assessment as a
  pre-calculation gate. An incomplete assessment cannot authorize calculation;
  explicit known zero can pass while UNKNOWN cannot.
- This PR creates no Capital Economics calculation. Future Capital-facing
  calculation must first consume a complete assessment and then use a separately
  authorized allocation/FX mapping; incomplete assessments expose no profit,
  ROI, or margin result.

### Result and ordering

The result preserves the exact Opportunity, composition, binding, Admission/
Quote source, Verified Economics Opportunity identity/time/version, policy name and
version, evaluation time, deterministic structured blocking/warning reasons,
and schema version. Reason order follows policy category order and is not free
text or set iteration.

### Persistence

Assessment persistence is deferred to a separate PR. This PR stabilizes the
Domain/Application policy and source-validation contract first. The assessment
therefore has no server identity or replay receipt yet and cannot be used as a
durable Capital-decision lineage fact. A persistence PR must add immutable exact
source references, policy version, append-only history, replay, restart,
rollback, and concurrency without changing this meaning.

## Consequences

- Unknown or weak critical costs cannot produce a complete Capital-facing cost
  source assessment.
- Current mixed-currency and positive unallocated shipping compositions are
  expected to be incomplete, accurately exposing missing authority.
- Existing operational Economics and Production Safety semantics remain stable.
- `COMPLETE` remains narrower than Capital Readiness and may carry deferred
  Conservative Economics warnings.

## Deferred

FX observations and conversion, shipping allocation calculation, separate
conditional-cost categories, Conservative Economics, Capital Readiness/Gate,
Founder capital approval, assessment persistence/API/UI, Actual Economics
expansion, supplier collection, and Snapshot Chain extension remain deferred.
