# HYB Opportunity AI Project Status

**Last Updated:** 2026-08-29
**Status Basis:** Baseline Regression Reliability Repair

## Current Snapshot

- Current work: Shadow PR4 authoritative exact-O2 + persisted-screening manual
  registration Application, POST, persistence-only exact GET, and request-first
  replay complete
- Last confirmed full regression: **3983 passed, 1 warning**
  (Baseline Regression Reliability Repair, 2026-08-29)
- The regression gate is clean on supported Python 3.12 after repairing slotted
  dataclass serialization compatibility and two pre-existing test-isolation
  defects; no business or authority semantics changed.
- Architecture approach: preserve existing Domain/Application/Infrastructure
  boundaries and additive authority contracts
- Shadow PR4 adds no UI, checkpoint, scheduler, evaluator, Portfolio,
  calibration statistics, automatic registration, or ranking-policy change

ADR-0067 accepts an existing-Discovery-owned persisted screening design:
immutable per-Group evaluation snapshots, a separate immutable ranking
publication, and `DiscoveryExecutionResult v2` referencing only the publication
ID. PR2 provides its explicit result-to-finalized-Group correlation
prerequisite. PR3 versions the current score, recommendation, production-safety,
and three-key stable ranking semantics and exposes structured reasons plus
raw/effective recommendation values. PR4 now defines immutable per-Group
evaluation snapshots, separate execution-level ranking publications, explicit
not-ranked entries, Discovery-only provenance and exact-used-input manifests,
canonical serialization, and integrity fingerprints. PR5 adds append-only
evaluation/publication histories and a separate immutable completion binding,
committed with the existing result row through one SQLite transaction. PR6 now
constructs the exact production evidence and publication, commits the full
completion bundle atomically, and reconstructs it on completed replay without
live runtime or current-policy recalculation. Existing unbound v1 results
remain legacy and are not backfilled. PR7 exposes the exact persisted
ranking/evaluations to Founder review without changing downstream authority.

ADR-0068 accepts the Shadow Opportunity Validation architecture. Shadow PR2
implements immutable Opportunity-owned registration, exact O2/screening
lineage, baseline source-manifest, time/completeness/eligibility,
evidence-class, canonical serialization, and fingerprint contracts. Shadow PR3
now commits Registration + Baseline + receipt atomically in append-only SQLite,
strictly reconstructs exact history, and fails closed on conflicts/corruption.
Shadow PR4 now resolves the exact persisted Screening -> finalized Group ->
Candidate -> O1 -> exact O2 chain, admits only the selected historical Screening
manifest plus explicit O2 subject identity, derives a source-availability
cutoff, and persists an eligible baseline through PR3. Request-level receipts
make retry source/ID/clock-free, and exact GET is persistence-only. Shadow
remains market-thesis evidence only and cannot create or stand in for Real
Commerce, Actual Outcome, revenue, profit, investment, buying, or Capital
authority.

## Production Discovery

The authoritative FastAPI composition in `app.web` currently executes:

```text
DiscoveryCommand + receipt
  -> live collection
  -> CollectedProductObservation persistence
  -> FinalizedProductGroup persistence at the grouping checkpoint
  -> ordered finalized Group IDs returned to the engine before analysis
  -> transient economics / ranking / recommendation
  -> sorted DiscoveryResult values retaining exact finalized Group IDs
  -> exact-used per-Group screening evaluations
  -> ranking publication from actual sorted output
  -> atomic evaluations/publication/result/completion-binding persistence
```

The command, observation, finalized Group, and execution-result boundaries use
the configured file-backed SQLite database. A successful zero-result is an
explicit persisted completion, not an inference from missing Group rows.

The persisted `DiscoveryExecutionResult` contains ordered finalized Group IDs,
completion time, schema, and fingerprint. It does **not** pretend to preserve a
runtime `OpportunityResult` or transient `DiscoveryResult`. Separate immutable
screening evaluations, ranking publication, and binding preserve the historical
screening snapshot. The existing POST and result/group GET APIs remain
backward-compatible; the separate exact screening-ranking GET exposes the
Founder view.

Candidate issuance is a separate, explicit durable API after Discovery
completion and Founder selection. Discovery does not automatically issue a
Candidate or create an Opportunity. Founder Home may explicitly select any
eligible ranked or not-ranked Group through the existing Candidate API.

Completed screening-capable replay is restart-safe and loads the exact stored
policy, reasons, provenance, evaluations, publication, result, and binding
without the runtime, collectors, current policy, identity generation, or clock.
Legacy unbound completed results remain readable with explicit
`SCREENING_NOT_RECORDED_LEGACY` and no backfill.
Incomplete execution is different: committed checkpoints can survive a later
failure, but there is no durable phase, attempt, failure, retry, or resume state
machine. Repeating an incomplete command reruns the current entry; that is not a
persisted resumable-workflow guarantee.

## Competition, Demand, and DMV v2

- Competition v2 is implemented at Domain, Application, SQLite, API v2, and
  OpenAPI boundaries. The current genuine Competition publication is persisted.
- Demand v2 is implemented at Domain, Application, SQLite, API v2, and OpenAPI
  boundaries. No provider network integration is implied.
- DMV v2 source-manifest preview and final validation POST are implemented and
  persisted. Target-aware Founder Sourcing, Verified Economics ingress, and
  DMV v2 consumption by Capital Readiness are also implemented.
- The target-bound software path reaches Capital Gate, but the current genuine
  run has not admitted Demand v2 or executed DMV v2/Capital Readiness/Capital
  Gate for that lineage.

## Genuine-Run Geography Status

The official NAVER advertising customer-center clarification received for the
current evidence is: `해외검색수 포함` (overseas searches included).

Therefore NAVER/ItemScout total search volume may include searches made outside
South Korea and is not Korea-only domestic-demand evidence. It must not be
submitted or described as an explicit KR-only query/search count.

This clarification does not clear the current STOP. Demand v2's accepted
evidence contract requires a truthfully scoped provider query/search count for
Korean market intent. The genuine run must remain stopped until either:

1. an authoritative provider field with Korea-only scope and complete provenance
   is obtained; or
2. a separately reviewed business/domain contract change explicitly admits and
   qualifies mixed-geography evidence.

No such contract change is part of this PR.

## Decision and Spending Authority

The existing Decision Dashboard outcome `INVEST` is a legacy screening decision
under the Decision Engine policy. It is not Capital Gate `PASS`, Founder Capital
Approval, a Real-Money Execution Intent, or permission to spend. Real-money
execution remains gated by the separate capital and Founder-authority chain.

## Current Known Gaps

- durable Discovery attempt/failure/resume state;
- automated provider collection for Competition/Demand v2;
- evidence-qualified Korea-only Market Intent for the current genuine run;
- Decision Composition v2 or any change that reconciles legacy screening
  outcomes with capital authorities.

These are follow-up scopes. F1 durable attempt/recovery remains a separate
track; PR6 completion atomicity does not make incomplete execution resumable.

## ADR-0067 PR7 Status

- `PersistedDiscoveryScreeningReader` is the single read capability behind the
  exact screening-ranking API and Founder review surface.
- The read follows completion binding -> ranking publication -> evaluation
  snapshots and preserves persisted rank/not-ranked order, policies, reasons,
  economics, provenance, timestamps, and fingerprints without recomputation.
- Founder terminology is High/Medium/Low Review Priority. Raw/effective
  BUY-family values remain explicitly labelled screening-engine audit detail.
- Legacy completions return `SCREENING_NOT_RECORDED_LEGACY`; missing execution
  returns 404 and corrupt/unsupported screening history returns 409 without
  live fallback.
- Founder Home restores completed reviews with GETs only and uses the existing
  Candidate API for an explicit selected-Group handoff. No Candidate is issued
  by a read and no O1/O2 or Capital state is automatic.
- ADR-0067 / Deep Audit F2 is **CLOSED**. F1 Recovery, Shadow production
  implementation, Scenario Simulation, automatic Candidate issuance, and
  autonomous purchase remain deferred.

## Shadow MVP Readiness Review

`SHADOW_PR4 = COMPLETE`. The immutable contracts require exact ADR-0060 O2,
Candidate/O1/finalized-Group lineage, and exact persisted ADR-0067 evaluation,
publication, used-input, timestamps, and fingerprints. Baseline sources are
explicitly selected, cutoff-safe, availability-aware, and structurally separate
from Actual Outcome and Real Commerce. PR3 preserves that exact bundle in one
append-only `BEGIN IMMEDIATE` transaction with strict reads, exact receipt
replay, rollback, restart, and same-database concurrency behavior.

Manual baseline collection is **READY**. HYB can now durably start Shadow
elapsed-time baselines for eligible exact-O2 Opportunities through an explicit
Founder POST and verify them by exact ID without live reconstruction. No
checkpoint, evaluator, Portfolio UI, scheduler, automatic calibration, or
automatic registration exists yet. Real/Shadow evidence remains strictly
separate. The next cut is Shadow PR5 manual checkpoint publication;
WatchList, F1 Recovery, and Scenario remain separate.

## Shadow PR4 Verification

- New authoritative registration Application/API tests: **8 passed, 1 warning**
- Focused Shadow + persisted Screening + Candidate/O1/O2 impact: **269 passed,
  1 warning**
- API/OpenAPI + DMV impact: **99 passed, 1 warning**
- Full regression: **3982 passed, 1 warning**
- No ADR deviation; Shadow PR5 readiness: **YES** after PR4 merge.

## Shadow PR3 Verification

- Focused Shadow PR2+PR3: **49 passed**
- Persisted screening compatibility: **113 passed, 1 warning**
- Candidate/O1 compatibility: **51 passed, 1 warning**
- Candidate promotion/O2 admission: **44 passed, 1 warning**
- O2 SQLite and Domain foundation: **16 passed** and **13 passed, 1 warning**
- Broader Opportunity/Discovery/Candidate/O2/Shadow impact: **1026 passed,
  2948 deselected, 1 warning**
- Full regression: **3974 passed, 1 warning**
- No ADR deviation; Shadow PR4 readiness: **YES**

## Shadow PR2 Verification

- New immutable Shadow Domain contract tests: **17 passed**
- Screening/Candidate Promotion/O2 focused compatibility: **85 passed, 1 warning**
- Screening PR2-PR7, Candidate/O1/O2, Opportunity, and Real/Shadow impact:
  **412 passed, 1 warning**
- Full regression: **3942 passed, 1 warning**
- No ADR deviation; Shadow PR3 readiness: **YES**

## ADR-0068 PR1 Verification

- Changed Markdown strict UTF-8 validation: passed (7 files)
- Changed Markdown relative-link validation: passed
- ADR required-section/decision-term contract check: passed (18 terms)
- Documentation knowledge/developer tests: **24 passed**
- `git diff --check`: passed
- Full regression was not rerun under the document-only PR rule; the last
  confirmed baseline remains **3925 passed, 1 warning**

## ADR-0067 PR7 Verification

- New/changed Application, API, Founder UI, and Candidate handoff focused run:
  **60 passed, 1 warning**
- PR2-PR7 screening coverage: **113 passed, 1 warning**
- Candidate, Founder Home, Discovery API/replay, OpenAPI, and web impact:
  **135 passed, 1 warning**
- Broader Discovery/Engine impact: **558 passed, 1 warning**
- Documentation knowledge/developer tests: **24 passed**
- Full regression: **3925 passed, 1 warning**

## ADR-0067 PR6 Status

- The authoritative production entry constructs PR4 evaluations by exact
  `finalized_group_id` and constructs the publication from actual sorted output
  without adding a tie-break key.
- The PR5 composite repository is the only successful completion write boundary
  for the production composition.
- Completed screening replay restores exact historical screening without live
  runtime or recalculation; legacy unbound results remain explicit legacy.
- Used-input provenance preserves actual limitations, including unknown source
  shipping plus a separate zero-fallback assumption and unsupported exact
  currency-rate lineage where the runtime does not expose that fact.
- PR7 API/UI is implemented. F1 recovery, Shadow Validation, and Scenario
  Simulation remain unimplemented.

## ADR-0067 PR6 Verification

- PR6 plus PR2/PR3/PR4/PR5 screening contract and persistence tests:
  **100 passed**
- Production execution/replay and Discovery API impact tests:
  **75 passed, 1 warning**
- Candidate issuance regression: **51 passed, 1 warning**
- Broader Discovery/Engine impact run: **370 passed, 3538 deselected,
  1 warning**
- Documentation knowledge/developer tests: **28 passed**
- Changed Markdown strict UTF-8 and relative-link validation: passed (5 files)
- Full regression: **3908 passed, 1 warning**

## ADR-0067 PR5 Status

- A Discovery-specific composite repository owns one connection and transaction
  for evaluations, ranking publication, execution result, and completion
  binding.
- PR4 canonical payloads and fingerprints are stored without float conversion;
  reads reconstruct and revalidate policy, reason, provenance, Decimal,
  datetime, ordering, Group, and publication lineage.
- Exact retry, rollback/fault injection, corruption, restart, legacy
  coexistence, and same-database concurrency are covered at the persistence
  boundary.
- PR6 subsequently wires Production Discovery and `app.web` to this repository.

## ADR-0067 PR5 Verification

- New SQLite completion persistence tests: **31 passed**
- PR2/PR3/PR4 plus Discovery persistence/completion/replay focused run:
  **150 passed**
- Broader Discovery and Candidate issuance/promotion impact run:
  **377 passed, 1 warning**
- Documentation knowledge/developer tests: **24 passed**
- Full regression: **3898 passed, 1 warning**

## ADR-0067 PR4 Verification

- New immutable screening Domain contract tests: **36 passed**
- PR2/PR3 and adjacent Discovery Domain tests: **51 passed**
- Discovery/orchestrator/recommendation/Safety/score impact tests:
  **334 passed, 1 warning**
- Combined focused, adjacent, and documentation knowledge/developer tests:
  **111 passed**
- Full regression: **3867 passed, 1 warning**

## ADR-0067 PR3 Verification

- New policy/reason semantic contract tests: **11 passed**
- Focused scoring, recommendation, Safety, ranking, correlation, and
  orchestrator tests: **73 passed**
- Discovery/presentation/history/web compatibility impact tests:
  **185 passed, 1 warning**
- Documentation knowledge/developer tests: **24 passed**
- Changed Markdown strict UTF-8 validation: passed (5 files; no relative links)
- Full regression: **3831 passed, 1 warning**

## ADR-0067 PR2 Verification

- Correlation plus adjacent Discovery runtime/grouping/collection tests:
  **109 passed**
- Completion replay, result persistence, Discovery API, and Candidate issuance
  impact tests: **119 passed, 1 warning**
- Documentation knowledge/developer tests: **28 passed**
- Changed Markdown strict UTF-8 and relative-link validation: passed (5 files)
- Full regression: **3820 passed, 1 warning**

## ADR-0067 Verification

- Changed Markdown strict UTF-8 and relative-link validation: passed (6 files)
- ADR required-section/rejected-alternative contract check: passed (28 checks)
- Documentation knowledge/developer tests: **24 passed**
- Full regression: not rerun under the Documentation Policy's document-only PR
  rule; the last confirmed baseline remains **3806 passed, 1 warning**

## PR1 Verification

- Changed-document UTF-8 and relative-link validation: passed
- Focused runbook/OpenAPI and Decision Dashboard tests: **12 passed, 1 warning**
- Discovery/Competition/Demand/DMV/Capital impact tests:
  **284 passed, 1 warning**
- Full regression: **3806 passed, 1 warning**

The warning is the known FastAPI/Starlette TestClient `httpx` deprecation
warning; it is not suppressed by this PR.
