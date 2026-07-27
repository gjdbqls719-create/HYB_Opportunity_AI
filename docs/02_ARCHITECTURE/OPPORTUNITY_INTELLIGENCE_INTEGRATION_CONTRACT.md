# Opportunity Intelligence Integration Contract v1

## 1. 목적

이 문서는 기존 Discovery 흐름과 신규 Opportunity Intelligence 도메인 사이의
통합 경계를 확정한다.

통합 대상은 다음 두 엔진이다.

- `app.engine.opportunity_score.OpportunityScoreEngine`
- `app.engine.opportunity_decision.OpportunityDecisionEngine`

현재 Discovery 결과와 기존 Orchestrator의 풍부한 분석 데이터를 억지로 신규
요소 점수에 대입하지 않고, 어떤 값이 공식 입력으로 사용 가능하며 어떤 값이
아직 부족한지를 명시한다.

## 2. 현재 계약

### 2.1 Discovery 출력

`app.domain.discovery.DiscoveryResult`는 다음 값을 공식 필드로 제공한다.

- `product`
- `opportunity_score: float`
- `matched_product_count`
- 기존 Recommendation의 grade/action/summary
- `rank`
- `metadata`

`app.infrastructure.discovery.OrchestratorOpportunityDiscoveryGateway`는 기존
`engine.orchestrator.OpportunityResult`를 위 계약으로 변환한다.

### 2.2 Opportunity Intelligence 입력

`OpportunityScoreEngine`은 다음 5개 요소가 모두 포함된
`OpportunityFactors`를 요구한다.

- `price_score: Decimal`
- `trend_score: Decimal`
- `demand_score: Decimal`
- `competition_score: Decimal`
- `risk_score: Decimal`

각 값은 0 이상 100 이하의 정규화된 점수여야 한다. `risk_score`는 위험 크기가
아니라 안전성 점수이므로 높을수록 유리하다.

별도로 `confidence: Decimal`을 받으며, 이 값도 0 이상 100 이하여야 한다.

## 3. Source Map

| 신규 입력 | 현재 후보 Source | 현재 상태 | PR-3 사용 여부 | 판단 근거 |
|---|---|---|---|---|
| `confidence` | `OpportunityResult.confidence.confidence_score` → `DiscoveryResult.metadata["confidence_score"]` | 직접 변환 가능 | 가능 | 이미 0~100 정수로 계산되며 의미가 동일함 |
| `price_score` | `analysis["raw_opportunity_score"]`, ROI, 순이익, PriceIntelligence | 직접 매핑 불가 | 불가 | 기존 aggregate 점수나 금액은 순수 가격 요소 점수가 아님 |
| `trend_score` | `TrendScoreResult.adjustment`, `PriceTrend` | 직접 매핑 불가 | 불가 | adjustment는 가감점이며 0~100 정규화 점수가 아님 |
| `demand_score` | `estimated_monthly_sales` 관련 입력 | 직접 매핑 불가 | 불가 | 원시 판매량 추정치의 범위와 정규화 정책이 없음 |
| `competition_score` | `competitor_count`, `SellerAnalysisResult.competition_level` | 직접 매핑 불가 | 불가 | 원시 개수/범주를 0~100으로 바꾸는 공식 정책이 없음 |
| `risk_score` | `risk_level`, Inventory/Seller/Market 분석 | 직접 매핑 불가 | 불가 | 여러 위험 신호를 안전성 점수로 합성하는 공식 정책이 없음 |

## 4. 금지되는 매핑

다음 방식은 정보 의미를 훼손하므로 사용하지 않는다.

1. 기존 `final_opportunity_score`를 5개 Factor에 복제한다.
2. 누락 Factor에 임의로 `50`을 넣는다.
3. Trend adjustment를 범위 검증 없이 Factor로 사용한다.
4. 문자열 위험도에 근거 없는 숫자를 즉시 부여한다.
5. 기존 Recommendation score를 신규 Opportunity Score로 이름만 바꿔 사용한다.
6. `metadata` 키가 없을 때 조용히 0 또는 50으로 대체한다.

## 5. 결측값 정책

### 5.1 원칙

- Factor는 모두 필수다.
- 일부 Factor만으로 `OpportunityScore`를 만들지 않는다.
- 결측을 중립값으로 위장하지 않는다.
- 계산 불가능은 실패가 아니라 명시적인 `unavailable` 상태다.

### 5.2 제안 Application 계약

PR-3의 최소 구현은 다음 의미를 가진 Application 경계를 사용한다.

```text
DiscoveryResult
    ↓
OpportunityIntelligenceInputAdapter
    ↓
OpportunityIntelligenceInput
    ├─ factors: OpportunityFactors | None
    ├─ confidence: Decimal | None
    └─ missing_factors: tuple[str, ...]
    ↓
OpportunityIntelligenceService
    ├─ factors가 완전하면 Score + Evaluation 생성
    └─ 불완전하면 unavailable 결과 반환
```

이 계약은 Domain 객체에 결측 상태를 넣지 않는다. 결측과 준비 상태는
Application 계층이 관리한다.

## 6. 제안 결과 계약

Application Service의 결과는 다음 세 상태를 구분해야 한다.

- `evaluated`: 신규 Score와 Evaluation 생성 완료
- `unavailable`: 필요한 Factor가 부족함
- `failed`: 타입 오류, 범위 오류 등 계약 위반

`unavailable`은 예외가 아니다. 데이터 수집과 정책이 아직 준비되지 않은 정상적인
운영 상태다.

권고 형태:

```text
OpportunityIntelligenceResult
    status
    score: OpportunityScore | None
    evaluation: OpportunityEvaluation | None
    missing_factors: tuple[str, ...]
```

## 7. 기존 Recommendation과 신규 Decision 공존 정책

### 7.1 PR-3~PR-4

기존 Recommendation을 Source of Truth로 유지한다.

- 기존 `recommendation_grade`
- 기존 `recommendation_action`
- 기존 `recommendation_summary`

신규 `OpportunityEvaluation`은 별도 결과로 병행 제공하며, 기존 필드를
덮어쓰지 않는다.

### 7.2 전환 조건

신규 Decision이 공식 Source of Truth가 되려면 다음 조건을 모두 만족해야 한다.

1. 5개 Factor의 공식 계산 정책이 존재한다.
2. 기존 Recommendation과 비교하는 회귀/특성 테스트가 있다.
3. Dashboard와 CLI가 신규 Reason 코드를 표시할 수 있다.
4. 운영 샘플에서 결정 차이를 검토했다.
5. Product Owner가 전환을 승인했다.

### 7.3 값 대응 주의

기존 Recommendation에는 `CAUTION`, `AVOID`가 있고 신규 Decision에는
`SKIP`이 있다. 문자열을 직접 일대일 치환하지 않는다. 전환은 별도 Migration
Policy에서 결정한다.

## 8. 책임 경계

### Domain

- `OpportunityFactors`, `OpportunityScore`, `OpportunityEvaluation`
- 점수 범위와 불변 조건
- Decision 및 Reason 코드

### Engine

- 완전하고 유효한 Factor로 Score 계산
- Score로 Evaluation 계산

### Application

- 데이터 준비 상태 확인
- Adapter 호출
- 결측 상태 관리
- Score Engine과 Decision Engine 오케스트레이션

### Infrastructure

- 기존 Orchestrator 결과에서 원시 Source 추출
- 외부 데이터와 기존 모델을 Application 입력으로 변환
- 정책 없이 임의 점수를 생성하지 않음

### Presentation

- 기존 Recommendation과 신규 Evaluation을 구분해 표시
- Reason 코드의 사용자 문구/현지화
- `unavailable` 상태의 안내

## 9. PR-3 최소 구현 범위

PR-3에서는 완전한 5-Factor 계산기를 만들지 않는다.

구현 범위:

1. Application Result/Status 계약
2. Input Adapter Port
3. 기존 DiscoveryResult용 Adapter
4. `confidence_score`의 엄격한 Decimal 변환
5. 누락 Factor 목록 반환
6. 완전한 Factor Provider를 주입했을 때만 Score/Evaluation 실행
7. 기존 Discovery와 Recommendation 동작 무변경

이 방식은 통합 경로를 실제 코드로 검증하면서도 근거 없는 Business Rule을
서둘러 도입하지 않는다.

## 10. 후속 정책 PR

Factor 정책은 각각 독립된 작은 PR로 추가한다.

1. Price Factor Policy
2. Trend Factor Policy
3. Demand Factor Policy
4. Competition Factor Policy
5. Risk Safety Factor Policy

두 개 이상의 실제 정책 변형이 생기기 전에는 Strategy 계층을 추가하지 않는다.

## 11. 결정 요약

- 현재 데이터만으로 신규 Opportunity Score를 정식 생성하지 않는다.
- 유일하게 직접 재사용 가능한 값은 confidence다.
- 결측값은 임의 기본값이 아니라 `unavailable`로 처리한다.
- 신규 Evaluation은 기존 Recommendation과 병행 운영한다.
- 통합 책임은 Application Service와 Infrastructure Adapter 사이에 둔다.
- PR-3은 계약과 실행 경로를 최소 구현하고 기존 동작을 변경하지 않는다.
