# DECISION TREE

Version 1.0

---

# 목적

이 문서는 AI가 구현을 시작하기 전에 올바른 의사결정을 내리기 위한 사고 절차를 정의한다.

문제를 발견했다고 바로 구현하지 않는다.

항상 아래 Decision Tree를 따른다.

---

# STEP 1

## 요구사항을 이해했는가?

YES

↓

STEP 2

NO

↓

관련 문서 읽기

↓

질문

↓

구현 중지

---

# STEP 2

관련 기능이 존재하는가?

YES

↓

기존 구현 분석

↓

확장 가능 여부 확인

NO

↓

새 구현 검토

---

# STEP 3

기존 클래스를 확장 가능한가?

YES

↓

확장

↓

끝

NO

↓

STEP 4

---

# STEP 4

새 클래스가 필요한가?

YES

↓

책임이 명확한가?

↓

YES

↓

생성

NO

↓

기존 구조 개선

---

# STEP 5

새 Directory가 필요한가?

거의 아니다.

새 Directory를 만들기 전에

기존 구조를 최소 2회 검토한다.

---

# STEP 6

Architecture를 변경하는가?

YES

↓

중지

↓

ADR 또는 설계 검토 필요

NO

↓

계속

---

# STEP 7

Domain 변경인가?

YES

↓

Domain 규칙 확인

↓

Value Object 확인

↓

Entity 확인

↓

Service 확인

↓

구현

NO

↓

STEP 8

---

# STEP 8

Application 변경인가?

YES

↓

UseCase 확인

↓

Port 확인

↓

Workflow 확인

↓

구현

NO

↓

STEP 9

---

# STEP 9

Infrastructure 변경인가?

YES

↓

Adapter 확인

↓

Repository 확인

↓

External API 영향 확인

↓

구현

NO

↓

STEP 10

---

# STEP 10

테스트가 존재하는가?

YES

↓

읽는다.

↓

영향 범위 분석

↓

수정

NO

↓

새 테스트 작성

---

# STEP 11

문서를 수정해야 하는가?

YES

↓

관련 문서 수정

↓

README 영향 확인

↓

Architecture 영향 확인

NO

↓

STEP 12

---

# STEP 12

최종 점검

□ 기존 기능 유지

□ 테스트 통과

□ 문서 동기화

□ Debug 제거

□ 리뷰 가능

↓

PR 생성

---

# AI Decision Principles

항상

Reuse

↓

Extend

↓

Create

↓

Refactor

순서로 판단한다.

절대로

Create

↓

Reuse

순서로 생각하지 않는다.

---

# STOP Conditions

다음 상황에서는 구현을 중단한다.

- Architecture 변경 필요

- 요구사항 불명확

- Domain 충돌

- 기존 구현 이해 실패

- 테스트 의도 파악 실패

이 경우

추측 구현하지 않는다.

---

END