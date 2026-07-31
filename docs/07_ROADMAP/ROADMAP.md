# HYB Roadmap

**Last Updated:** 2026-07-29  
**Current Baseline:** Sprint 8 PR3-B2 completed, 1053 tests passed

## Roadmap Principle

HYB는 기능 수를 빠르게 늘리는 것보다
정확한 데이터, 안정적인 경계, 설명 가능한 판단,
실제 사업 가치 검증을 우선합니다.

우선순위는 다음과 같습니다.

```text
Correctness
→ Stability
→ Maintainability
→ Extensibility
→ Readability
→ Performance
→ Speed
```

## Completed Foundations

### Architecture and Domain Foundation

- Architecture baseline and domain separation
- Opportunity Discovery domain/application/workflow
- Canonical product identity
- Change domain foundation
- Append-only price history

### Opportunity Intelligence

- Price, trend, inventory, seller, market analysis
- Opportunity scoring and ROI intelligence
- Explainable recommendation and decision report
- AI Partner and dashboard integration

### Presentation and Marketplace Foundation

- Marketplace adapter contract
- eBay adapter integration
- Opportunity list ViewModel and CLI
- Presentation component refactoring

## Current Milestone — Sprint 8 WatchList Monitoring

### Completed

- WatchList domain
- SQLite repository
- Monitor foundation
- Listing lookup port and dispatcher
- Exact eBay item lookup API
- Deterministic Amazon item lookup contract

### Immediate Next

1. **PR3-B3 Marketplace Reader Integration**
2. Dispatcher composition and reader registration
3. WatchList Monitor end-to-end lookup flow
4. Lookup result to Change Detection connection
5. Monitoring result contract stabilization

## Near-Term Roadmap

### Sprint 8 Completion

- WatchList item registration and retrieval
- Exact Marketplace listing lookup
- Change Detection integration
- Feature and full regression validation
- Sprint 8 documentation and audit update

### Next Development Phase

- Monitoring orchestration
- Change persistence and history
- Dashboard WatchList visibility
- Alert/notification boundary design
- Sandbox/live evidence collection

The exact Sprint number and PR breakdown for this phase must be decided after Sprint 8 evidence review.

## Founder Success Roadmap

HYB의 첫 번째 고객은 Product Owner 자신이다.

모든 기능은 실제 판매 활동에서 검증되며,
실제 사업 성과를 만드는 것을 우선한다.

우선 검증 대상은 다음과 같다.

- 실제 투자 판단 개선
- 수익률 향상
- 시간 절약
- 반복 업무 자동화
- 실제 판매 데이터 기반 검증

사업적 가치가 검증된 기능을 중심으로
플랫폼을 점진적으로 확장한다.

## Business Validation Roadmap

Technical expansion should remain connected to real seller decisions.

Priority evidence:

- Accurate landed cost
- Marketplace fee structure
- Tax and duty impact
- Demand and competition signals
- Sales velocity
- Return and inventory risk
- Historical price stability
- Real opportunity outcomes

## Marketplace Expansion Roadmap

Expansion order is evidence-driven rather than feature-count-driven.

Current state:

- eBay: adapter and exact item lookup foundation
- Amazon: deterministic development contract; production integration pending

Future candidates:

- Walmart
- Coupang
- AliExpress
- Temu

A new Marketplace should be added only after its contract, data quality,
failure isolation, normalization, and business value are reviewed.

## Long-Term Product Direction

```text
Opportunity Discovery
→ Opportunity Evaluation
→ Explainable Investment Decision
→ WatchList Monitoring
→ Change Detection
→ Alerts
→ Automated Opportunity Discovery
```

Long-term success is measured by whether HYB improves real investment decisions,
not merely by the number of supported features or marketplaces.

Long-term vision:

Founder Success

↓

Business Decision Intelligence

↓

AI Commerce Platform

↓

Autonomous Opportunity Discovery