# HYB Opportunity AI Roadmap

## Current Strategic Priority

HYB의 현재 최우선 목표는 **실제로 팔리고 이익을 남길 상품을 반복해서 발견하고,
작은 real-world validation을 통해 그 능력을 증명하는 것**이다. 시스템과 architecture는
그 결과를 만들고 안전하게 반복하기 위한 수단이다.

현재 운영 우선순위:

```text
FIND
→ FAST SCREEN
→ CHEAP REAL-WORLD VALIDATION
→ SELL / DROP
→ DEEP VALIDATION FOR SURVIVORS
→ SCALE
→ OUTCOME
→ LEARN
```

Near-term work는 다음에 직접 기여할 때 우선한다.

- Discovery accuracy와 Top Opportunity hit rate 개선
- low-cost validation의 속도와 launch quality 개선
- actual sales, returns, costs와 realized profit 수집
- predicted-vs-actual economics 비교
- 반복되는 운영 friction 제거
- 의미 있는 capital을 보호하는 existing authority 연결

Capital-Ready foundation은 폐기하지 않는다. Competition/Demand → DMV → target-aware
Sourcing → Verified Economics → Conservative Economics → Critical Cost → Capital
Readiness → Capital Gate → Founder Approval → Execution chain은 meaningful scaling
capital의 authoritative deep path로 계속 유효하다. 새 운영 전략은 약한 초기 후보마다
그 전체 분석 비용을 먼저 지불하지 않도록 screening과 bounded validation을 앞세운다.

Validation Capital과 Scaling Capital은 현재 운영상 구분일 뿐 새 Domain authority나
정책 값이 아니다. material capital deployment는 기존 Capital Readiness/Capital Gate
경계를 우회하지 않는다.

현재 Genuine vehicle seat-back organizer run과 이미 persisted된 authority는 이 우선순위
변경으로 재해석하지 않는다. 해당 run은 기존 문서의 external blocker와 exact evidence
규칙을 유지한 채 계속한다.

---

## Completed Foundation

현재 저장소에는 다음 기반이 이미 구현되어 있다.

- authoritative Discovery persistence, restart, replay, conflict
- Candidate와 Opportunity의 persisted lineage
- Product, Price, Economics Snapshot 및 complete Snapshot Chain
- Market Evidence와 Verified Economics
- Production Safety
- Decision Readiness와 Decision Composition
- Founder approve/reject lifecycle
- Actual Economics와 Estimated-vs-Actual Economics Variance
- append-only durability, source binding, auditability

이 완료 이력은 폐기하지 않는다. Capital-Ready MVP는 이 기반을 다시 만드는 작업이 아니라, 실제 자본 판단에 필요한 아직 없는 facts와 gates를 연결하는 작업이다.

---

## Capital-Ready Roadmap

### CR-0 — Minimal Architecture Decisions

구현 전에 future coupling이 큰 authority, identity, replay, trust, capital-safety 경계만 결정한다.

- Candidate Universe authority, batch identity, replay
- Screening policy ownership과 reject history
- Sourcing identity, quote, MOQ, supplier trust boundary
- selling product와 sourcing product의 match authority
- critical economics cost scope
- Conservative Scenario authority와 version
- Capital Readiness boundary
- Capital Gate authority와 reserve/exposure 의미
- Capital-bound Founder Approval의 exact source binding

모든 기능을 새 ADR 대상으로 만들지 않는다. 기존 계약으로 안전하게 연결 가능한 구현은 작은 PR로 진행한다.

### CR-1A — Discovery Intelligence

Real-Money validation 전에 recommendation-first discovery를 완성한다.

1. Candidate Universe contract
2. bulk/manual structured ingestion
3. provenance, batch identity, duplicate handling
4. Cheap Screening
5. reject reason과 history
6. domestic Demand/Competition evidence ingress
7. 현재 계약이 허용하는 Trend/Change evidence 연결
8. explainable, risk-aware ranking
9. persisted Top N recommendation

초기 Candidate Universe는 CSV, Excel 또는 manual structured ingestion으로 시작할 수 있다. ItemScout API는 필수 선행조건이 아니다. ItemScout, Coupang, Naver 연동은 실제 source 확보와 authority가 검증될 때 source별 PR로 진행한다.

#### Persisted Discovery Screening F2

[ADR-0067](../13_ADR/ADR-0067-persisted-discovery-screening-authority.md)은
screening authority를 기존 Discovery에 두고 evaluation과 ranking publication을
분리한다. 구현은 다음 작은 PR 순서를 따른다.

1. PR2: explicit finalized-Group correlation contract
2. PR3: versioned screening/ranking policy descriptors와 structured reasons
3. PR4: immutable evaluation/ranking/provenance Domain contracts
4. PR5: SQLite composite completion persistence와 atomicity/replay/corruption/concurrency
5. PR6: production completion integration과 runtime-free v2 replay
6. PR7: Founder screening read API와 Top-N UI

PR7과 F2 closure 후 [ADR-0068](../13_ADR/ADR-0068-shadow-opportunity-validation-authority.md)이
Shadow Opportunity Validation architecture를 MVP foundation으로 승인했다.
F1 durable attempt/recovery는 계속 별도 track이며 Shadow와 하나의 대형 PR로
합치지 않는다.

### CR-1B — Capital Safety

Discovery Track과 병렬로 실제 손실 방지 경계를 완성한다.

1. Founder-assisted Sourcing Admission
2. sourcing persistence와 replay
3. supplier, quote, MOQ, option, shipping, lead-time facts
4. sourcing product와 selling product match verification
5. economics critical cost scope 확장
6. 모든 critical cost에서 `UNKNOWN != 0` 적용
7. Conservative Economics scenario
8. Capital Readiness
9. Capital Gate
10. capital-bound Founder Approval

현재 발견된 **missing shipping을 numeric zero로 변환하는 경로**는 Capital-Ready 계산 전에 반드시 제거하거나 authoritative calculation에서 격리해야 하는 critical issue다. Unknown cost를 zero로 가장한 결과는 Capital Gate의 근거가 될 수 없다.

### CR-2 — Founder Capital Journey

기존 Founder Home과 Opportunity Detail을 최대한 재사용하여 다음 facts를 한 판단 흐름에서 보여준다.

- Top Opportunity detail
- sourcing facts
- economics breakdown
- known / estimated / unknown 구분
- Conservative result
- major risks
- evidence provenance와 confidence
- required capital
- Capital Gate result
- exact evidence-bound Founder approval

새 UI framework를 만들지 않는다. Founder는 승인 전에 어떤 사실이 확인되었고 무엇이 아직 unknown인지 볼 수 있어야 한다.

### CR-3 — Shadow Validation

ADR-0068은 Shadow를 새 bounded domain이나 WatchList 기능으로 만들지 않고,
기존 Opportunity boundary가 thesis/evaluation value semantics를 소유하도록
결정했다. Shadow는 실제 출시 없이 recommendation-at-time-T와 immutable
baseline을 보존하고, elapsed-time future market evidence로 thesis가
`MAINTAINED`, `WEAKENED`, `INVALIDATED`, `INCONCLUSIVE`인지 평가한다. 가상
판매·매출·이익이나 Actual Outcome은 만들지 않는다.

첫 authoritative MVP는 exact ADR-0060 O2와 exact persisted ADR-0067 screening
evaluation/publication에 묶인 `MACHINE_SCREENING_BASED` 등록만 허용한다.
Candidate-only 및 `FOUNDER_DECLARED` 등록은 MVP에서 제외한다. Checkpoint는
manual/on-demand로 시작하고 cadence는 versioned policy data다.

작은 구현 순서는 다음과 같다.

1. Shadow PR1: ADR + contract decision — 완료
2. Shadow PR2: immutable registration/baseline Domain contracts — 완료
3. Shadow PR3: append-only SQLite registration/baseline persistence + replay — 다음
4. Shadow PR4: exact O2 + persisted screening 기반 manual Application/API 등록
5. trustworthy baseline 수집 시작
6. Shadow PR5: manual checkpoint publication contracts/persistence
7. Shadow PR6: deterministic thesis evaluation
8. Shadow PR7: Founder Shadow Portfolio/read surface

Scheduler, alerts, generic workflow, automatic calibration/ML은 선행조건이
아니다. Shadow와 Real Outcome denominator는 섞지 않는다. Paper Portfolio도
자동으로 mandatory로 확정하지 않으며 별도 근거와 결정을 요구한다.

### CR-4 — Actual Outcome Readiness

기존 Actual Economics와 Economics Variance의 historical behavior를 유지하고,
closed-loop v2 authority를 additive하게 확장하여 첫 실제 거래의 결과를 잃지
않도록 한다.

- advertising
- returns, refunds, loss
- tax, duty, logistics scope
- 필요한 inventory와 quantity
- realized profit와 ROI
- sourcing lineage
- approved capital lineage
- recommendation lineage
- prediction vs actual
- failure reason foundation

Actual Outcome capture path는 첫 판매 전에 준비되어야 한다.

ADR-0054는 closed-loop v2의 판매 측 입력을 legacy `ActualEconomics`의 재해석이
아닌 별도 `ActualSaleSettlement`로 결정한다. 첫 Coupang 검증은 명시적
상품/평가 창, 실제 출고 수량, 매출, 환불·취소, 광고, fulfillment/storage,
수수료와 payout provenance를 수동 evidence로 보존하며, 미확인 중요 범위는
`BLOCKED`로 남긴다. Domain/Application/API와 판매 출고를 반영하는 Owned
Inventory v2는 구현되었고 Actual Outcome v2는 후속 구현 범위다.

#### CR-1B6D1 Actual Outcome decision and validation cuts

ADR-0055 defines ActualOutcome as a future immutable persisted result over one
exact Purchase Execution, one terminal COMPLETE Actual Acquisition Settlement,
the exact Goods Receipt set, and an explicit cumulative COMPLETE Actual Sale
Settlement prefix. It separates sold COGS and realized profit from remaining
sellable basis, damaged loss, and unreceived exposure. Multi-purchase allocation
is blocked until a separate lot/pool policy exists. Owned Inventory v2 and the
ActualOutcome Domain/Application/SQLite/API are now implemented by CR-1B6D2.

The milestones are distinct:

- Functional Founder MVP: production-callable purchase, settlement, receipt,
  sale, and owned-inventory boundaries exist.
- Real-Money Validated MVP: one genuine chain additionally has a CALCULABLE
  persisted ActualOutcome using actual evidence and money. Full liquidation and
  Variance v2 are not required.
- Closed-Loop Learning MVP: the same lineage has an exact Conservative Economics
  result, ActualOutcome, and future Variance v2.

No real-world validation is claimed by this decision-only CR.

#### CR-1B6D2 Actual Outcome implementation and production API

ADR-0055 is implemented through immutable Domain/Application authority,
append-only SQLite history and replay/alias receipts, production UUID/time
suppliers, and `POST /api/v1/opportunities/{opportunity_id}/actual-outcomes`.
The result freezes exact acquisition, receipt, and sale snapshots and exposes
conserved cost basis, realized operating economics, ratio availability, and
separate inventory resolution without planned or legacy fallback.

This establishes software capability only. Real-Money Validated MVP is not
achieved until one genuine O2 completes the real purchase, settlement, receipt,
sale, and CALCULABLE ActualOutcome evidence chain. The next architecture task is
Variance v2 authority for exact ConservativeEconomics versus exact
ActualOutcome; no Variance v2 behavior is implemented here.

#### CR-1B6E1 Conservative vs Actual Variance v2 authority

ADR-0056 now defines the decision-only `conservative-actual-variance / 2.0.0`
boundary. A future immutable result will bind one explicit persisted
ConservativeEconomics result to one explicit persisted ActualOutcome, preserve
per-metric comparability and actual-only/exposure context, and classify future
calibration suitability independently from numeric comparison. It performs no
latest selection, source recalculation, automatic calibration, model training,
or policy update.

The milestone boundaries remain separate:

- Functional Founder MVP remains the production-callable operational journey.
- Real-Money Validated MVP still requires one genuine CALCULABLE ActualOutcome;
  Variance v2 is not required.
- Closed-Loop Learning MVP software capability additionally requires persisted
  Variance v2 over an exact persisted Conservative/Actual pair, structured
  comparability, and calibration eligibility. Operational validation still
  requires genuine real-world data.

For the first real-world variance, archive/reference the exact Conservative
result before external purchase, create the genuine ActualOutcome after the
actual loop, and compare only those two exact IDs. A post-outcome replacement
prediction is not calibration-eligible.

#### CR-1B6E2 Conservative vs Actual Variance v2 implementation

ADR-0056 is now implemented through immutable Domain/Application authority,
exact source reconstruction, append-only SQLite history and replay/alias
receipts, and
`POST /api/v1/opportunities/{opportunity_id}/economics-variances`. The result
preserves ordered comparable metrics, actual-only/predicted-only context,
inventory exposure, source timestamps, and calibration eligibility without
latest lookup, source recalculation, or fabricated zero values.

This establishes Closed-Loop Learning MVP software capability only. Operational
validation still requires one genuine real-world O2 whose exact pre-purchase
Conservative result and CALCULABLE ActualOutcome are compared. Calibration,
model training, and automatic policy update remain future work.

### Real-Money Ready Gate

Real-Money Ready는 기능 목록 완료가 아니라 다음 evidence gate를 모두 통과한 상태다.

#### Discovery Intelligence

- authoritative Candidate Universe
- Cheap Screening과 reject history
- 필요한 domestic market evidence
- persisted Top N recommendation

#### Capital Safety

- verified sourcing facts와 product match
- critical costs가 known이거나 blocking 상태
- Conservative Economics
- Capital Readiness와 Capital Gate

#### Founder Authority

- Founder가 exact evidence와 unknowns를 확인
- approval이 exact recommendation, sourcing, economics, gate sources에 binding

#### Validation and Outcome

- Shadow Mode 적용 여부는 CR-3 architecture decision 결과를 따름
- Actual Outcome capture 준비
- critical tests 통과
- unresolved critical unknown 없음

### CR-5 — Staged Real-Money Validation

Founder planning range는 **100~200만원**이지만 policy 값이 아니다. 생활비와 비상자금에서 분리된 risk capital이어야 하며, 실제 상품, MOQ, Capital Gate 결과에 따라 달라질 수 있다.

자본은 한 번에 전부 사용하지 않는다.

small initial release

→ real result

→ review

→ next capital release

정확한 release 비율은 아직 결정하지 않는다.

---

## Evidence-Based Progression

달력이 아니라 evidence가 다음 Phase 진입을 결정한다.

- 빠르게 증명되면 빠르게 진행한다.
- critical issue가 발견되면 먼저 해결한다.
- 안전하게 미룰 수 있는 과잉설계는 뒤로 보낸다.
- 실제 판매 후에는 actual result, prediction variance, false positive/negative, failure reason, recommendation improvement, repeatability를 검증한다.

---

## Deferred Until Repeated Commerce Validation

다음 작업은 반복 가능한 Discovery, launch와 actual Commerce outcome evidence가
확보되기 전 우선순위가 아니다.

- autonomous purchasing
- full commerce automation
- generalized portfolio engine
- ML optimizer
- 필요성이 증명되지 않은 worker/queue framework
- multi-country expansion
- broad marketplace UI
- stock/investment implementation
- general Opportunity Engine
- unnecessary new identity frameworks

---

## Long-Term Direction

기존 North Star는 유지한다.

Domestic Commerce success

→ repeated profitability

→ progressive automation

→ autonomous Commerce loop

Commerce의 장기 loop는 automatic market scan → opportunity selection → sourcing/capital decision → automatic selling → operational management → actual outcome → learning → repeat이다.

Commerce에서 반복 가능한 수익성과 progressive automation을 증명한 뒤에만 Investment/Stock을 두 번째 domain으로 검토한다. General Opportunity Intelligence는 그보다 더 장기적인 방향이며 현재 Sprint backlog가 아니다.

관련 장기 원칙은 [HYB Long-Term Vision](../00_FOUNDATION/HYB_LONG_TERM_VISION.md), [Project North Star](../00_FOUNDATION/09_PROJECT_NORTH_STAR.md), [Commerce Opportunity Strategy](../09_BUSINESS/HYB_COMMERCE_OPPORTUNITY_STRATEGY.md)를 따른다.

---

## Implementation Sequence

현재 실행 순서는 기존 CR authority를 보존하면서 real business validation을 앞세운다.

1. 현재 Genuine run의 external evidence blocker를 사실대로 해소하고 exact lineage를 계속한다.
2. 실제로 팔릴 후보를 찾는 Discovery와 Fast Screen을 outcome 기준으로 검증한다.
3. 수동 launch-quality workflow로 bounded, low-cost real-world validation을 수행한다.
4. weak candidate는 빠르게 Drop하고 실제 원인과 비용을 보존한다.
5. survivor는 exact sourcing/economics와 기존 deep capital path로 scaling 적합성을 검증한다.
6. actual sales, returns, costs와 realized profit을 predicted facts와 비교한다.
7. 반복 friction과 measurable value가 증명된 부분부터 progressive automation한다.

세부 evidence gate와 연구 맥락은 [HYB Evidence-Based Roadmap — Draft](HYB_EVIDENCE_BASED_ROADMAP_DRAFT.md) 및 [Founder Discussion Record](../RESEARCH/FOUNDER_DISCUSSION_RECORD_2026-08-07.md)를 참고한다. 본 문서가 현재 공식 실행 우선순위를 정의한다.
