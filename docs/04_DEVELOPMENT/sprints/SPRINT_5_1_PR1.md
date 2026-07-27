# Sprint 5.1 PR-1 — Architecture Alignment v1

## 목표

최신 실제 코드베이스를 기준으로 HYB의 계층 책임, Discovery 실행 계약,
안정 영역, 기술 부채와 Sprint 5 확장 순서를 문서로 확정한다.

## 작업 성격

- 문서 전용 PR
- 런타임 동작 변경 없음
- 공개 API 변경 없음
- 신규 패턴 및 신규 Domain 객체 추가 없음

## 핵심 결정

1. 현재 HYB는 점진적 전환형 하이브리드 아키텍처다.
2. Discovery Workflow, Use Case, Gateway, Ranking의 현재 책임을 유지한다.
3. Ranking Strategy는 실제 대체 정책이 두 개 이상 생길 때까지 보류한다.
4. 별도 Opportunity Dataset은 현재 Result/Response/Run 계약과 중복되므로
   추가하지 않는다.
5. 새 Business Rule Engine을 중복 구현하지 않는다.
6. 이미 구현된 `OpportunityScoreEngine`과 `OpportunityDecisionEngine`을
   Discovery 흐름에 연결하는 계약을 Sprint 5의 다음 우선순위로 둔다.
7. 기존 Orchestrator와 Presentation은 한 번에 교체하지 않고 Adapter를 통해
   점진적으로 이전한다.

## 변경 파일

- `docs/02_ARCHITECTURE/ARCHITECTURE_ALIGNMENT_V1.md`
- `docs/02_ARCHITECTURE/ARCHITECTURE_INDEX.md`
- `docs/04_DEVELOPMENT/CHANGELOG.md`
- `docs/04_DEVELOPMENT/sprints/SPRINT_5_1_PR1.md`

## 검증

- 문서 링크와 경로 확인
- Python 런타임 코드 변경 없음 확인
- 전체 회귀 테스트 실행

## 다음 PR

Sprint 5.1 PR-2 — Opportunity Intelligence Integration Contract

다음 PR에서는 코드를 바로 추가하지 않고 다음을 먼저 확정한다.

- Discovery 결과에서 Opportunity Factors로 연결 가능한 데이터 Source Map
- 필수/선택 값과 결측값 정책
- 기존 Recommendation과 신규 Decision의 공존 정책
- Application Service 또는 Adapter 경계

## 실제 테스트 결과

### Architecture 관련 대상 테스트

```text
145 passed
```

실행 범위:

- Discovery Domain
- Discovery Application
- Opportunity Domain
- Opportunity Evaluation
- Opportunity Score Engine
- Opportunity Decision Engine

### 전체 회귀 테스트

```text
734 passed, 92 failed
```

실패는 이번 문서 PR의 변경 파일과 무관하며, 공통적으로 다음 기존 Snapshot
생성 경로에서 발생했다.

```text
PriceSnapshot / InventorySnapshot / SellerSnapshot
    -> __post_init__()
    -> zero-argument super().__post_init__()
    -> TypeError
```

이번 PR은 문서만 변경하므로 해당 런타임 문제를 함께 수정하지 않는다. 사용자
환경에서 보고된 기존 기준은 826 passed이며, 다음 코드 PR 전에 실행 환경과
Snapshot 상속 구현을 별도 확인해야 한다.
