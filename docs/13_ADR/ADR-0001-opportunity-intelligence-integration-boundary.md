# ADR-0001 — Opportunity Intelligence Integration Boundary

- 상태: Accepted
- 날짜: 2026-07-28
- 결정자: Product Owner / HYB AI Technical Partner

## Context

신규 Opportunity Domain은 정규화된 5개 Factor를 요구하지만, 현재 Discovery와
기존 Orchestrator는 aggregate score, 원시 금액, 범주형 위험도, 가감점 등 서로
다른 의미와 단위를 제공한다.

이 값을 즉시 숫자로 변환하면 빠르게 연결할 수 있지만, Factor 의미가 불명확하고
기존 Recommendation과 신규 Decision이 충돌할 위험이 있다.

## Decision

1. Opportunity Intelligence 통합 오케스트레이션은 Application 계층에 둔다.
2. 기존 모델 변환은 Infrastructure Adapter가 담당한다.
3. 5개 Factor 중 하나라도 없으면 신규 Score를 만들지 않는다.
4. 누락 Factor에 0 또는 50과 같은 암묵적 기본값을 사용하지 않는다.
5. 계산 불가능 상태를 `unavailable`로 명시한다.
6. 기존 Recommendation은 전환 조건이 충족될 때까지 유지한다.
7. 신규 Evaluation은 병행 결과로 제공한다.

## Consequences

### Positive

- Factor의 비즈니스 의미를 보호한다.
- 거짓 정밀도와 중복 Business Rule을 방지한다.
- 기존 826-test 기준 동작을 안전하게 유지할 수 있다.
- Factor 정책을 독립적인 작은 PR로 추가할 수 있다.

### Negative

- PR-3 직후에도 모든 Discovery 결과에 신규 Evaluation이 생성되지는 않는다.
- Factor 정책 완성 전까지 두 추천 체계가 병행된다.
- Presentation에서 `unavailable` 상태를 이해해야 한다.

## Rejected Alternatives

### 기존 최종 점수를 모든 Factor에 복제

각 요소의 의미가 사라지고 결과가 순환적으로 계산되므로 기각한다.

### 누락 Factor에 50 사용

데이터 부족을 중립 상태로 위장해 신뢰도를 과장하므로 기각한다.

### 기존 Recommendation 즉시 제거

현재 소비자와 테스트의 호환성을 깨뜨리므로 기각한다.

### Domain 모델에 Optional Factor 허용

불완전한 Domain 객체를 허용하고 Engine 검증을 약화하므로 기각한다.
