# HYB Opportunity AI Project Status

**Last Updated:** 2026-07-30
**Status Basis:** Sprint 9 PR2 구현, 기능 테스트 및 전체 회귀 테스트

## Current Stage

HYB Opportunity AI는 기존 CLI와 Orchestrator를 유지하면서 신규
**Opportunity Intelligence 결과를 실제 CLI 실행 경로에 추가 출력**하도록
Sprint 9 PR2 수직 통합을 완료했습니다.

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

Sprint 8에서는 WatchList가 등록된 상품을 Marketplace에서 정확히 다시 조회하고,
변경 감지 흐름으로 전달하기 위한 Application과 Infrastructure 경계를 구축했습니다.
해당 Sprint에서 남은 통합 항목은 아래 WatchList Monitoring 이력에 별도로 기록합니다.

---

## Current Snapshot

- Current Sprint: **Sprint 9**
- Current Position: **PR2 구현 및 검증 완료**
- Current Focus: **Opportunity Intelligence CLI Integration**
- Last Confirmed Full Regression Test: **1119 passed**
- Regression Verified At: **2026-07-30**
- Architecture Baseline: **Sprint 4.4 Architecture Freeze 유지**

### Recently Completed

- Sprint 9 PR2 기존 CLI Opportunity Intelligence 추가 출력
- 기존 OpportunityResult → DiscoveryResult 변환 재사용
- 신규 Score, Decision, Confidence, Risk CLI 표시
- 기존 CLI, Orchestrator, Dashboard, Recommendation 호환 유지
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

### Sprint 9 PR2 Limitations

- 기본 CLI는 Price History Repository를 신규 Opportunity Intelligence
  Adapter에 주입하지 않는다.
- 따라서 Trend Assessment와 신규 Final Recommendation은 실제 입력이
  제공되는 경로에서만 생성되며, 기본 CLI에서는 Score, Decision,
  Decision Report, Confidence, Risk 결과를 표시한다.
- 기존 `ai_recommendation`은 제거하거나 대체하지 않는다.

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

Sprint 8에서 남은 후속 항목:

- Concrete Marketplace Reader integration
- Dispatcher registration and composition
- WatchList end-to-end monitoring flow
- Change detection connection

---

## Sprint 8 WatchList Architecture Direction

다음 구조는 Sprint 8에서 확립한 WatchList 방향이며,
Sprint 9 PR2의 현재 CLI Opportunity Intelligence 통합과 구분되는 과거 설계 기준입니다.

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

## Remaining Backlog from Sprint 8

1. Sprint 8 PR3-B3 Marketplace Reader Integration
2. WatchList Monitor end-to-end 연결
3. Marketplace lookup 결과와 Change Detection 연결

위 항목은 Sprint 9 PR2의 현재 완료 상태가 아니라,
Sprint 8 WatchList 작업에서 이월된 후속 과제입니다.

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
