# Sprint 5.1 PR-5 — Discovery Factor Provider

## 목적

기존 Discovery 결과에서 검증 가능한 원천값을 읽어 `OpportunityFactors`를 생성하고,
Opportunity Intelligence가 기본 Adapter만으로 실제 Score와 Evaluation을 만들 수 있게 한다.

## 변경 사항

- `DiscoveryFactorPolicy` 추가
- ROI, 가격 추세 보정값, 예상 월 판매량, 경쟁 판매자 수, 위험 수준을 0~100 점수로 정규화
- 일부 원천값이 없으면 해당 Factor만 `missing_factors`에 기록
- 모든 원천값이 준비된 경우 완전한 `OpportunityFactors` 생성
- Discovery Gateway가 `trend_score_adjustment`를 metadata에 전달
- 기존 Gateway 테스트 더블과의 호환성을 위해 선택 필드는 `getattr(..., None)`으로 처리

## 정규화 정책

### Price

ROI를 다음 기준점 사이에서 선형 보간한다.

- 0% → 0
- 15% → 40
- 30% → 60
- 50% → 80
- 100% 이상 → 100

### Trend

기존 Trend Score Adjustment 범위를 Opportunity Factor로 변환한다.

- -18 → 0
- 0 → 50
- +15 → 100

### Demand

예상 월 판매량을 다음 기준점 사이에서 선형 보간한다.

- 0 → 0
- 50 → 40
- 200 → 70
- 500 이상 → 100

### Competition

경쟁 판매자 수가 적을수록 높은 안전성 점수를 부여한다.

- 0 → 100
- 5 → 90
- 20 → 60
- 50 → 30
- 100 이상 → 0

### Risk

기존 위험 수준을 위험 안전성 점수로 변환한다.

- low → 90
- medium → 50
- high → 10

## 비파괴 원칙

- 원천값 누락 시 임의 0점 또는 50점을 넣지 않는다.
- 부분 Factor 객체를 만들지 않는다.
- 기존 Recommendation 및 Discovery 공개 필드는 변경하지 않는다.
- 기존 `OpportunityIntelligenceStatus` 계약을 유지한다.

## 테스트

관련 통합 및 회귀 테스트:

```text
24 passed
```

현재 실행 환경 전체 테스트:

```text
747 passed, 92 failed
```

92개 실패는 기존 Python 3.14 Snapshot `super().__post_init__()` 문제와 동일하다.
이번 PR 신규 테스트 4개는 모두 통과했으며 기존 실패 수는 증가하지 않았다.
사용자 환경 기준 예상 전체 결과는 기존 835개에 4개가 추가된 `839 passed`이다.
