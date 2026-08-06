# FOUNDER DISCUSSION RECORD — NORTH STAR REALIGNMENT

날짜: 2026-08-07

상태: PRESERVE CONTEXT

목적: 이번 토론의 결론뿐 아니라 왜 그런 결론에 도달했는지 보존한다.

> 이 문서는 정제된 ADR이 아니다.
> Founder와 AI Partner가 제품의 존재 이유, 현실적 수익 목표, 장기 이상향을 다시 정렬한 Discussion Record다.
> 향후 새로운 대화/에이전트는 결론만 읽지 말고 가능하면 전체 맥락을 읽는다.
> 현재 구현 계약이나 production 완료 상태는 코드·ADR·상태 문서가 소유하며, 이 기록이 이를 대체하지 않는다.

## 1. 시작점 — 현재 MVP에 대한 Founder의 문제 제기

Founder는 현재 MVP를 직접 사용한 뒤,
현재 기능만 보면 “내가 직접 검색해서 찾아내는 과정을 조금 줄인 것”처럼 느껴진다고 말했다.

과거 실제 상품 발굴 경험에서는 아이템스카우트에서 사람들이 많이 찾는 상품을 기준으로,
경쟁이 상대적으로 유리하고 많이 팔 수 있는 물건을 우선순위로 두고 찾았다.

Founder가 원했던 MVP에 더 가까운 모습은 다음이었다.

- 아이템스카우트 같은 시장 ranking/candidate data를 HYB에 넣는다.
- HYB가 상품군을 직접 대량 분석한다.
- 좋은 상품 후보를 먼저 추천한다.
- Founder는 추천된 후보를 검토한다.

즉 “직접 검색 → HYB 결과”보다 “HYB가 먼저 후보를 찾음 → Founder 검토”가 핵심이었다.

AI Partner는 처음에 이것을 새 방향처럼 반응했으나,
Founder는 이것이 프로젝트 초기에 이미 합의했던 장기 방향임을 지적했다.

이 지적은 중요하다.
향후에는 현재 구현에 지나치게 몰입하여 원래 North Star를 새 아이디어처럼 취급하지 않도록 한다.

## 2. 원래 장기 비전의 재확인

Founder가 다시 설명한 원래 목표:

- 사람이 할 수 없는 압도적인 검색량
- 사실 기반의 근거
- 시기/계절/트렌드 반영
- 수익성이 좋음
- 손해 가능성을 최대한 줄임
- 수요 대비 경쟁이 유리함
- HYB가 사용자보다 먼저 최적의 상품을 추천
- 충분한 검증 이후 자동화와 결합
- 궁극적으로 최고의 의사결정 AI

AI Partner는 “검색(Search)”보다 “발견(Discovery)”이라는 표현이 더 정확하다고 정리했다.

검색은 사람이 시작하지만 Discovery는 HYB가 먼저 시작한다.

## 3. 손실과 경쟁에 대한 토론

Founder는 수익성이 좋고 경쟁자가 적으며 손해를 최소화할 수 있는 상품을 원한다고 설명했다.

AI Partner의 반론:

“경쟁자가 적다”는 절대 목표가 되어서는 안 된다.
경쟁자가 많다는 것은 큰 수요를 의미할 수도 있고,
경쟁자가 적어도 시장 자체가 작을 수 있다.

합의된 방향:

> 경쟁자 절대 수가 아니라 수요 대비 경쟁이 얼마나 유리한가를 본다.

또한 “손해 0”을 알고리즘 목표로 삼으면 너무 보수적으로 변할 수 있다.

합의된 방향:

> 전체 위험조정수익을 극대화하면서 치명적 손실을 방지한다.

작은 실패 가능성을 완전히 제거하려는 대신,
한 번의 판단이 전체 자본을 크게 훼손하지 못하게 하는 Capital Safety가 중요하다.

## 4. 최종 Commerce 자동화 이상향

Founder가 추가로 명확히 한 장기 이상향:

자동서치
→ 올바른 상품 찾기
→ 자동판매
→ 자동관리
→ 다시 시장과 성과를 읽음

이 사이클이 알아서 도는 것이 Founder가 현재 상상하는 Commerce의 최고 이상향이다.

AI Partner는 기술적으로 가능하다고 평가했지만,
처음부터 완전자율화를 구현하는 방식에는 반대했다.

합의:

추천
→ Founder 승인
→ 반자동 실행
→ 실제 결과 검증
→ 제한적 자동 실행
→ 자동화 범위 확대

자동화는 엔진의 신뢰가 만들어낸 결과여야 한다.

## 5. Closed Feedback Loop

대화 중 가장 중요한 장기 경쟁우위 후보 중 하나로 정리된 내용.

HYB가 단순히 추천만 하면 충분하지 않다.

예:

예상 월 판매량 100
예상 ROI 40%

실제:
월 판매량 37
실제 ROI 18%

이 경우 왜 틀렸는지 기록해야 한다.

가능한 실패 원인:
- 수요 과대평가
- 배송비 누락
- 광고비
- 경쟁 급증
- 반품
- 상품 동일성 오류
- 계절 종료
- 공급 문제

반대 방향도 중요하다.

HYB가 Reject한 상품이 실제 시장에서 크게 성공했다면
False Negative 원인을 기록해야 한다.

장기 Data Moat 후보:

시장 데이터
+ HYB 예측
+ Founder 판단
+ 실제 투자/소싱
+ 실제 판매
+ 실제 수익/손실
+ 실패 원인

## 6. 주식과 범용 Opportunity Intelligence

Founder는 이전부터 HYB 방식이 주식 매매/투자와 구조적으로 닮았다는 점을 이야기했으며,
Commerce 성공 후 주식과 병행해보자는 아이디어가 있었다고 다시 설명했다.

Founder는 여기에 만족할 생각도 없다고 말했다.
더 좋은 성공 가능성이 있다면 계속 성장하고 싶다는 장기 야망도 명확히 했다.

AI Partner는 상위 추상 구조를 다음처럼 정리했다.

거대한 후보 공간
→ 신호 수집
→ Opportunity Detection
→ Risk-adjusted Evaluation
→ Capital Allocation
→ Execution
→ Outcome Measurement
→ Learning

그러나 중요한 제한도 합의했다.

- 주식은 지금 목표가 아니다.
- Commerce 성공과 안정화가 선행된다.
- Commerce model을 주식에 그대로 복제하지 않는다.
- General Opportunity Engine을 너무 일찍 만들지 않는다.
- 범용화는 실제 성공 사례에서 추출한다.

Founder는 이 순서에 동의했다.

## 7. Founder의 현실적 우선순위

Founder는 현재 수익이 필요하다는 현실을 다시 강조했다.

장기 이상향을 포기하지 않지만,
막연한 고점을 좇으며 너무 많은 일을 한꺼번에 하지 않는다.

우선순위:

1. Commerce에서 성공
2. 실제 수익 발생
3. 반복 가능한 수익 증명
4. Commerce 자동화 확대
5. 충분한 안정화
6. 그 후 주식/두 번째 도메인
7. 더 먼 미래에 범용 Opportunity Intelligence

Founder는 충분히 노력하고 AI Partner가 잘 돕는다면
생각보다 빠르게 많은 일을 할 수 있다고 믿지만,
“착실하게 넘어간다”는 원칙도 동시에 강조했다.

AI Partner는 시간 기반이 아닌 Evidence-Based Roadmap을 제안했다.

Founder는 이 표현이 자신이 무의식적으로 원했던 진행 방식을 잘 정리했다고 동의했다.

## 8. 개발 방식의 재정의

Founder가 원하는 프로젝트 진행 방식:

“최대한 효율적으로 빠르게 내가 원하는 길을 걷되,
안정성을 해치거나 작더라도 생긴 문제나 해결해야 하는 문제를 무시하는 일은 절대 없도록 한다.”

AI Partner의 정리:

> 목표까지 가장 빠른 길을 선택한다.
> 다만 미래의 성공을 위협하는 문제를 덮어서 얻는 속도는 진짜 속도로 인정하지 않는다.

동시에 과잉설계도 피한다.

- 지금 수익 검증에 가까워지는가?
- 지금 해결하지 않으면 더 위험해지는가?
- 안전하게 미룰 수 있는가?

이 세 질문이 향후 우선순위 판단 기준이 된다.

## 9. 국내 시장 First

Founder는 전 세계 상품을 다루는 장기 방향은 유지하지만,
지금은 국내에서 성공해보는 것이 현실적이라고 판단했다.

초기 판매 채널:
- Primary: 쿠팡
- Secondary: 네이버 스마트스토어

과거 상품 발굴:
- 쿠팡
- 아이템스카우트

과거 소싱:
- 도매꾹
- 1688

추가 선행정보:
- SNS

AI Partner는 데이터 source를 역할별로 분리하자고 제안했다.

Candidate Universe:
- 아이템스카우트

Demand / Competition:
- 쿠팡
- 네이버에서 지속 가능한 데이터

Supply:
- 1688
- 도매꾹

Trend / Seasonality:
- 네이버 트렌드/검색 데이터
- SNS는 후순위 early signal

Outcome:
- 실제 쿠팡/네이버 판매자 성과

## 10. 초기 Discovery Universe와 Filter Cascade

처음부터 인터넷 전체를 스캔하지 않는다.

검증된 Candidate Universe에서 시작해서
비용이 낮은 필터로 대량 후보를 줄이고
비싼/정밀한 검증은 소수 후보에만 적용한다.

예시:

10,000 candidates
→ HYB broad filter
→ 1,000
→ demand/competition verification
→ 100
→ sourcing/economics verification
→ 20
→ risk/evidence ranking
→ Founder Top 5

이 방식은 단기 수익 필요성과 장기 대규모 Discovery Engine 사이의 현실적 다리로 합의되었다.

## 11. ItemScout와 데이터 획득 전략

Founder는 아이템스카우트 API 과금과 관련해
크롤링이나 화면 캡처 방식으로 데이터를 가져올 수 있는지 질문했다.

AI Partner의 결론:

기술적으로 screenshot → OCR → structured facts는 가능하다.

그러나 장기 핵심 pipeline에는 다음 문제가 있다.

- OCR 오독
- UI 변경 취약성
- 대량 처리 비용
- 이용약관/권한 문제

따라서 초기 검증 단계에서는 다음 순서를 권장했다.

1. CSV/Excel export
2. screenshot/manual ingestion
3. 반자동 exporter
4. 가치가 증명되고 volume이 커지면 공식 API

Screenshot OCR을 버리지 않는다.
오히려 Universal Evidence Ingestion의 한 경로로 볼 수 있다.

다만 API/CSV/OCR/inference는 같은 신뢰도로 취급하지 않는다.

## 12. HYB가 가져야 할 핵심 경쟁우위

토론 결과 장기 Moat 후보:

1. Scale
2. Change Detection
3. Cross-Market Intelligence
4. Evidence-based Risk-adjusted Ranking
5. Closed Feedback Loop

특히 5번은 장기간 실제 판매결과가 누적될수록 경쟁자가 복제하기 어려운 자산이 될 가능성이 크다.

또한 Canonical Product / identity matching 능력은
서로 다른 marketplace listing과 공급처 상품을 같은 상품 또는 대체 가능한 상품군으로 연결하는 데 중요한 기술적 Moat 후보로 남는다.

## 13. CONFIRMED

- Commerce success is #1.
- HYB는 Search Tool이 아니라 Opportunity Discovery Engine을 지향한다.
- HYB가 상품 후보를 먼저 추천해야 한다.
- 국내 시장에서 먼저 성공한다.
- 쿠팡은 초기 핵심 판매/실행/feedback 시장 후보다.
- 아이템스카우트는 초기 Candidate Universe provider로 활용할 가치가 있다.
- 1688/도매꾹은 supply/cost 축의 핵심 후보다.
- 네이버 트렌드/검색 데이터는 demand/seasonality sensor 후보로 중요하다.
- SNS는 초기 final-decision source보다 early signal에 가깝다.
- 실제 판매 결과는 장기적으로 가장 중요한 학습 데이터가 된다.
- 자동화는 신뢰가 증명될수록 단계적으로 확대한다.
- 주식/범용 엔진은 Commerce 성공 이후의 인생/프로젝트 로드맵에 보관한다.
- 시간보다 Evidence가 다음 phase 진입을 결정한다.
- 빠르게 가되 실제 문제를 덮지 않는다.
- 과잉설계도 피한다.

## 14. HYPOTHESES TO PROVE

- ItemScout-based candidate universe가 실제로 초기 수익상품 발견에 충분히 유용한가?
- Demand/competition/supply/trend/outcome의 5축으로 초기 추천 정확도를 확보할 수 있는가?
- Change signal이 absolute popularity보다 더 좋은 early opportunity indicator가 되는가?
- HYB 추천이 Founder manual research보다 더 빠르고 더 정확한가?
- Risk-adjusted ranking이 높은 raw ROI ranking보다 실제 realized return에서 우수한가?
- 실제 판매 feedback이 recommendation precision을 유의미하게 향상시키는가?
- 국내 성공 패턴이 다른 Commerce 시장으로 재현 가능한가?

## 15. OPEN QUESTIONS

가장 가까운 다음 질문:

> Founder가 과거 아이템스카우트에서 실제로 어떤 화면, 숫자, 순서로 상품을 찾고 버렸는가?

이를 통해 Founder의 tacit seller judgment를
첫 번째 Discovery input schema와 filtering hypothesis로 옮긴다.

추가 Open Questions:

- ItemScout에서 실제 확보 가능한 export/API fields
- 쿠팡 시장 데이터의 지속 가능하고 허용된 획득 경로
- 1688/도매꾹 sourcing facts의 초기 확보 방법
- 네이버 trend data의 구체적 time-series contract
- 첫 Commerce validation experiment의 size/budget
- 성공/실패 판정 기준
- Capital Safety 초기 한도

## 16. 다음 대화의 시작점

이 기록 이후 바로 이어갈 질문:

“예전에 아이템스카우트에서 상품을 찾을 때,
처음 어떤 화면을 보고,
어떤 숫자를 확인하고,
어떤 기준으로 바로 버리고,
어떤 경우에 쿠팡까지 들어가 검토했는가?”

Founder의 실제 과거 행동을 가능한 구체적으로 재현한다.

## 17. 후속 Discussion — Capital-Ready Commerce MVP

Founder는 장기 기능 전체를 완성한 뒤에야 실제 돈을 투입하자는 뜻이 아니었다고 명확히 했다.
실제 돈이 들어가기 직전까지 필요한 시스템을 높은 완성도로 만들고,
그 근거를 확인한 뒤 제한된 자본으로 Commerce validation을 시작하려는 의미였다.

이 단기 목표를 `HYB Capital-Ready Commerce MVP`로 정리했다.

Candidate Universe
→ Screening
→ Market Validation
→ Sourcing Validation
→ Conservative Economics
→ Risk / Evidence / Unknown Safety
→ Explainable Ranking
→ Capital Readiness
→ Founder Decision

### 17.1 CONFIRMED

- Recommendation-first Discovery가 Capital-Ready MVP의 출발 방향이다.
- 대량 후보에는 cheap screening을 먼저 적용하고 소수 후보를 정밀 분석한다.
- 실제 투자 전 demand, competition, trend/change, sourcing 가능성과 economics를 검증해야 한다.
- 중요한 비용이나 evidence의 `UNKNOWN`을 0으로 가장하지 않는다.
- 단순 점수보다 추천 이유, 알려진 사실, unknown, 주요 위험을 Founder에게 설명해야 한다.
- 좋은 상품과 좋은 투자는 같지 않으며, 전체 자본 대비 exposure를 보는 Capital Gate가 필요하다.
- Shadow Experience와 Real Commerce Experience는 동일한 evidence가 아니다.
- 실제 production 변경 전 `Capital-Ready MVP Gap Analysis`를 수행한다.
- 공식 Roadmap 재정렬은 Gap Analysis 이후 별도 단계로 남긴다.

### 17.2 Initial Validation Capital — PLANNING HYPOTHESIS

첫 실전 validation capital로 약 100~200만 원 범위를 논의했다.

이 숫자는 절대적 project contract나 보장된 최적 자본이 아니다.
생활비·비상자금과 분리된 risk capital을 전제로 한 현실적 planning range이며,
실제 상품, MOQ, 비용과 Capital Safety 분석에 따라 변경할 수 있다.

### 17.3 Shadow Mode — STRONG CANDIDATE

실제 돈을 투입하기 전에 HYB가 매일 Opportunity를 추천하고,
추천 당시 facts, prediction, ranking을 immutable하게 보존한 뒤
실제 시장 변화와 비교하는 아이디어를 논의했다.

Founder는 실제 자본으로 실험할 수 있는 수보다 훨씬 많은 판단 경험을
손실 없이 축적할 가능성을 높게 평가했다.

분석 후보:

- recommendation 유지
- downgrade
- reject
- prediction error

Shadow Mode의 mandatory 여부와 architecture는 아직 확정하지 않는다.

### 17.4 Paper Portfolio — STRONG CANDIDATE

가상 validation capital을 Opportunity별로 배분하여
position size, reserve, concentration, capital exposure를 검증하는 아이디어를 논의했다.

1,500,000 KRW 예시는 개념 설명을 위한 planning example이며 정책 값이 아니다.
구체적인 portfolio algorithm은 확정하지 않는다.

### 17.5 Experience Data Direction — ACTIVE HYPOTHESIS

Founder와 AI Partner는 좋은 Engine만큼 좋은 Experience Data가 중요하다는 데 동의했다.

검토할 evidence hierarchy:

Market Observation
→ Shadow Decision Outcome
→ Founder-reviewed Decision
→ Real Capital Decision
→ Actual Commerce Outcome

실제 Commerce Outcome은 conversion, advertising, returns, logistics,
inventory turnover, realized profit/loss 같은 현실 마찰을 포함한다.
따라서 Shadow data는 실제 결과를 대체하지 않는다.

### 17.6 Capital Gate and Staged Deployment

Opportunity가 좋아도 Founder의 전체 validation capital 대비 초기 투자 exposure가 과도하면
투자를 차단하거나 축소할 수 있어야 한다는 방향에 동의했다.

Real-Money Ready 이후에도 validation pool 전체를 한 번에 투입하지 않고,
일부 자본 투입 → 실제 결과 확인 → 다음 capital release 순서의 staged deployment를
Capital Safety 후보로 남겼다. 정확한 threshold와 비율은 미결이다.

### 17.7 OPEN QUESTIONS

- Capital-Ready capability 중 현재 저장소에 이미 존재하거나 재사용 가능한 것은 무엇인가?
- Shadow Mode와 Paper Portfolio 중 무엇이 Real-Money Readiness의 필수 gate인가?
- Best / Base / Conservative scenario를 어떤 authoritative facts로 구성할 수 있는가?
- 핵심 unknown이 있을 때 readiness를 어떤 Domain/API 의미로 표현할 것인가?
- Capital Gate의 exposure, reserve, MOQ, downside threshold는 무엇인가?
- staged deployment의 release evidence와 비율은 무엇인가?
- Shadow와 Real Experience를 어떤 신뢰도 및 학습 가중치로 구분할 것인가?

다음 단계는 위 계약을 임의로 설계하는 것이 아니라,
실제 저장소 전체를 대상으로 `Capital-Ready MVP Gap Analysis`를 수행하는 것이다.
