# HYB Documentation Policy

## Purpose

HYB 프로젝트 문서의 생성, 검토, 최신화, 배포 및 보존 규칙을 정의합니다.

---

## Core Rules

1. 각 문서는 하나의 명확한 책임을 가져야 합니다.
2. 실제 저장소, 코드, 테스트 또는 승인된 결정으로 확인되지 않은 내용을 사실처럼 기록하지 않습니다.
3. 중복 문서는 병합하거나 Archive로 이동하되, 역사 기록을 이유 없이 삭제하지 않습니다.
4. 주요 구조 변경은 관련 Architecture, Context, Development 문서에 함께 반영합니다.
5. 실행하지 않은 테스트를 통과했다고 기록하지 않습니다.
6. 마지막 확인 테스트 값과 현재 변경에서 새로 검증한 값을 구분합니다.
7. 문서 경로나 존재 여부는 실제 저장소 Inventory를 기준으로 확인합니다.
8. UTF-8을 공식 문서 인코딩으로 사용합니다.

---

## Source of Truth

상태별 공식 기준은 다음과 같습니다.

- 현재 프로젝트 상태: `docs/01_CONTEXT/PROJECT_STATUS.md`
- 전체 프로젝트 맥락: `docs/01_CONTEXT/PROJECT_CONTEXT.md`
- 시스템 설계: `docs/02_ARCHITECTURE/`
- 개발 규칙: `docs/03_ENGINEERING/`
- 변경 이력: `docs/04_DEVELOPMENT/CHANGELOG.md`
- 실제 작업 로그: `docs/04_DEVELOPMENT/DEV_LOG.md`
- 방향과 학습 기록: `docs/04_DEVELOPMENT/DEVELOPMENT_JOURNAL.md`
- Sprint 완료 요약: `docs/04_DEVELOPMENT/sprints/SPRINT_HISTORY.md`
- 공식 결정: `docs/13_ADR/`
- 감사 결과: `docs/11_AUDIT/`

---

## Responsibility Boundaries

### PROJECT_STATUS

현재 시점의 상태, 마지막 확인 테스트, 현재 Sprint와 다음 우선순위를 기록합니다.

### CHANGELOG

추가, 변경, 수정, 제거된 내용을 Sprint/PR 단위로 기록합니다.

### DEV_LOG

실제 수행한 작업, 변경 파일, 검증 결과, 문제 해결과 다음 작업을 기록합니다.

### DEVELOPMENT_JOURNAL

방향 전환, 중요한 판단의 이유, 프로젝트가 배운 내용을 기록합니다.

### SPRINT_HISTORY

Sprint별 완료 상태와 개별 Sprint 문서로 이동할 수 있는 링크를 제공합니다.

### ADR

장기적인 아키텍처 결정과 대안, 선택 이유, 결과를 기록합니다.

---

## Update Triggers

다음 상황에서는 관련 문서를 업데이트해야 합니다.

- Sprint 또는 PR 완료
- Public API 또는 계층 책임 변경
- 데이터 모델 또는 저장 방식 변경
- 테스트 기준 또는 품질 게이트 변경
- 배포·환경·보안 절차 변경
- 중요한 사업 방향 또는 제품 범위 변경
- 기존 문서와 실제 구현의 불일치 발견

---

## Validation Checklist

문서 변경 전후에 가능한 범위에서 다음을 확인합니다.

- [ ] 파일이 UTF-8로 정상 열리는가
- [ ] 내부 상대 링크가 실제 경로를 가리키는가
- [ ] 현재 상태와 역사 기록이 혼합되지 않았는가
- [ ] 완료되지 않은 작업을 완료로 쓰지 않았는가
- [ ] 테스트를 실행했는지 여부가 명시되어 있는가
- [ ] 마지막 확인 테스트 값의 출처가 분명한가
- [ ] 기존 기록을 불필요하게 삭제하지 않았는가
- [ ] DOCUMENT_INDEX에서 핵심 문서에 접근할 수 있는가

---

## Document-only PR Rule

문서만 변경하는 PR은 코드 테스트를 생략할 수 있습니다.

그 경우 다음을 명시해야 합니다.

- 코드 테스트를 재실행하지 않았음
- 마지막 확인 전체 테스트 기준
- 대신 수행한 문서 검증
  - 인코딩 검사
  - 링크 검사
  - 경로 및 Inventory 확인
  - Git 기록 확인

---

## Deliverable Rule

Sprint 또는 문서 PR Deliverable에는 최소한 다음을 포함합니다.

- 실제 변경 파일
- `README_UPDATE.md`
- `APPLY.md`
- `MANIFEST.md`

Deliverable은 기존 프로젝트 전체를 덮어쓰지 않고,
명시된 변경 파일만 적용할 수 있어야 합니다.

---

## Document Lifecycle

```text
Draft
↓
Review
↓
Approved
↓
Active
↓
Archived
```

Archive로 이동할 때는 대체 문서 또는 이동 이유를 남깁니다.
