# HYB Documentation Status

**Last Updated:** 2026-08-27
**Status Basis:** ADR-0067 PR4 Screening Domain Contracts

## Purpose

이 문서는 HYB 문서 체계의 현재 신뢰도와 최신화 상태를 빠르게 확인하기 위한
current-state index입니다. Historical Sprint/PR/ADR 기록의 당시 상태와 테스트 수는
현재 값으로 덮어쓰지 않습니다.

## Current Documentation Baseline

- Official documentation root: `docs/`
- Encoding: UTF-8
- Architecture policy: 기존 계층과 additive authority 경계 유지
- Last confirmed full regression: **3867 passed, 1 warning**
  (ADR-0067 PR4, 2026-08-27)
- Production Discovery: command/receipt, observations, finalized Groups, and
  execution result are wired to SQLite through `app.web`
- Persisted Discovery Screening F2: ADR-0067 accepted; PR2 explicit
  finalized-Group correlation, PR3 policy/reason semantics, and PR4 immutable
  evaluation/ranking/provenance Domain contracts implemented; PR5 through PR7
  pending
- Competition v2, Demand v2, and Domestic Market Validation (DMV) v2: implemented
- Genuine-run status: STOP before Demand v2 admission; see the runbook for the
  NAVER geography evidence ruling

## Current-State Documents

| Document | Path | Status | Update Trigger |
|---|---|---|---|
| Project Status | `docs/01_CONTEXT/PROJECT_STATUS.md` | Current | production wiring, limitation, or regression baseline changes |
| System Architecture | `docs/02_ARCHITECTURE/01_SYSTEM_ARCHITECTURE.md` | Current | authoritative composition or authority path changes |
| Database Schema | `docs/02_ARCHITECTURE/04_DATABASE_SCHEMA.md` | Current with historical increment notes | durable schema or production wiring changes |
| API Specification | `docs/02_ARCHITECTURE/05_API_SPEC.md` | Current | production route or API meaning changes |
| Discovery Workflow | `docs/02_ARCHITECTURE/OPPORTUNITY_DISCOVERY_WORKFLOW.md` | Current | Discovery completion/replay/recovery contract changes |
| First Real-World Validation Runbook | `docs/05_OPERATIONS/FIRST_REAL_WORLD_VALIDATION_RUNBOOK.md` | Current operational contract | genuine authority/evidence status or production route changes |
| Deployment Guide | `docs/05_OPERATIONS/DEPLOYMENT.md` | Current minimum deployment contract | composition, validation, or rollback requirements change |
| Document Status | `docs/DOCUMENT_STATUS.md` | Current | documentation audit result changes |

## Historical and Stable Documents

- `docs/00_FOUNDATION/` contains stable project principles.
- `docs/04_DEVELOPMENT/sprints/` and accepted ADR decision bodies preserve the
  state at the time of each decision.
- When later implementation supersedes an ADR's original future/deferred status,
  add an `Implementation Status` annotation rather than rewriting the historical
  decision body.

## Current Documentation Debt

- `DiscoveryExecutionResult` v1 persists ordered finalized Group IDs, not the
  full ranked `OpportunityResult`/`DiscoveryResult` payload. ADR-0067 now
  defines separate evaluation/ranking history and a publication-ID-only v2
  completion reference. PR4 Domain contracts now exist, but PR5 persistence,
  result v2 completion, replay, API, and UI remain unimplemented.
- Fresh production results now preserve the exact `finalized_group_id` assigned
  before analysis through sorting and runtime mapping. The value remains
  transient until later screening persistence work; title, URL, item inference,
  and post-sort positional assumptions remain forbidden.
- Fresh production results also expose immutable v1 score, recommendation,
  production-safety, and three-key stable ranking descriptors plus structured
  v1 reasons and explicit raw/effective recommendation semantics. These remain
  transient contracts; no screening snapshot or ranking publication is yet
  persisted.
- Immutable PR4 evaluation and ranking publication contracts now compose those
  PR3 values with Discovery-only provenance, exact-used input manifests,
  canonical serialization, Group-membership and integrity fingerprints, and
  explicit not-ranked semantics. Production does not yet construct them.
- Completed Discovery replay is durable and runtime-free, but incomplete
  executions have no persisted phase/attempt/failure/resume workflow contract.
- NAVER total search volume may include overseas searches. It is not Korea-only
  demand evidence and cannot be labeled as such in a genuine Demand v2 artifact.
- Older architecture/alignment and Sprint reports remain historical snapshots;
  they must not be used as the current production wiring source without the
  current-state documents above.

## Validation Policy

When a document records tests, distinguish:

- the tests actually executed for that change;
- an explicitly named earlier regression baseline; and
- historical counts recorded by earlier Sprint/PR documents.

Never report an unexecuted regression as passed.
