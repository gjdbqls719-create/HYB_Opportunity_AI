# HYB Opportunity AI Project Status

**Last Updated:** 2026-07-29  
**Status Basis:** Sprint 8 PR3-B2 완료 저장소 스냅샷, Git 기록, 전체 회귀 테스트 재실행

## Current Stage

HYB Opportunity AI는 Foundation, Opportunity Intelligence, Explainable Decision Pipeline,
Presentation 기반 구축을 완료했으며 현재 **WatchList Monitoring System**을 확장하고 있습니다.

현재 핵심 흐름은 다음과 같습니다.

```text
Marketplace Data
→ Product Normalization
→ Opportunity Discovery
→ Opportunity Intelligence
→ Explainable Decision
→ AI Partner
→ Dashboard / CLI
→ WatchList
→ Marketplace Listing Lookup
→ Change Detection
```

현재 Sprint 8에서는 WatchList가 등록된 상품을 Marketplace에서 정확히 다시 조회하고,
변경 감지 흐름으로 전달할 수 있도록 Application과 Infrastructure 경계를 연결하고 있습니다.

---

## Current Snapshot

- Current Sprint: **Sprint 8**
- Current Position: **PR3-B2 완료 / PR3-B3 준비**
- Current Focus: **Marketplace Reader Integration**
- Latest Commit: `3806736 feat: add marketplace item lookup APIs`
- Branch: `main`
- Last Confirmed Full Regression Test: **1053 passed**
- Regression Verified At: **2026-07-29**
- Architecture Baseline: **Sprint 4.4 Architecture Freeze 유지**

### Recently Completed

- Sprint 7 Documentation Quality Audit
- Sprint 7 Marketplace Adapter Integration
- Sprint 7 Marketplace Contract Tests
- Sprint 7 Presentation Refactoring
- Sprint 7 Opportunity List ViewModel 및 CLI
- Sprint 8 WatchList Domain
- Sprint 8 SQLite WatchList Repository
- Sprint 8 Monitor Foundation
- Sprint 8 PR3-B1 Marketplace Listing Lookup Dispatcher
- Sprint 8 PR3-B2 Marketplace Item Lookup APIs

---

## Current Core Systems

### Opportunity Intelligence

- Product normalization
- Canonical product identity
- Product matching
- Price intelligence
- Price trend analysis
- Inventory analysis
- Seller analysis
- Market intelligence
- Market adjustment
- Opportunity scoring
- ROI intelligence

### Explainable Decision

- Recommendation
- Decision report
- AI Partner explanation
- Dashboard decision timeline
- Opportunity list presentation

### WatchList Monitoring

Completed:

- WatchList domain model
- WatchList application ports
- SQLite repository and mapper
- Monitor request/result models
- WatchList monitor use case foundation
- Marketplace listing lookup dispatcher
- eBay item lookup API
- Amazon deterministic item lookup contract

Next:

- Concrete Marketplace Reader integration
- Dispatcher registration and composition
- WatchList end-to-end monitoring flow
- Change detection connection

---

## Current Architecture Direction

```text
WatchListMonitorUseCase
        ↓
ListingLookupPort
        ↓
MarketplaceListingLookupAdapter
        ↓
Marketplace Reader
        ↓
eBay / Amazon get_product_by_id()
        ↓
Product
        ↓
Change Detection
```

Search와 exact item lookup은 서로 다른 책임으로 유지합니다.
검색 결과 첫 항목을 감시 대상 상품으로 추정하지 않으며,
Marketplace의 정확한 item ID를 사용해 조회합니다.

---

## Current Limitations

### Marketplace

- Amazon Production API 미연결
- eBay Live 환경 검증 미완료
- Walmart, Coupang, AliExpress, Temu 미연결

### Business Intelligence

- Landed cost
- Tax / duty
- Return risk
- Sales velocity
- Competition and demand signals
- 운영 데이터 기반 수익성 검증

### Operations

- Authentication
- Deployment
- Monitoring
- Alerting / notification

---

## Current Priorities

1. Sprint 8 PR3-B3 Marketplace Reader Integration
2. WatchList Monitor end-to-end 연결
3. Marketplace lookup 결과와 Change Detection 연결
4. 기능별 테스트 후 전체 회귀 테스트 유지
5. Sprint 상태·로드맵·개발 기록의 지속적 최신화

---

## Definition of Done

모든 주요 PR은 다음 순서를 따릅니다.

1. Architecture / design review
2. Small PR-sized implementation
3. Feature-specific tests
4. Full regression test
5. Documentation update
6. Git commit and push
7. Changed-files ZIP
8. Quick Context and Full Context ZIP
9. Next-step guidance

---

## Long-term Goal

HYB Opportunity AI는 온라인 판매자가
“이 상품에 내 돈을 투자해도 되는가?”를 데이터와 설명 가능한 근거로 판단하도록 돕는
AI Opportunity Intelligence Platform을 목표로 합니다.

장기적으로는 Opportunity Discovery, Investment Decision,
Continuous Monitoring, Automatic Opportunity Detection을 하나의 안정적인 흐름으로 연결합니다.
