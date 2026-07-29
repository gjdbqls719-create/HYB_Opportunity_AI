# HYB Opportunity AI Project Context

**Last Updated:** 2026-07-29  
**Primary Audience:** 새 채팅의 AI Partner, 개발자, 리뷰어

## Quick Context

- Project: **HYB Opportunity AI**
- Current Sprint: **Sprint 8**
- Current Position: **PR3-B2 완료 / PR3-B3 준비**
- Current Focus: **Marketplace Reader Integration**
- Branch: `main`
- Latest Commit: `3806736 feat: add marketplace item lookup APIs`
- Latest Full Regression: **1053 passed**
- Architecture Baseline: **Sprint 4.4 Architecture Freeze**

## Product Purpose

온라인 판매자가 상품을 구매하거나 투자하기 전에
가격, 시장, 수익성, 위험, 변화 이력을 바탕으로
“이 상품에 투자할 가치가 있는가?”를 판단하도록 지원합니다.

HYB는 단순 검색 또는 가격 비교 도구가 아니라,
상품 기회를 발견하고 평가하며 지속적으로 감시하는
설명 가능한 Opportunity Intelligence Platform입니다.

## Current System Flow

```text
Marketplace Collectors
→ Normalized Product
→ Product Matching / Canonical Identity
→ Opportunity Discovery
→ Opportunity Intelligence
→ Explainable Decision
→ AI Partner
→ Dashboard / CLI
→ WatchList
→ Exact Marketplace Listing Lookup
→ Change Detection
```

## Current Sprint 8 Scope

### Completed

- WatchList domain
- SQLite WatchList repository
- Monitor foundation
- Listing lookup application port
- Marketplace listing dispatcher
- eBay exact item lookup API
- Amazon deterministic exact item lookup contract

### Next PR

**Sprint 8 PR3-B3 — Marketplace Reader Integration**

Expected direction:

```text
MarketplaceListingLookupAdapter
        ↓
EbayListingReader / AmazonListingReader
        ↓
marketplaces.ebay.get_product_by_id()
marketplaces.amazon.get_product_by_id()
```

Do not bypass exact lookup with `search_items(...)[0]`.
Search and single-item lookup must remain separate responsibilities.

## Architecture Rules

- User is Product Owner and final decision-maker.
- Prefer correctness, stability, maintainability, extensibility, readability, performance, then speed.
- Review architecture before implementation.
- Preserve the Sprint 4.4 architecture baseline unless strong evidence and an ADR justify change.
- Domain and application layers must not depend on Marketplace HTTP details.
- Marketplace-specific fetching belongs in infrastructure / marketplace modules.
- Canonical identity distinguishes Strong Identity from Weak Identity.
- Price history remains append-only.
- Do not invent unavailable data or silently substitute defaults.
- Do not redesign stable architecture merely to simplify one PR.

## Development Workflow

1. Inspect actual repository state.
2. Review design and boundaries.
3. Implement in a small PR-sized increment.
4. Run feature-specific tests.
5. Run full regression.
6. Update code, tests, ADRs, architecture, changelog, release notes, AI development log, and `DEVELOPMENT_PRINCIPLES.md` when major work changes engineering practice.
7. Commit and push.
8. Produce one changed-files ZIP per PR.
9. Produce Quick Context and Full Context ZIPs.
10. State the exact next development step.

## Standard Deliverable

Each PR should include:

- Implementation summary
- Added / modified / deleted paths
- Feature test command and result
- Full regression command and result
- Git commands
- Changed-files ZIP
- Quick Context ZIP script
- Full Context ZIP script
- Next-step recommendation

## Important Continuity Rule

Before implementing in a new chat:

1. Read this document.
2. Read `PROJECT_STATUS.md`.
3. Inspect relevant source and tests from the uploaded Context ZIP.
4. Confirm repository and Git metadata.
5. Report the understood current state.
6. Only then begin implementation.
