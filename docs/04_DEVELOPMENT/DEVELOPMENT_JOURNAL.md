# HYB Development Journal

## Purpose

프로젝트의 역사, 방향 변화, 주요 의사결정과 배운 점을 기록한다.

이 문서는 단순 변경 목록이 아니라 다음 질문에 답하는 장기 기록이다.

- 왜 이 프로젝트를 시작했는가?
- 어떤 방향을 선택했고 왜 선택했는가?
- 어떤 기술적·사업적 판단이 중요했는가?
- 무엇을 배웠으며 다음 개발에 어떻게 반영할 것인가?

---

## Project Direction

HYB Opportunity AI는 단순 상품 검색 도구가 아니다.

장기적으로는 시장 데이터를 수집하고,
동일 상품을 식별하며,
가격·비용·위험·판매 가능성을 분석하고,
그 결과를 설명 가능한 형태로 전달하는
**AI 기반 Opportunity Discovery and Decision Platform**을 목표로 한다.

프로젝트의 성공 기준은 기능 수가 아니라 다음과 같다.

- 실제 사업 의사결정에 도움이 되는가
- 판단 근거를 설명할 수 있는가
- 장기적으로 안정적으로 확장할 수 있는가
- 실데이터와 실제 수익 가능성으로 검증할 수 있는가

---

## Core Development Principles

### Architecture First

기능을 빠르게 추가하기 전에 책임과 경계를 먼저 확인한다.

단기 편의보다 다음 우선순위를 따른다.

1. 정확성
2. 안정성
3. 유지보수성
4. 확장성
5. 가독성
6. 성능
7. 개발 속도

### Document First

코드와 문서를 함께 발전시킨다.

기존 문서를 확인하지 않은 상태에서 새 내용을 덮어쓰지 않으며,
문서마다 역할을 구분한다.

- PROJECT_STATUS: 현재 상태
- CHANGELOG: 변경사항
- DEV_LOG: 실제 작업 기록
- DEVELOPMENT_JOURNAL: 방향과 배움
- SPRINT_HISTORY: Sprint 단위 완료 요약

### Explainability

HYB가 제시하는 점수와 추천은 이유를 설명할 수 있어야 한다.

Engine에서 계산한 근거가
Decision Report,
AI Partner,
Dashboard까지 일관되게 전달되어야 한다.

### Test Discipline

테스트 개수 자체보다 계약과 경계를 실제로 검증하는지가 중요하다.

기능 변경 시 관련 테스트와 전체 회귀 테스트를 함께 확인하고,
실행하지 않은 테스트를 통과했다고 기록하지 않는다.

---

## Major Milestones

### Foundation

프로젝트의 구조, 역할, 협업 원칙과 문서 체계를 수립했다.

### Opportunity Intelligence Engine

Product Matching,
Price Intelligence,
Trend,
Confidence,
Opportunity Scoring,
Recommendation,
Orchestrator를 연결했다.

### Discovery Integration

Discovery Workflow가 Opportunity Intelligence를 선택적으로 실행하고,
항목별 실패를 격리하며,
기존 공개 동작을 유지하도록 통합했다.

### Explainable Decision Pipeline

Sprint 6에서 분석 결과를 단순 점수로 끝내지 않고,
시장 조정,
추천,
Decision Report,
AI Partner,
Dashboard까지 판단 이유가 흐르도록 확장했다.

전체 회귀 테스트 853개가 통과했고,
Sprint 6 변경사항은 Commit 및 Push되었다.

---

## Key Lessons Learned

### 임의 기본값은 정보가 아니다

사용할 수 없는 Factor에 임의의 0이나 50을 채우면
시스템은 계산을 계속할 수 있지만 판단 신뢰도는 낮아진다.

그래서 HYB는 불완전한 상태를 `unavailable`로 명시하고,
실제 데이터가 준비되었을 때만 평가하도록 설계한다.

### 기존 동작을 보존하며 확장해야 한다

새로운 Intelligence 기능은 기존 Discovery와 Recommendation을 즉시 대체하지 않고,
일정 기간 병행하면서 계약과 결과를 검증해야 한다.

### 문서 손상도 기술 부채다

한글 인코딩이 깨진 문서는 기록이 존재해도 사용할 수 없다.

문서는 코드와 마찬가지로
읽을 수 있어야 하고,
책임이 명확해야 하며,
변경 이력을 유지해야 한다.

### 문서 구조도 실제 저장소에서 확인해야 한다

대화에서 전달된 경로나 이전 스냅샷만으로 문서 존재 여부를 단정하면
실제 저장소 구조와 다른 결론을 낼 수 있다.

이번 감사에서는 `SPRINT_HISTORY.md`가 없다고 판단했던 이전 메모를
실제 저장소 기준으로 정정했다.

실제 경로는 다음과 같았다.

```text
docs/04_DEVELOPMENT/sprints/SPRINT_HISTORY.md
```

앞으로 문서 구조, 파일 수, 최신 상태와 같은 사실은
항상 실제 저장소 Inventory와 Git 기록을 먼저 확인한 뒤 문서화한다.

### 테스트 통과만으로 사업 검증이 끝나지 않는다

853개의 테스트는 소프트웨어 안정성을 의미하지만,
실제 상품이 수익으로 이어진다는 것을 보장하지는 않는다.

앞으로는 Production Marketplace 데이터,
Landed Cost,
수수료,
세금,
판매 속도,
경쟁도,
반품 위험 등 실제 사업 신호를 연결해야 한다.

---

## Current Focus — Sprint 7

Sprint 7의 첫 목표는 새로운 기능 추가가 아니라,
Sprint 6까지 완성된 구조를 안정적으로 정리하는 것이다.

현재 우선순위:

1. 문서 아키텍처 정비
2. 문서 인코딩 및 내용 복구
3. 문서별 책임과 업데이트 규칙 확립
4. Presentation 구조 검토
5. 공통 테스트 Fixture 검토
6. Marketplace 확장 기반 준비

---

## Long-term Commitment

HYB는 한 번에 완성되는 단기 실험이 아니라
실제 사업 가능성을 단계적으로 검증하는 장기 프로젝트다.

기술적 완성도와 사업적 검증을 함께 추구하며,
잘못된 지름길보다 더 강하고 신뢰할 수 있는 경로를 선택한다.
