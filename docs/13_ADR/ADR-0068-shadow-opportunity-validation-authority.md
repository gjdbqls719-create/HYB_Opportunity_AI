# ADR-0068: Shadow Opportunity Validation Authority and Real/Shadow Separation

## Status

Accepted

## Implementation Status

Architecture is **APPROVED FOR MVP FOUNDATION**. This ADR is the decision-only
Shadow PR1. It adds no Shadow production contract, persistence, API, UI,
scheduler, checkpoint, evaluator, or calibration behavior.

ADR-0067 / Deep Audit F2 is **CLOSED**. Completed persisted screening now
provides exact finalized-Group correlation, immutable evaluation and ranking
publication identities, policy and source manifests, structured reasons,
screening-time economics, timestamps, integrity fingerprints, runtime-free
replay, and exact Founder reads. That authority makes a trustworthy Shadow
baseline possible without reconstructing historical screening from the live
engine.

The next implementation cut is Shadow PR2: immutable
`ShadowValidationRegistration` and `ShadowBaselineSnapshot` Domain contracts
inside the existing Opportunity boundary. Until that PR is implemented and
validated, no Shadow registration exists in production.

## Context

Founder capital is limited. HYB may identify more promising Opportunities than
the Founder can fund and launch. If twenty Opportunities appear promising but
only three can receive real capital, discarding the other seventeen also
discards the chance to test HYB's original judgment over elapsed market time.

Shadow Opportunity Validation preserves those unfunded theses and later asks:

> How did the original Opportunity thesis evolve in the real future market?

Its business objective is to validate HYB's historical Opportunity judgment
over real elapsed time without requiring real capital investment in every
candidate. It is longitudinal market-thesis evidence, not pretend commerce.

ADR-0067 supplies authoritative persisted screening, while ADR-0060 supplies an
exact new-to-market KR commercial target and distinct O2. Competition, Demand,
Sourcing, and Economics already own their respective evidence semantics. A
Shadow foundation must compose those authorities without inventing a second
copy of their facts, assigning Shadow meaning to WatchList, or contaminating
Actual Outcome.

## Critical Semantic Boundary

Shadow Validation is not:

- virtual sales or simulated sales volume;
- fake revenue or paper revenue;
- virtual, realized, or actual profit;
- Actual Outcome;
- Conservative-versus-Actual Variance;
- an assertion about HYB's conversion, advertising, reviews, fulfillment, or
  inventory performance; or
- accounting for money HYB never earned or spent.

Because HYB did not launch the Shadow subject, it cannot know HYB's units sold,
conversion rate, advertising performance, reviews, fulfillment quality,
realized revenue, or realized profit. Shadow may evaluate only the historical
market Opportunity thesis against later real market evidence.

## Decision

Shadow Opportunity Validation is an additive capability over the existing
Opportunity boundary.

- No new bounded Shadow domain is created.
- The existing Opportunity boundary owns Shadow thesis, assertion, falsifier,
  and evaluation-result value semantics.
- An Application-level Shadow Validation capability owns registration,
  baseline assembly, future checkpoint publication, and evaluation
  orchestration.
- Upstream evidence owners retain their facts and publication semantics.
- Shadow stores exact references plus the canonical semantic projections it
  actually used; it does not become a second raw evidence warehouse.
- The MVP is manual/on-demand and does not introduce a generic workflow engine.

## Ownership

| Concern | Authority | Shadow relationship |
| --- | --- | --- |
| Shadow thesis and verdict value semantics | Opportunity | Defines the meaning of the registered thesis and future evaluation. |
| Registration, baseline, checkpoint, and evaluation orchestration | Shadow Validation Application capability | Resolves exact authorities, validates time/subject compatibility, and publishes immutable Shadow records. |
| Historical screening evaluation and ranking | Discovery | Shadow references exact ADR-0067 persisted identities and fingerprints. |
| Competition observations and publications | Competition | Remain Competition facts; Shadow may reference comparable exact revisions. |
| Demand observations and publications | Demand | Remain Demand facts with their actual provider, geography, query, cohort, and period semantics. |
| Supplier, quote, and source facts | Sourcing | Remain Sourcing facts and revisions. |
| Economic facts and compositions | Economics | Remain Economics facts; Shadow cannot convert them into realized commerce. |
| Low-level deltas | Change | May calculate compatible changes but does not own the Shadow verdict. |
| Listing lookup and price monitoring | WatchList/Application/Infrastructure mechanisms | May be reused narrowly later; WatchList does not own Shadow meaning or baseline state. |

No generic Opportunity Engine, Shadow workflow platform, or cross-domain
evidence owner is introduced.

## Authoritative MVP Subject

The first authoritative Shadow MVP requires this exact lineage:

```text
Candidate
  -> O1
  -> exact ADR-0060 New-to-Market KR selling target
  -> distinct O2 / immutable target binding
  -> ShadowValidationRegistration
```

The registration subject is the exact O2 plus its exact
`NewToMarketDomesticSellingTargetIdentity` and immutable target binding. The O2
source manifest preserves Candidate and O1 lineage; Shadow must resolve that
persisted lineage and must not accept caller-assembled equivalents.

Candidate-only registration is rejected for the first authoritative MVP. A
Candidate identifies a Discovery handoff, while O2 identifies the commercial
product subject intended for evaluation in KR. Treating the two as equivalent
would permit baseline and checkpoint evidence to refer to different commercial
subjects.

No current code constraint justifies weakening this rule. ADR-0060 and its
implemented immutable target-binding contracts provide the exact subject that
Shadow needs.

## Registration Authority Class

Shadow PR2 begins with one registration authority class only:

`MACHINE_SCREENING_BASED`

It requires one exact persisted ADR-0067 screening evaluation and the exact
ranking publication that referenced it. It may later be eligible for HYB
screening-calibration statistics if all subject, source, and time rules pass.

`FOUNDER_DECLARED` is deferred. A future ADR or contract revision may allow the
Founder to register an explicit thesis when machine score or rank is
unavailable, but such a record must never be presented as machine-ranking
validation and would have weaker or provisional calibration eligibility. The
MVP has no compelling business reason to combine both authority classes before
the machine-based contract is trustworthy.

## Persisted Screening Baseline Authority

A machine-based registration must reference and verify:

- `screening_ranking_publication_id` and publication fingerprint;
- `screening_evaluation_id` and evaluation fingerprint;
- `finalized_group_id` and exact Group membership fingerprint;
- the structured screening and Safety reasons;
- screening, recommendation, Safety, and ranking policy manifests and versions;
- exact used-input and source manifests;
- screening-time expected economics and provenance;
- screening `evaluated_at`; and
- ranking `ranking_created_at`.

Shadow must follow the persisted completion binding, publication, and
evaluation lineage. It must not reconstruct historical screening from the live
engine, current policy, current marketplace data, finalized-Group ordering,
raw historical transient objects, title/URL matching, or any mutable latest
selection. Legacy `SCREENING_NOT_RECORDED_LEGACY` completions are not valid
machine-based Shadow baselines.

## Immutable Registration Contract Direction

`ShadowValidationRegistration` will conceptually preserve at least:

- a server-issued `shadow_validation_id`;
- authority class exactly `MACHINE_SCREENING_BASED` for v1;
- exact O2 Opportunity identity, lifecycle reference, target identity, and
  target-binding identity/fingerprint;
- exact Candidate, O1, promotion, and O2 admission lineage;
- exact screening evaluation/publication IDs and fingerprints;
- exact finalized Group ID and membership fingerprint;
- `registered_at`;
- screening `evaluated_at` and ranking `ranking_created_at`;
- `knowledge_cutoff_at`;
- operator/founder identity and a factual registration reason;
- cadence policy identity/version; and
- registration schema/policy version and integrity fingerprint.

The registration is immutable and append-only. An exact retry may return the
existing registration; changed content must conflict. Correction or a new
thesis requires a new explicitly related registration rather than mutation.

Registration does not create a Purchase Execution, inventory, settlement,
Actual Outcome, Capital decision, or WatchItem.

## Immutable Baseline Snapshot Direction

`ShadowBaselineSnapshot` answers:

> What exactly did HYB know when this Shadow test began?

It is immutable, bound to exactly one registration, and contains the exact
screening authority plus any explicitly admitted target-bound baseline sources
used by the registered thesis. It records availability and missingness rather
than filling unknown evidence with current values or numeric zero.

Registration and baseline may be separate immutable values but must become one
trustworthy atomic persistence boundary in Shadow PR3. A registration must not
be committed as authoritative without its exact baseline, and a baseline must
not float without its registration.

## Baseline Source Manifest

Shadow does not copy every upstream raw provider payload. Upstream authority
remains upstream. For every source it actually uses, the baseline manifest
preserves:

- exact source identity and source kind;
- owning boundary;
- schema/policy version, immutable revision, and integrity fingerprint where
  available;
- the canonical semantic projection actually used by the Shadow thesis;
- observation-window start/end and `observed_at` where applicable;
- source `generated_at`/`evaluated_at` and `committed_at` where supplied by the
  owner;
- provenance, provider, geography, locale, query/category/cohort, unit,
  currency, and period semantics needed for interpretation;
- availability outcome and an explicit missing/unavailable/unsupported reason;
  and
- one top-level canonical baseline-manifest fingerprint.

The manifest uses exact persisted ADR-0067 lineage wherever possible. A source
that lacks a stable historical identity, revision, or truthful semantic
projection cannot be silently replaced by its latest value.

## Time Semantics and Calibration Eligibility

The following times are distinct facts and must not be collapsed:

- upstream source `observed_at` and observation window;
- upstream source `committed_at` or other authoritative availability time;
- screening `evaluated_at`;
- ranking `ranking_created_at`;
- Shadow `registered_at`;
- baseline `knowledge_cutoff_at`; and
- each future checkpoint observation window, publication time, and commit time.

`knowledge_cutoff_at` is the latest evidence-availability boundary admitted to
the baseline. Every admitted baseline projection must have been available no
later than that cutoff, and the cutoff cannot follow `registered_at`. Future
checkpoint windows used as outcome evidence must begin after the cutoff.

The critical calibration rule is:

> Baseline knowledge must predate the future outcome evidence used to judge it.

A registration created after an operator or HYB has seen checkpoint evidence
must never be presented as unbiased historical validation. Future contracts
will expose explicit eligibility rather than infer it at read time:

- `ELIGIBLE`: exact machine screening and O2 lineage, trustworthy cutoff, and
  no checkpoint evidence available before registration/cutoff;
- `PROVISIONAL`: useful longitudinal evidence with an unresolved timing,
  coverage, or provenance limitation, never silently counted as unbiased; and
- `INELIGIBLE`: known hindsight, incompatible subject/evidence, or another
  violation that forbids calibration use.

This ADR defines the concepts only. It does not implement a calibration engine
or claim that a future registration is eligible merely because it exists.

## Future Checkpoint Direction

Checkpoint cadence is versioned policy data. A 7/14/30/60/90-day sequence is a
possible initial policy, not a Domain constant and not a promise that every
source can be observed at each interval.

Initial checkpoint execution is manual/on-demand. Each checkpoint will be an
immutable publication bound to the registration, cadence policy, intended
window, actual observation windows, exact source identities/revisions,
availability outcomes, committed time, and integrity fingerprint.

Scheduler, cron, alerts, retries, background workflow infrastructure, and
generic orchestration platforms are deferred. They are not prerequisites for
starting trustworthy baseline collection.

## Future Re-observation and Comparability

A checkpoint may later reference exact new publications such as Competition
v2, Demand v2, Sourcing quote revisions, Economics source compositions, and
authoritative listing observations. Comparison is allowed only when the
evidence is semantically comparable, including compatible:

- exact commercial target;
- provider and field semantics;
- geography and locale;
- query/category/cohort and result-surface policy;
- marketplace and inclusion/exclusion rules;
- units, currencies, aggregation, and periods; and
- schema/policy versions or an explicit reviewed compatibility rule.

An unavailable or incompatible source produces explicit missing/inconclusive
evidence; it is not coerced into a delta. Change may compute low-level deltas
after compatibility is established, but Opportunity owns the thesis verdict.

NAVER/ItemScout total search volume may include overseas searches. It must not
be relabeled, compared, or aggregated as KR-only Demand evidence. The existing
genuine-run geography STOP and Demand v2 evidence semantics remain unchanged.

## Future Thesis Evaluation

The future value is named `ShadowThesisEvaluation`, not
`ShadowActualOutcome`. Its outcome language is:

- `MAINTAINED`;
- `WEAKENED`;
- `INVALIDATED`; or
- `INCONCLUSIVE`.

The evaluator belongs to the Opportunity boundary and consumes only one exact
baseline plus compatible checkpoint publications. Each thesis should evolve
toward structured, machine-evaluable assertions, thresholds, directionality,
and falsifiers rather than free text alone. Human explanation may accompany the
structured result but cannot replace its evidence lineage.

This ADR does not define the final assertion schema, thresholds, or evaluator
algorithm and does not implement evaluator code.

## Real and Shadow Separation

This is a hard evidence boundary:

| Real Launch / Actual Outcome | Shadow Opportunity Validation |
| --- | --- |
| Requires the real execution and settlement chain appropriate to the result. | Requires no Purchase Execution. |
| May use actual acquisition and sale settlements. | Uses market-thesis observations only. |
| Can preserve actual sold quantity, revenue, costs, and realized profit/loss when the evidence is calculable. | Has no HYB units sold, revenue, realized costs, or actual/virtual profit. |
| Evaluates HYB's realized commerce outcome, including operational friction. | Evaluates how the historical market Opportunity thesis evolved. |
| May support Conservative-versus-Actual Variance. | Must not populate Actual Outcome or Variance contracts. |

Future cross-surface contracts should discriminate evidence meaning explicitly,
for example `REAL_COMMERCE` versus `SHADOW_MARKET_THESIS`. These are semantic
classes, not interchangeable confidence levels. Shadow evidence cannot be
promoted into Real evidence by a score, elapsed time, Founder review, or missing
real launch.

This ADR does not modify any Actual Outcome, Actual Settlement, Purchase
Execution, inventory, or Variance contract.

## Calibration Safety

Future read-only Shadow statistics may include:

- thesis maintenance rate;
- weakening rate;
- invalidation rate; and
- inconclusive/evidence-coverage rate.

Shadow and Real Outcome denominators must remain separate and visibly labeled.
Shadow results do not automatically retrain scoring, change thresholds, update
policy, revise historical screening, or initiate ML training. No individual
evaluation or aggregate statistic can mutate a production decision policy.

Any automatic learning, threshold adjustment, model training, or policy update
requires evidence from collected baselines and a separate ADR.

## WatchList Relationship

WatchList is not Shadow authority. The current WatchList is a mutable,
primarily price-monitor-oriented capability around watched marketplace items.
A `WatchItem` cannot serve as an immutable Shadow registration or baseline.

Future Shadow orchestration may reuse narrow listing-lookup or price-observation
adapters through Application/Infrastructure mechanisms. Reuse does not transfer
Shadow business meaning, thesis ownership, baseline identity, checkpoint
publication, or verdict ownership to WatchList. This ADR does not expand or
modify WatchList.

## F1 Recovery Relationship

F1 durable Discovery attempt/failure/retry/resume remains an independent
production-reliability P1. It is not a prerequisite for registering Shadow
against a successfully completed, authoritative ADR-0067 screening evaluation.

Shadow must fail closed for incomplete, legacy-unbound, or corrupt screening;
it does not repair Discovery history. This ADR does not implement F1 or combine
F1 with the Shadow PR sequence.

## Scenario Simulation Relationship

Scenario Simulation asks:

> What happens under explicit economic assumptions?

Shadow Opportunity Validation asks:

> What actually happened to the market Opportunity thesis over elapsed time?

They may eventually reference the same target identity or upstream evidence,
but neither owns, aliases, or substitutes for the other. Scenario output is not
future observed evidence and cannot become a Shadow checkpoint. This ADR does
not implement Scenario Simulation.

## Consequences

- HYB can begin accumulating trustworthy elapsed-time baselines without funding
  every promising Opportunity.
- Exact O2 binding prevents silent subject drift between historical screening
  and future observations.
- Persisted screening remains the historical decision authority; Shadow does
  not depend on the live engine or current policy.
- Real commerce evidence, money, and Actual Outcome remain uncontaminated by
  unfunded hypotheses.
- Upstream evidence stays owned by its existing Domain, avoiding copied raw
  payloads and a new Shadow data silo.
- Manual operation allows early baseline collection before scheduler or alert
  infrastructure is justified.
- The narrow machine-based MVP defers Founder-only theses and therefore does not
  cover every potentially interesting historical Opportunity.
- Exact lineage, time, and comparability requirements may produce
  `INCONCLUSIVE` or ineligible results; that is preferable to false calibration.

## Alternatives Considered

### New bounded Shadow domain

Rejected. Shadow composes existing Opportunity meaning and existing evidence
authorities. A new bounded domain would duplicate thesis and evidence semantics.

### WatchList-owned Shadow mode

Rejected. WatchList's mutable price-monitoring meaning cannot authoritatively
represent an immutable thesis, baseline, checkpoint, or verdict.

### Candidate-only registration

Rejected for the authoritative MVP. It cannot prove that baseline and future
observations concern the exact same KR commercial subject.

### Support machine-based and Founder-declared registration together

Deferred. Mixing them in v1 risks presenting a Founder thesis as validation of
machine rank. The exact machine-based path is the smallest trustworthy start.

### Reconstruct the baseline from current or latest facts

Rejected. It introduces hindsight, current-policy drift, mutable-source drift,
and unverifiable historical claims.

### Model Shadow as Actual Outcome, virtual sales, or paper profit

Rejected. HYB did not execute the commerce required to observe those facts.

### Scheduler or generic workflow engine first

Rejected. Manual/on-demand checkpoints are sufficient to begin evidence
collection and avoid unproven infrastructure.

## MVP Implementation Sequence

1. **Shadow PR1 — this ADR:** authority, subject, baseline, time, and
   Real/Shadow decisions; no production code.
2. **Shadow PR2:** immutable Opportunity-owned
   `ShadowValidationRegistration` and `ShadowBaselineSnapshot` contracts.
3. **Shadow PR3:** append-only SQLite registration/baseline persistence,
   atomicity, integrity validation, idempotent replay, and corruption behavior.
4. **Shadow PR4:** manual Application/API registration against exact O2 and
   exact persisted ADR-0067 screening authority.
5. **Begin collecting Shadow baselines** as soon as PR4 is trustworthy.
6. **Shadow PR5:** manual checkpoint publication contracts and append-only
   persistence.
7. **Shadow PR6:** deterministic Opportunity-owned thesis evaluation.
8. **Shadow PR7:** Founder Shadow Portfolio/read surface with explicit evidence
   class and calibration-eligibility labels.

Scheduler and alerts are not prerequisites. Each implementation PR must keep
the existing authority boundaries, add focused tests, update current-state
documentation, and remain independently reviewable.

## MVP Non-goals

- fake or simulated sales;
- virtual revenue or profit;
- Monte Carlo simulation;
- automatic scheduling, alerts, cron, or workflow platform;
- generic workflow engine;
- automatic ML calibration, retraining, threshold adjustment, or score update;
- automatic Candidate, O1, or O2 creation;
- automatic purchasing or capital action;
- WatchList ownership;
- Shadow/Real evidence or denominator mixing;
- Candidate-only ambiguous target validation;
- Founder-declared registration in v1;
- historical hindsight registration presented as unbiased calibration;
- changes to Actual Outcome, Variance, Purchase Execution, settlement,
  inventory, or Scenario Simulation; and
- F1 durable Discovery recovery.

## Shadow PR2 Readiness

With this ADR's documentation validation green, Shadow PR2 readiness is
**YES**. PR2 must remain Domain-contract-only, require exact O2 and
`MACHINE_SCREENING_BASED` lineage, and must not pull persistence, API,
checkpoint execution, evaluation, WatchList, or scheduling into the same cut.

## Prior Architecture Design Alignment

This ADR records the approved prior Shadow Architecture Design without a
semantic deviation. It selects the recommended minimal option—exact O2 plus
`MACHINE_SCREENING_BASED` only—and makes explicit the baseline manifest,
time/calibration, Real/Shadow, WatchList, F1, Scenario, and staged-PR boundaries
required before implementation.
