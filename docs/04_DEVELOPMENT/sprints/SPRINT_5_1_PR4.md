# Sprint 5.1 PR-4 — Discovery Workflow Intelligence Integration

## 목적

Discovery의 기존 실행 계약을 유지하면서 Opportunity Intelligence를 선택적으로 실행하는 비파괴 통합 경로를 추가한다.

## 구현 결정

- `DiscoverOpportunitiesWorkflow`에 선택적 `intelligence_service` 의존성을 추가했다.
- Ranking이 끝난 각 `DiscoveryResult`를 순서대로 평가한다.
- 결과는 Discovery 결과와 같은 순서를 유지하는 `intelligence_results` tuple로 반환한다.
- Intelligence가 설정되지 않으면 기존 Workflow 단계와 반환 동작을 그대로 유지한다.
- 개별 Intelligence 평가에서 예상하지 못한 예외가 발생해도 해당 항목만 `FAILED` 결과로 변환한다.
- Intelligence 실패는 Discovery 성공과 선택적 Publish 실행을 중단하지 않는다.

## 변경 파일

- `app/application/discovery/workflow.py`
- `tests/test_discovery_workflow_intelligence.py`
- `docs/04_DEVELOPMENT/sprints/SPRINT_5_1_PR4.md`
- `docs/04_DEVELOPMENT/CHANGELOG.md`

## 테스트

신규 및 관련 회귀 테스트:

```text
16 passed
```

실행 명령:

```powershell
pytest tests/test_workflow_engine.py tests/test_opportunity_intelligence_integration.py tests/test_discovery_workflow_intelligence.py -q
```

전체 테스트는 작업 환경의 Python 3.14에서 기존 Snapshot 상속 문제로 다음 결과를 보였다.

```text
743 passed, 92 failed
```

92개 실패는 `PriceSnapshot`, `InventorySnapshot`, `SellerSnapshot`의 기존 `super().__post_init__()` 오류에서 발생했으며 이번 PR 변경 경로와 무관하다. 사용자 환경의 기존 기준은 832 passed이므로 신규 테스트 3개를 포함하면 835 passed가 예상되지만, 실제 사용자 환경 결과를 최종 기준으로 삼는다.

## 다음 단계

Sprint 5.1 PR-5에서는 Workflow에서 생성된 Intelligence 결과를 기반으로 Explainability 경계를 설계한다. 기존 Recommendation을 교체하지 않고 병렬 설명 결과로 확장한다.
