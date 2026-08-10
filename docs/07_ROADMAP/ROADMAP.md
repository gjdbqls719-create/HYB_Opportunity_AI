# HYB Opportunity AI Roadmap

## Current Strategic Priority

HYB의 현재 최우선 목표는 **Capital-Ready Commerce MVP**, 즉 Founder가 실제 자본을 투입하기 전에 추천, 소싱, 비용, 위험, 승인 근거를 신뢰할 수 있는 **Real-Money Ready** 상태를 만드는 것이다.

현재 단계는 단순 ROI 계산기나 Decision Engine 기능 추가가 아니다. 기존의 authoritative evidence chain을 재사용하여 다음 두 필수 Track을 함께 완성한다.

### Track A — Discovery Intelligence

Candidate Universe

→ Cheap Screening

→ Domestic Market Validation

→ Explainable / Risk-aware Ranking

→ Top Opportunities

### Track B — Capital Safety

Sourcing Validation

→ Complete Critical Cost Scope

→ Unknown Safety

→ Conservative Economics

→ Capital Readiness

→ Capital Gate

→ Capital-bound Founder Approval

어느 한 Track만으로는 Capital Ready가 아니다.

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

Shadow Mode는 실제 돈을 투입하기 전 추천 품질을 검증하는 strong gate candidate다. 다만 별도 architecture decision 전에는 mandatory gate로 확정하지 않으며 CR-1보다 앞서 구현하지 않는다.

검토 범위는 recommendation-at-time-T, immutable prediction snapshot, later market outcome, downgrade/maintain/reject, revision history, no-real-money disposition이다.

Paper Portfolio도 자동으로 mandatory로 확정하지 않는다. Capital Gate 정책 검증에 필요하다는 근거가 생기면 CR-3 또는 CR-3B에서 결정한다.

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

## Deferred Until After Capital Readiness

다음 작업은 Capital-Ready 전 우선순위가 아니다.

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

1. CR-0 최소 architecture decisions
2. CR-1A Discovery Intelligence와 CR-1B Capital Safety의 작은 병렬 PR
3. CR-2 Founder Capital Journey
4. CR-3 Shadow Validation decision 및 필요한 구현
5. CR-4 Actual Outcome Readiness
6. Real-Money Ready Gate 검증
7. CR-5 Staged Real-Money Validation
8. 실제 evidence에 따른 recommendation 개선과 progressive Commerce automation

세부 evidence gate와 연구 맥락은 [HYB Evidence-Based Roadmap — Draft](HYB_EVIDENCE_BASED_ROADMAP_DRAFT.md) 및 [Founder Discussion Record](../RESEARCH/FOUNDER_DISCUSSION_RECORD_2026-08-07.md)를 참고한다. 본 문서가 현재 공식 실행 우선순위를 정의한다.
