# HYB COMMERCE OPPORTUNITY STRATEGY

상태: CONFIRMED DIRECTION + ACTIVE HYPOTHESES

작성 기준: 2026-08-07 Founder Discussion

> 이 문서는 사업 방향과 검증 가설을 함께 보존한다. Commerce-first, recommendation-first,
> domestic-first와 evidence discipline은 확정 방향이다. 특정 데이터 공급자·획득 방식의 유효성,
> 필터 단계 수치와 KPI는 검증 가설이며, 실제 adapter 또는 production integration 완료를 뜻하지 않는다.
> 미결 질문은 [Founder Discussion Record](../RESEARCH/FOUNDER_DISCUSSION_RECORD_2026-08-07.md#15-open-questions)를 따른다.

## 1. 현재 MVP에 대한 재평가

현재 Founder Home은 사용자가 keyword를 입력하면 Discovery가 실행된다.

이 기능과 지금까지 만든 architecture, persistence, replay, lineage, snapshot, evidence, safety 기반은 무의미하지 않다.
오히려 향후 실제 자본을 다루는 시스템의 신뢰성과 자동화 기반이 된다.

그러나 제품 가치만 보면 현재 단계는 주로:

사용자가 직접 찾음
→ HYB가 조사 과정을 일부 단축

에 가깝다.

Founder가 원한 MVP의 핵심은 더 앞에 있다.

시장 데이터
→ HYB 대량 분석
→ 좋은 후보 자동 필터링
→ Top Opportunities를 Founder에게 먼저 추천

따라서 앞으로 핵심 제품 목표는 “검색 UX”가 아니라 “추천형 Discovery”로 이동해야 한다.

## 2. 인간보다 압도적으로 잘하기 위한 핵심 능력

### Scale

사람이 하루에 검토할 수 없는 수만~수십만 개 후보를 다룬다.
목표는 Maximum Search Volume 자체가 아니라 Maximum Useful Coverage다.

### Change Detection

현재 절대값만 보지 않는다.

- 검색 관심 증가율
- 판매 속도 변화
- 경쟁 판매자 증가 속도
- 평균 가격 변화
- 공급가격 변화
- 리뷰 변화
- 계절성 전환

현재 가장 인기 있는 상품보다 “인기가 생기기 시작하는 상품”을 먼저 찾는 것을 중요하게 본다.

### Cross-Market Intelligence

Demand market과 Supply market을 연결한다.

쿠팡 / 네이버 / 시장 트렌드
↕
1688 / 도매꾹 / 공급처

“잘 팔릴 것 같다”에서 끝나지 않고
“이 비용으로 소싱하여 이 시장에서 팔면 실제로 돈이 남을 가능성이 높다”까지 연결한다.

### Evidence-Based Risk-Adjusted Ranking

높은 ROI 하나만 보고 추천하지 않는다.

예상수익
+ 근거 신뢰도
+ 수요 강도
+ 경쟁 대비 시장 매력
+ 공급 안정성
- 불확실성
- 리스크

를 함께 본다.

정확한 수식은 실제 결과 데이터가 쌓이기 전에 성급히 고정하지 않는다.

### Closed Feedback Loop

장기 Data Moat의 핵심 후보다.

시장 데이터
+ HYB 예측
+ Founder 판단
+ 실제 구매/소싱
+ 실제 판매
+ 실제 순이익/손실
+ 실패 원인

을 연결한다.

예상 ROI와 실제 ROI의 차이,
예상 판매량과 실제 판매량의 차이,
추천했지만 실패한 경우,
Reject했지만 실제 시장에서는 성공한 False Negative까지 기록한다.

## 3. 경쟁에 대한 관점

“경쟁자가 적다” 자체를 목표로 삼지 않는다.

경쟁자가 많아도 수요가 압도적으로 크면 좋은 시장일 수 있고,
경쟁자가 적어도 수요가 없으면 나쁜 시장일 수 있다.

따라서 핵심은:

> 수요 대비 유효 경쟁이 얼마나 유리한가

이다.

## 4. 국내 시장 우선

현재 현실적 1단계는 대한민국 Commerce에서 성공하는 것이다.

Primary execution/sales market 후보:
- 쿠팡

Secondary sales market 후보:
- 네이버 스마트스토어

Candidate / market intelligence:
- 아이템스카우트
- 쿠팡에서 확보 가능한 시장 신호
- 네이버 데이터/트렌드

Supply:
- 1688
- 도매꾹

Early trend:
- SNS는 가치가 있으나 초기 핵심 판단 source보다는 선행 Discovery signal로 본다.

Outcome:
- 우리 실제 쿠팡/네이버 판매 성과

## 5. 초기 국내 Discovery Universe

권장 초기 구조:

아이템스카우트 등 Candidate Universe
→ HYB 1차 대량 필터
→ 쿠팡/네이버 수요·경쟁 검증
→ 1688/도매꾹 원가·MOQ·조달 위험 검증
→ Economics / Risk
→ Top N
→ Founder 검토
→ 실제 판매
→ Outcome feedback

데이터 source 개수를 무작정 늘리기보다 다음 축을 먼저 완성한다.

- Demand
- Competition
- Supply / Landed Cost
- Trend / Seasonality
- Actual Outcome

## 6. ItemScout의 초기 역할

아이템스카우트는 HYB의 영구 정체성이 아니다.

초기 역할:

> High-quality Candidate Universe Provider

처음부터 HYB가 아이템스카우트 전체 기능을 복제할 필요는 없다.

목표 예시:

10,000 candidates
→ 1,000
→ 100
→ 20
→ Founder Top 5

비싼 정밀 분석을 모든 상품에 적용하지 않고
싸고 넓은 1차 필터 뒤에 점점 정밀한 검증을 붙인다.

## 7. ItemScout Data Ingestion Strategy

초기에는 정식 API만 고집하지 않는다.

검토 순서:

1. CSV / Excel export
2. Founder가 직접 제공하는 screenshot
3. 필요하면 반자동 exporter
4. 가치와 규모가 증명되면 정식 API 계약

Screenshot OCR은 기술적으로 가능하지만 장기 backbone으로는 적합하지 않을 수 있다.

이유:
- OCR 오독 가능성
- UI 변경 취약성
- 대량 처리 비효율
- 사용권한/약관 확인 필요

그러나 Universal Ingestion의 한 방식으로는 가치가 있다.

Screenshot / PDF / CSV / Excel / External API
→ HYB Evidence Ingestion
→ Normalized Market Facts

## 8. Data Authority / Confidence

획득 방식별 신뢰도를 동일하게 취급하지 않는다.

정책 방향 예시:

- 공식 API / 직접 authoritative seller data: highest trust
- 공식 export CSV/Excel: high trust
- manually verified structured import: high/medium
- screenshot OCR: medium until verified
- inferred/estimated data: explicitly marked estimated

주요 값에는 source provenance, observed time, confidence/verification status를 보존한다.

## 9. 초기 제품 성공 화면의 목표

Founder가 아침에 HYB를 열었을 때:

- 오늘 분석한 후보 수
- HYB 추천 수
- Conservative filter 통과 수
- Top Opportunities

를 먼저 보여준다.

각 Opportunity에는 최소한 다음이 필요하다.

- 무엇을 파는 상품인가
- 왜 지금인가
- 수요 변화
- 경쟁 변화
- 공급가 / landed cost
- 예상 판매가
- 예상 순이익
- 예상 ROI
- 위험
- 근거 신뢰도
- 미확인 사항

핵심 질문:

> 이 상품에 내 돈을 투자해도 되는가?

## 10. 장기 KPI 후보

기능 수나 테스트 수만으로 사업 성공을 판단하지 않는다.

장기 핵심 KPI 후보:

- Opportunity Precision
- Opportunity Recall
- Realized ROI Error
- Capital Loss Rate

추가 후보:
- time-to-decision
- inventory turnover
- realized net profit
- drawdown / loss concentration
- false positive / false negative cause taxonomy

아직 KPI threshold는 실제 데이터가 없으므로 확정하지 않는다.

## 11. Capital-Ready Commerce MVP — CONFIRMED DIRECTION

장기 Commerce automation 전체를 완성한 뒤에야 실전으로 가는 것이 아니다.
첫 실제 자본 투입 직전에 필요한 판단 흐름을 충분한 근거와 함께 제공하는
`HYB Capital-Ready Commerce MVP`를 단기 목표로 둔다.

Candidate Universe
→ Screening
→ Market Validation
→ Sourcing Validation
→ Conservative Economics
→ Risk / Evidence / Unknown Safety
→ Explainable Ranking
→ Capital Readiness
→ Founder Decision

핵심 요구 방향:

- Candidate Universe에서 HYB가 먼저 Top Opportunities를 제안한다.
- 싸고 넓은 screening으로 약한 후보를 먼저 제거하고 소수 후보를 정밀 검증한다.
- Demand, Competition, Trend / Seasonality, Change signals를 점진적으로 검증한다.
- 실제 자본 투입 전 공급처와 조달 가능성을 검증한다. 초기에는 Founder-assisted sourcing도 허용할 수 있다.
- 낙관적인 ROI 하나보다 보수적 경제성 판단을 중요하게 취급한다.

Best / Base / Conservative scenario 구분은 검토 대상이다.
정확한 scenario algorithm과 Founder-facing 표현 계약은 아직 확정하지 않는다.

## 12. Unknown Data Safety — CONFIRMED PRINCIPLE

실제 자본 판단에 중요한 비용이나 evidence가 `UNKNOWN`이면 이를 0으로 가장하지 않는다.

예를 들어 국제배송비나 광고비가 확인되지 않았을 때 0원으로 authoritative calculation에 넣어
높은 ROI 또는 BUY 판단을 만드는 방향은 금지한다.

필수 정보가 부족하면 투자 판단을 보류할 수 있어야 한다.
`NOT READY`, `NEEDS VERIFICATION`, `INVESTMENT HOLD`는 의미 후보이며,
구체적인 enum, API, Domain contract는 아직 결정하지 않는다.

## 13. Evidence and Explainability — CONFIRMED DIRECTION

Capital-Ready MVP는 최종 점수 하나로 실제 투자 결정을 유도하지 않는다.

Founder는 최소한 다음 질문에 답을 얻을 수 있어야 한다.

- 왜 추천했는가?
- 무엇을 알고 있는가?
- 무엇을 아직 모르는가?
- 무엇이 가장 큰 위험인가?

검토할 evidence dimensions:

- profitability
- demand
- competition advantage
- trend
- sourcing confidence
- cost confidence
- evidence completeness
- major risks
- unknown facts

## 14. Capital Gate — CONFIRMED DIRECTION, OPEN CONTRACT

좋은 상품과 좋은 투자는 같은 의미가 아니다.

Opportunity가 좋아도 Founder의 전체 validation capital 대비 초기 exposure가 과도하면
투자를 차단하거나 축소할 수 있어야 한다.

향후 검토할 요소:

- total validation capital
- requested investment
- single-opportunity exposure
- reserve capital
- confidence / evidence completeness
- downside risk
- MOQ constraints

정확한 threshold, allocation algorithm, 상태 계약은 아직 확정하지 않는다.

## 15. Initial Validation Capital — PLANNING HYPOTHESIS

첫 실전 검증 자본으로 약 100~200만 원 범위를 논의했다.

이 범위는 절대적인 project contract나 최적 자본 보장이 아니다.
생활비와 비상자금에서 분리된 risk capital을 전제로 한 planning assumption이며,
실제 상품, MOQ, 비용과 Capital Safety 분석에 따라 달라질 수 있다.

## 16. Shadow Mode and Paper Portfolio — STRONG CANDIDATES

Shadow Mode는 실제 자본 투입 전에 HYB가 실제처럼 Opportunity를 추천하고,
추천 당시 facts, prediction, ranking을 immutable하게 보존한 뒤
recommendation 유지, downgrade, reject, prediction error를 추적하는 후보 기능이다.

Paper Portfolio는 가상 validation capital을 Opportunity별로 배분하여
position size, reserve, concentration, capital exposure를 함께 검증하는 후보 기능이다.
예시 자본 1,500,000 KRW는 개념 설명이며 확정 정책 값이 아니다.

두 기능의 mandatory 여부, architecture, portfolio algorithm은 확정하지 않는다.

## 17. Experience Data Direction — ACTIVE HYPOTHESIS

좋은 Engine만큼 좋은 Experience Data가 중요하다.

검토할 evidence hierarchy:

Market Observation
→ Shadow Decision Outcome
→ Founder-reviewed Decision
→ Real Capital Decision
→ Actual Commerce Outcome

Shadow Experience와 Real Commerce Experience를 동일하게 취급하지 않는다.
실제 결과는 conversion, advertising, returns, logistics, inventory turnover,
realized profit/loss와 같은 현실 마찰을 포함하므로 더 강한 evidence가 될 수 있다.
Shadow data는 real outcome을 대체하지 않는다.

## 18. Real-Money Readiness and Next Step

검토할 전략 흐름:

Discovery Ready
→ Capital Ready
→ Shadow Mode / Paper Portfolio
→ Real-Money Readiness
→ Staged Real Capital Validation
→ Actual Outcome
→ Learning Loop

Real-Money Ready 이후에도 전체 validation pool을 한 번에 투입하지 않고,
일부 자본 투입과 실제 결과 확인 뒤 다음 자본을 release하는 staged deployment를
Capital Safety 후보 전략으로 둔다. 정확한 비율은 결정하지 않는다.

다음 공식 단계는 production 구현이 아니라 `Capital-Ready MVP Gap Analysis`다.
현재 capability를 `Already Exists`, `Reusable`, `Partially Exists`, `Needs Extension`,
`Missing`, `Architecture Decision Required`로 분류한 뒤 Roadmap 재정렬 여부를 판단한다.
