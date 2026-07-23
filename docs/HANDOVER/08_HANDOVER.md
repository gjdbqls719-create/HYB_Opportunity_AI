# HYB Opportunity AI
## PROJECT HANDOVER

Version: 1.0

---

# 목적

이 문서는 다른 컴퓨터 또는 새로운 개발 환경에서
HYB Opportunity AI 프로젝트를 이어받기 위한 인수인계 문서이다.

---

# 프로젝트 목표

HYB Opportunity AI는

AI가 글로벌 온라인 마켓을 분석하여

사람보다 먼저
수익 기회를 발견하는 플랫폼이다.

모든 개발은 이 목표를 기준으로 진행한다.

---

# 개발 순서

1.

Foundation

↓

2.

AI Engine

↓

3.

Marketplace

↓

4.

Automation

↓

5.

API

↓

6.

Dashboard

↓

7.

Mobile

이 순서를 변경하지 않는다.

---

# 새 PC에서 시작

1.

Git Clone

```
git clone <repository>
```

2.

가상환경 생성

```
python -m venv .venv
```

3.

가상환경 활성화

Windows

```
.venv\Scripts\activate
```

Linux / macOS

```
source .venv/bin/activate
```

4.

패키지 설치

```
pip install -r requirements.txt
```

5.

환경 변수 설정

.env 생성

필요한 API Key 입력

6.

테스트 실행

```
pytest
```

모든 테스트가 통과하면 개발을 시작한다.

---

# 개발 시작 전 체크리스트

□ PROJECT_NORTH_STAR 읽기

□ MASTER_CONTEXT 읽기

□ PROJECT_STATUS 확인

□ ROADMAP 확인

□ CHANGELOG 확인

---

# 개발 원칙

기능을 만들기 전에

이 기능이

최종 목표에 기여하는지 확인한다.

Engine을 우선한다.

UI는 마지막이다.

---

# Git Workflow

개발

↓

Test

↓

Commit

↓

Push

↓

Pull Request (필요 시)

↓

Merge

---

# 절대 변경하지 말 것

Architecture Layer

Module Responsibility

Flow Direction

AI First Philosophy

---

# 최종 목표

이 프로젝트는

가격 비교 프로그램이 아니다.

AI 기반 Opportunity Intelligence Platform이다.

모든 개발자는
이 목표를 기준으로 의사결정을 내린다.

---

# 마지막 메시지

이 문서를 읽는 개발자는

기존 프로젝트의 방향을 유지하면서
더 나은 AI를 만드는 데 집중한다.

새로운 기능은 자유롭게 추가할 수 있지만

프로젝트의 철학은 바꾸지 않는다.