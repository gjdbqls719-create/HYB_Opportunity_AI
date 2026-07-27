# Sprint 5.1 PR-3 — Minimal Opportunity Intelligence Integration

## 목표

PR-2에서 확정한 Opportunity Intelligence Integration Contract를 최소 코드로 구현한다.
기존 Discovery와 Recommendation을 교체하지 않고, 신규 Score/Decision Engine으로
이어지는 병렬 통합 경로를 검증한다.

## 핵심 구현

### Application 계약

- `OpportunityIntelligenceStatus`
  - `evaluated`
  - `unavailable`
  - `failed`
- `OpportunityIntelligenceInput`
- `OpportunityIntelligenceResult`
- `OpportunityIntelligenceInputAdapter` Port
- `OpportunityIntelligenceService`

### Infrastructure Adapter

`DiscoveryResultOpportunityIntelligenceAdapter`는 현재 공식적으로 재사용 가능한
`metadata["confidence_score"]`만 엄격하게 `Decimal`로 변환한다.

현재 공식 정책이 없는 다음 5개 Factor는 임의 값으로 채우지 않는다.

- `price_score`
- `trend_score`
- `demand_score`
- `competition_score`
- `risk_score`

따라서 기본 Adapter 결과는 정상적인 `unavailable` 상태다.

### 완전한 Provider 경로

Application Service는 Adapter가 완전한 `OpportunityFactors`와 confidence를
제공할 때만 다음 순서로 실행한다.

```text
DiscoveryResult
    ↓
OpportunityIntelligenceInputAdapter
    ↓
OpportunityScoreEngine.calculate()
    ↓
OpportunityDecisionEngine.evaluate()
    ↓
OpportunityIntelligenceResult(evaluated)
```

## 안전성 결정

1. 기존 `DiscoveryResult.opportunity_score`를 신규 Factor로 재사용하지 않는다.
2. 누락 Factor에 0 또는 50을 넣지 않는다.
3. `unavailable`은 예외가 아닌 정상 운영 상태다.
4. 타입 및 범위 계약 위반은 `failed` 결과로 격리한다.
5. 기존 Recommendation 필드는 수정하거나 덮어쓰지 않는다.
6. Discovery Use Case와 Workflow에는 아직 통합하지 않는다.

## 변경 파일

- `app/application/opportunity_intelligence/__init__.py`
- `app/application/opportunity_intelligence/models.py`
- `app/application/opportunity_intelligence/ports.py`
- `app/application/opportunity_intelligence/service.py`
- `app/infrastructure/opportunity_intelligence/__init__.py`
- `app/infrastructure/opportunity_intelligence/discovery_result_adapter.py`
- `tests/test_opportunity_intelligence_integration.py`
- `docs/04_DEVELOPMENT/CHANGELOG.md`
- `docs/04_DEVELOPMENT/sprints/SPRINT_5_1_PR3.md`

## 테스트

Targeted regression:

```text
81 passed
```

포함 범위:

- 신규 Opportunity Intelligence 통합 테스트
- Opportunity Score Engine
- Opportunity Decision Engine
- Discovery Application

현재 실행 환경의 전체 테스트:

```text
740 passed, 92 failed
```

92개 실패는 기존 Snapshot dataclass의 `super().__post_init__()`와 Python 3.14
환경 사이에서 발생하는 기존 호환 문제다. PR-2 기준 동일 환경의
`734 passed, 92 failed`에서 신규 테스트 6개가 추가로 통과했으며, 이번 PR이
기존 실패 수를 증가시키지 않았다.

사용자 프로젝트 환경의 기대 결과는 기존 826개 + 신규 6개인 `832 passed`다.

## 완료 기준

- Application 상태/결과 계약 구현
- Adapter Port 구현
- DiscoveryResult Adapter 구현
- confidence 엄격 변환
- missing Factor 명시
- 완전한 입력에서 Score + Evaluation 실행
- 기존 Discovery/Recommendation 동작 무변경
- 신규 및 관련 회귀 테스트 통과

## 다음 PR

Sprint 5.1 PR-4 — Discovery Opportunity Intelligence Enrichment Contract

예정 검토 범위:

- Discovery 응답에 신규 Intelligence 결과를 비파괴적으로 연결하는 방식
- 순위와 기존 Recommendation 유지
- 단건/배치 평가의 Application 책임
- Presentation 노출 전 호환성 계약
