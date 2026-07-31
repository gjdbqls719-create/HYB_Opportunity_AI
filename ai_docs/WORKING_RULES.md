# WORKING RULES

Version 1.0

---

# 목적

이 문서는 AI가 실제 구현을 수행할 때 반드시 따라야 하는 작업 규칙을 정의한다.

PLAYBOOK이 사고방식을 정의한다면,

WORKING_RULES는 실제 행동을 정의한다.

---

# RULE 1

항상 먼저 읽는다.

구현 전에

- 관련 문서
- 관련 코드
- 관련 테스트

를 먼저 읽는다.

읽지 않고 구현하지 않는다.

---

# RULE 2

기존 패턴을 우선한다.

이미 존재하는

- UseCase
- Repository
- Service
- Entity
- Value Object

패턴을 우선 사용한다.

---

# RULE 3

Architecture를 존중한다.

Layer를 건너뛰지 않는다.

Dependency 방향을 변경하지 않는다.

Domain에서 Infrastructure를 참조하지 않는다.

---

# RULE 4

최소 변경 원칙

필요한 부분만 수정한다.

불필요한 리팩토링을 하지 않는다.

관련 없는 코드 수정 금지.

---

# RULE 5

Naming 유지

프로젝트의 Naming Convention을 따른다.

새로운 약어를 만들지 않는다.

기존 용어를 변경하지 않는다.

---

# RULE 6

파일 추가 기준

새 파일은

기존 구조로 해결할 수 없을 때만 만든다.

먼저 확장을 검토한다.

---

# RULE 7

함수 작성

하나의 함수는

하나의 책임만 가진다.

가능하면 짧게 유지한다.

---

# RULE 8

클래스 작성

클래스는

명확한 책임을 가진다.

God Object를 만들지 않는다.

---

# RULE 9

중복 제거

같은 코드가 2번 이상 등장하면

공통화 가능성을 검토한다.

단,

과도한 추상화는 금지한다.

---

# RULE 10

Exception

예외는 숨기지 않는다.

의미 있는 메시지를 사용한다.

빈 except를 사용하지 않는다.

---

# RULE 11

Logging

필요한 로그만 남긴다.

Debug 출력은 제거한다.

print()를 남기지 않는다.

---

# RULE 12

Test

새 기능은 테스트를 가진다.

버그 수정은

재현 테스트를 먼저 생각한다.

---

# RULE 13

Documentation

동작이 바뀌면

문서도 수정한다.

문서를 나중으로 미루지 않는다.

---

# RULE 14

Self Review

PR 전에

스스로 리뷰한다.

코드를 처음 보는 사람 입장에서 읽는다.

---

# RULE 15

Commit Ready

다음을 모두 만족해야 한다.

- 구현 완료

- 테스트 통과

- 문서 업데이트

- Debug 제거

- Import 정리

- 리뷰 가능

이후에만 PR을 생성한다.

---

END