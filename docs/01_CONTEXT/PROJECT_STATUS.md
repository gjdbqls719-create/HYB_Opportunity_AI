# HYB Opportunity AI Project Status

**Last Updated:** 2026-08-27
**Status Basis:** ADR-0067 PR4 Screening Domain Contracts

## Current Snapshot

- Current work: Persisted Discovery Screening F2 PR2 correlation, PR3
  policy/reason semantics, and PR4 immutable evaluation/ranking/provenance
  Domain contracts implemented; PR5 SQLite composite completion is next
- Last confirmed full regression: **3867 passed, 1 warning**
  (ADR-0067 PR4, 2026-08-27)
- Architecture approach: preserve existing Domain/Application/Infrastructure
  boundaries and additive authority contracts
- This PR adds no new business authority and changes no production ranking
  formula or stable-tie behavior

ADR-0067 accepts an existing-Discovery-owned persisted screening design:
immutable per-Group evaluation snapshots, a separate immutable ranking
publication, and `DiscoveryExecutionResult v2` referencing only the publication
ID. PR2 provides its explicit result-to-finalized-Group correlation
prerequisite. PR3 versions the current score, recommendation, production-safety,
and three-key stable ranking semantics and exposes structured reasons plus
raw/effective recommendation values. PR4 now defines immutable per-Group
evaluation snapshots, separate execution-level ranking publications, explicit
not-ranked entries, Discovery-only provenance and exact-used-input manifests,
canonical serialization, and integrity fingerprints. Production construction,
persistence, completion schema v2, replay v2, API, and UI remain deferred.

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
  -> DiscoveryExecutionResult persistence
```

The command, observation, finalized Group, and execution-result boundaries use
the configured file-backed SQLite database. A successful zero-result is an
explicit persisted completion, not an inference from missing Group rows.

The persisted `DiscoveryExecutionResult` contains ordered finalized Group IDs,
completion time, schema, and fingerprint. It does **not** preserve the complete
ranked `OpportunityResult` or transient `DiscoveryResult` payload. The POST
response and result/group GET APIs therefore expose authoritative completion and
lineage, not a durable ranking snapshot.

Candidate issuance is a separate, explicit durable API after Discovery
completion and Founder selection. Discovery does not automatically issue a
Candidate or create an Opportunity.

Completed exact replay is restart-safe and does not call the live runtime.
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
- construction and SQLite composite persistence of Discovery screening
  evaluations and ranking publications (ADR-0067 PR5);
- automated provider collection for Competition/Demand v2;
- evidence-qualified Korea-only Market Intent for the current genuine run;
- Decision Composition v2 or any change that reconciles legacy screening
  outcomes with capital authorities.

These are follow-up scopes. PR2 correlation and PR3 semantic contracts do not
persist screening. F1 durable attempt/recovery remains a separate track.

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
