# HYB Opportunity AI — Project Audit Report

- Audit date: 2026-07-24
- Source: `HYB_Opportunity_AI_AUDIT_v1(5).zip`
- Companion context: `HYB_STARTER_PACK_v1.0(1).zip`
- Source of truth: extracted code, automated tests, Git metadata, SQLite schema

## Executive Summary

현재 프로젝트는 단순 초기 프로토타입보다 훨씬 앞선 상태다. 공통 Product 모델, eBay/Amazon adapter, 상품 매칭, 가격 분석, Opportunity 계산, confidence/trend/recommendation/decision report/AI partner/AI memory, SQLite history, CLI와 presentation 계층까지 구현되어 있다.

Audit 시작 시 전체 자동 테스트 120개가 통과했다. Sprint 3 Opportunity Engine 1차 확장 후에는 123개가 통과한다.

다만 Production 준비 상태는 아니다. 가장 큰 위험은 코드 기능보다 저장소 기준선과 비밀정보 관리다. 전달된 ZIP에 `.env`, `.venv`, `.git`, SQLite DB, cache가 포함되어 있었고, Git 작업트리는 대규모 수정·삭제·미추적 상태였다.

## Verified Status

| Area | Verified status | Evidence |
|---|---|---|
| Python package structure | Working | 72 Python source/test files, compileall success |
| Automated tests | Working | 120/120 before Sprint 3, 123/123 after Sprint 3 |
| Product model | Implemented | unified `app.models.Product` with compatibility aliases |
| Marketplace layer | Implemented prototype | eBay adapter/auth, Amazon adapter/stub behavior |
| Product matching | Implemented | grouping and matching tests pass |
| Price intelligence | Implemented | Decimal-based analysis and tests pass |
| Opportunity Engine | Sprint 3 in progress | expanded cost model and profitability filters |
| Recommendation stack | Implemented prototype | confidence, trend, explainable score, recommendation, reports |
| Persistence | Implemented prototype | SQLite price/opportunity history repositories |
| Presentation/CLI | Implemented | dashboard formatter/builder/CLI tests pass |
| Production API usage | Not verified | audit did not call external production APIs |
| Automation/deployment | Not implemented as production system | no scheduler, worker, deployment pipeline verified |

## Entry Points

- Primary CLI entry: `main.py`
- Main application CLI: `app/cli.py`
- Diagnostic scripts: `check_ebay_token.py`, `check_ebay_search.py`, `check_orchestrator.py`, `check_price_history.py`, `check_price_trend.py`

The diagnostic scripts are useful during development but should not be treated as separate product entry points.

## Dependency Audit

`requirements.txt` currently contains:

- pytest
- requests
- python-dotenv

This is consistent with imports found in the current codebase. A lock file or reproducible environment file is still missing.

## Environment and Secret Audit

Required variables:

- `EBAY_ENV`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`

`.gitignore` correctly excludes `.env`, virtual environments, local DB files, caches, and generated exports. However, the delivered ZIP still contained `.env` and `.venv`. Even when ignored by Git, archive/export procedures must exclude them.

### Immediate security action

Because credentials were included in a shared archive, rotate the eBay client secret if the archive left the user's private machine or was shared beyond a trusted environment.

## Git Audit

The embedded repository reports a very large dirty working tree:

- many modified Python/test files
- many deleted legacy docs
- multiple new documentation directories and presentation files

A large portion of Python diffs appears consistent with line-ending normalization, but there are also real structural documentation changes. The current ZIP must not be blindly reset or rebased. First create a safety branch/commit from the user's real working repository, then compare against this audit deliverable.

Recommended safe sequence:

1. Back up the current real project folder.
2. Run `git status` in the real repository.
3. Commit intended work on a branch such as `feature/sprint-3-opportunity-engine`.
4. Never use `git reset --hard` until the intended changes are confirmed.

## Database Audit

SQLite database: `data/hyb_opportunity.db`

Tables:

- `price_history`
- `opportunity_history`

Both tables contain zero rows in the uploaded snapshot. The schema supports history and AI partner fields, but Sprint 3's new cost breakdown fields are not yet persisted. A later migration should add total cost, payment fee, tax, other cost, margin rate, landed-cost ROI, filter result, and warnings.

## Architecture Findings

### Strengths

- External marketplace code is separated from the analysis engine.
- A unified Product model is in use.
- Marketplace failure isolation exists in the orchestrator.
- Core calculations are covered by tests.
- Price intelligence uses Decimal.
- Recommendation output is increasingly explainable.

### Risks and inconsistencies

1. `engine/orchestrator.py` is becoming a large integration module and contains a malformed-looking docstring fragment. It runs, but should be cleaned in a focused refactor.
2. Opportunity calculation previously used float while price intelligence used Decimal. Sprint 3 now converts calculation inputs through Decimal, but public outputs remain floats for compatibility.
3. There are multiple layers of scoring: raw opportunity score, confidence-adjusted score, trend adjustment, final score, recommendation, decision report, AI partner report. The ownership and ordering need a single written contract.
4. Documentation was reorganized, but Git still reports many deleted legacy docs and new replacement folders. Links and canonical status documents must be stabilized before deleting history.
5. The archive includes development artifacts (`.git`, `.venv`, caches, DB, `.env`) that should not be in a normal handoff ZIP.
6. Sprint 3 cost fields are not yet exposed through CLI options or persisted to SQLite.

## Sprint 3 — Implemented in this Audit

Updated:

- `engine/opportunity.py`
- `engine/orchestrator.py`
- `tests/test_opportunity.py`

Added behavior:

- marketplace fee
- payment fee
- tax cost
- shipping cost
- other cost
- landed cost
- selling cost
- total cost
- net profit
- margin rate
- legacy ROI compatibility
- landed-cost ROI
- minimum net-profit filter
- minimum ROI filter
- decision reason
- risk warnings
- profitability pass/fail flags
- Decimal-based internal arithmetic and rounding

Backward compatibility:

- Existing function names and dict result style remain.
- Existing callers that only provide marketplace fee and shipping still work.
- Existing `roi` denominator remains purchase price to avoid breaking score/recommendation behavior.
- New `landed_cost_roi` provides a more conservative operational metric.

## Test Result

```text
123 passed
python -m compileall: success
```

## Sprint 3 Remaining Work

Priority order:

1. Add a dedicated typed Opportunity input/result model instead of an unstructured dict.
2. Define the authoritative ROI formula and migration plan for legacy consumers.
3. Add CLI arguments/config profiles for payment fee, tax, other costs, minimum net profit, and minimum ROI.
4. Persist Sprint 3 cost breakdown and warnings to opportunity history.
5. Add currency/exchange-rate structure; do not silently compare mixed currencies.
6. Add marketplace-specific fee policy objects rather than one generic rate.
7. Add return/refund reserve and duty/import-cost fields.
8. Clean orchestrator docstring/formatting and separate pipeline stages.
9. Add edge tests for zero purchase price, zero selling price, rounding boundaries, very high combined fees, and mixed Decimal/float/string input.
10. Update dashboard cards to show total cost, margin, landed-cost ROI, filter failure, and warnings.

## Audit Decision

The project is healthy enough to continue Sprint 3 without a full rewrite. The correct strategy is incremental stabilization around the existing tested architecture, not starting over.
