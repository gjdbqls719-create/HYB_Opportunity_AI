# HYB EVIDENCE-BASED ROADMAP — DRAFT FOR REALIGNMENT

상태: DRAFT / DISCUSSION-BASED

주의: 기존 ROADMAP을 바로 대체하기 위한 문서가 아니다.

목적: 이번 Founder Discussion의 방향을 향후 공식 Roadmap 재정렬의 기준으로 보존한다.

공식 현재 계획은 [ROADMAP.md](ROADMAP.md)와 [MVP_ROADMAP.md](MVP_ROADMAP.md)가 소유한다.
아래 phase는 승인된 일정이나 구현 완료 선언이 아니라 evidence gate를 검토하기 위한 addendum다.

## Next Analysis Gate — Capital-Ready MVP Gap Analysis

상태: CONFIRMED PROCESS / ROADMAP NOT YET REALIGNED

다음 production 개발이나 공식 Roadmap 재정렬 전에 실제 저장소를 기준으로
Capital-Ready Commerce MVP capability를 감사한다.

Candidate Universe
→ Screening
→ Market Validation
→ Sourcing Validation
→ Conservative Economics
→ Risk / Evidence / Unknown Safety
→ Explainable Ranking
→ Capital Readiness
→ Founder Decision

각 capability를 다음 중 하나로 분류한다.

- Already Exists
- Reusable
- Partially Exists
- Needs Extension
- Missing
- Architecture Decision Required

Shadow Mode와 Paper Portfolio는 강력한 후보지만 mandatory phase 또는 architecture로 확정하지 않는다.
Gap Analysis가 reuse, extension, missing contract를 밝힌 뒤 별도 Roadmap Realignment를 진행한다.

## Phase 0 — Current Baseline

현재 HYB는:
- authoritative Discovery
- product grouping/read model
- Founder Home
- persisted evidence/replay/lineage
- Candidate/Price/Economics/Snapshot/Review/Decision 관련 상당한 foundation

을 가지고 있다.

그러나 Founder가 keyword를 입력해야 시작하는 현재 UX는
장기 목표의 최종 MVP 경험이 아니다.

Exit evidence:
- 현재 system baseline은 유지
- Founder가 실제 browser에서 Discovery를 실행 가능
- 다음 단계에서 기존 안정성을 파괴하지 않고 recommendation-first로 이동 가능

## Phase 1 — Recommendation-First Domestic MVP

목표:
Founder가 직접 상품명을 검색하지 않아도 HYB가 candidate universe를 받아
Top Opportunities를 먼저 제안한다.

초기 universe:
- ItemScout export/API/manual import 등
- 필요한 경우 curated domestic candidate data

초기 verification:
- demand
- competition
- supply
- economics
- risk/evidence confidence

Exit evidence:
- 실제 후보 universe를 대량 처리
- Founder에게 Top N 자동 추천
- 추천 근거 표시
- 최소 1개 이상 실제 상품 validation으로 연결

## Phase 2 — Real Commerce Profit Validation

목표:
HYB 추천이 실제 돈을 벌 수 있는가를 검증한다.

Founder approves investment manually.

측정:
- 예상 ROI
- 실제 ROI
- 예상 판매속도
- 실제 판매속도
- inventory turnover
- 광고/반품/수수료/배송 차이
- 실패 원인

Exit evidence:
- 실제 수익 발생
- prediction vs realized result 기록
- 한 번의 우연이 아니라 여러 validation cycle 확보

## Phase 3 — Repeatability

목표:
HYB가 반복적으로 수익 가능한 Opportunity를 발견하는가를 증명한다.

핵심:
- Precision/Recall
- ROI error
- Capital loss
- false positive/false negative taxonomy
- season/trend robustness

Exit evidence:
- 여러 시기/카테고리에서 반복성
- Founder manual research 대비 명확한 효율 우위
- recommendation confidence calibration 근거

## Phase 4 — Closed Feedback Learning

목표:
실제 판매 결과가 다음 추천을 개선한다.

- predicted vs realized
- failure cause
- model/policy version
- opportunity cohorts
- postmortem

Exit evidence:
- feedback가 실제 ranking/filter 변경으로 연결
- 변경 전후 품질 차이 측정 가능
- data lineage와 explainability 유지

## Phase 5 — Progressive Commerce Automation

목표:
검증된 범위에 한해 사람 개입을 줄인다.

순서:
recommendation
→ approval workflow
→ assisted execution
→ bounded automation
→ broader automation

자동화 대상 후보:
- listing
- pricing
- inventory
- sourcing workflows
- order operations
- advertising
- monitoring

Capital Safety required.

Exit evidence:
- 자동 실행이 manual baseline 대비 품질/안전 저하 없음
- stop/rollback/limits 검증
- audited outcome

## Phase 6 — Autonomous Commerce Loop

목표:
자동 search/discovery
→ selection
→ execution/selling
→ operation/management
→ outcome feedback
→ improved discovery

가 가능한 한 자율적으로 순환.

Founder는 strategy/limits/governance의 최종 owner로 남는다.

## Phase 7 — Second Domain (Investment/Stocks)

Commerce success/stability 이후에만 검토.

Commerce architecture를 무비판적으로 재사용하지 않는다.

Goal:
Opportunity methodology가 두 번째 domain에서도 재현 가능한지 검증.

## Phase 8 — General Opportunity Intelligence

두 개 이상의 실제 domain success 이후에만 추출.

Generalization은 미래 가정을 기반으로 미리 만들지 않는다.
성공한 concrete systems의 공통 구조를 증거로 추출한다.

# Governing Rule

Phase 이동은 날짜가 아니라 Evidence Gate로 결정한다.

빠르게 증명되면 빠르게 이동한다.
근본 문제가 발견되면 해결한다.
안전하게 미룰 수 있는 것은 미룬다.
