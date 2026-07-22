# HYB Opportunity AI — Project Context

> Last Updated: 2026-07-23  
> Version: v0.2.0 (Development)  
> Purpose: 새 채팅이나 새 개발 환경에서 현재 프로젝트 상태를 빠르게 파악하기 위한 단일 기준 문서

---

## 1. 프로젝트 개요

### 프로젝트명

HYB Opportunity AI

### 목표

온라인 마켓플레이스의 상품 데이터를 수집·정규화·비교하고, 가격·추세·신뢰도·수익성·위험 신호를 분석하여 AI가 높은 가능성의 상품 기회(Opportunity)를 먼저 발견하고 설명 가능한 형태로 추천하는 플랫폼을 만든다.

### 최종 비전

> AI가 사용자가 직접 찾기 전에 수익 가능성이 있는 상품 기회를 발견한다.

단순 가격 비교 도구가 아니라 **AI 기반 Opportunity Discovery Platform**을 목표로 한다.

---

## 2. 현재 프로젝트 상태

Foundation 단계와 핵심 분석 파이프라인의 1차 구현이 완료되어 있다.

현재 확인된 구성:

- 공통 Product 모델
- eBay 연동 경로
- Amazon 테스트·가짜 데이터 경로
- 상품 유사도 비교
- Price Intelligence
- Price History
- Price Trend
- Trend Scoring
- Confidence Scoring
- Opportunity 계산
- Explainable Score
- Recommendation
- Decision Report
- Score Formatter
- Market Analyzer
- Orchestrator
- SQLite 기반 기록 저장
- CLI 및 점검 스크립트
- pytest 자동 테스트

2026-07-23 Audit 환경에서 확인한 테스트 결과:

```text
98 passed in 0.68s
```

> 위 수치는 이번 Audit 복사본에서 실행한 결과다. 이후 코드가 변경되면 다시 갱신해야 한다.

---

## 3. 현재 아키텍처 흐름

```text
Marketplace Search / Collectors
        ↓
Normalized Product Model
        ↓
Product Matching
        ↓
Price Intelligence
        ↓
Confidence / Trend Analysis
        ↓
Opportunity Calculation
        ↓
Explainable Score
        ↓
Recommendation
        ↓
Decision Report
        ↓
Score Formatter / Market Analyzer
        ↓
CLI / Storage / Future API & Dashboard
```

### 핵심 원칙

- Marketplace별 코드는 수집과 변환을 담당한다.
- Engine은 Marketplace 원본 구조를 알지 않는다.
- 핵심 계산은 설명 가능하고 테스트 가능해야 한다.
- 하나의 Marketplace 오류가 전체 분석을 중단시키지 않아야 한다.
- Presentation 계층은 기존 분석 결과를 조합하며 핵심 비즈니스 로직을 새로 만들지 않는다.

---

## 4. 현재 작업 기준

이번 Audit에서는 기능 로직을 변경하지 않았다.

완료한 유지보수 작업:

- 실제 작업 프로젝트인 내부 Git 저장소를 기준 프로젝트로 확정
- `.venv`, `.pytest_cache`, `__pycache__`, 로컬 `.env`, 로컬 DB를 공유용 복사본에서 제외
- `.gitignore` 보강
- `docs/README.md` 문서 인덱스 개편
- `PROJECT_CONTEXT.md` 최신화
- `DEV_LOG.md` 생성
- Audit Report 생성
- 전체 테스트 실행

다음 기능 개발 후보:

1. AI Analyst 계층의 요구사항과 테스트 확정
2. `tests/test_ai_analyst.py` 작성
3. `engine/ai_analyst.py` 구현
4. Orchestrator 연결
5. 전체 pytest
6. Commit → Push

AI Analyst는 기존 Recommendation, DecisionReport, MarketAnalyzer, ExplainableScore 출력을 조합하는 계층으로 설계하며 핵심 계산 로직을 중복하지 않는다.

---

## 5. 개발 원칙

1. 안정성을 속도보다 우선한다.
2. 한 번에 하나의 기능만 개발한다.
3. 작업 단위는 가능한 작게 유지한다.
4. 기존 기능을 깨뜨릴 수 있는 변경은 영향 범위를 먼저 설명한다.
5. 코드를 추측해서 수정하지 않는다.
6. 수정 후 반드시 테스트한다.
7. 테스트 통과 후 다음 단계로 넘어간다.
8. 기능 완료 후 Commit → Push를 권장한다.
9. 승인하지 않은 대규모 리팩터링은 진행하지 않는다.
10. 기존 구조와 코드를 최대한 재사용한다.

---

## 6. 코드 제공 및 응답 원칙

사용자는 부분 패치보다 **교체 가능한 파일 전체 코드**를 선호한다.

개발 작업 응답 순서:

```text
작업 목표
↓
수정 이유
↓
영향받는 파일
↓
파일 전체 코드
↓
테스트 방법
↓
다음 작업
```

코딩 스타일:

- Python PEP 8 준수
- Type Hint 적극 사용
- 명확한 함수명과 변수명
- 불필요한 코드와 추상화 금지
- 금액 계산은 Decimal 정확성을 유지

---

## 7. 테스트 및 Git 규칙

- 모든 핵심 기능은 pytest 통과를 기준으로 한다.
- 새 기능에는 테스트를 함께 작성한다.
- 버그 수정은 가능하면 재현 테스트를 먼저 추가한다.
- 외부 API에 직접 의존하는 불안정한 테스트를 피한다.
- 기능 단위 Commit을 사용한다.

Commit prefix 예시:

```text
feat:
fix:
refactor:
test:
docs:
chore:
```

현재 원격 저장소:

```text
https://github.com/gjdbql5719-create/HYB_Opportunity_AI.git
```

---

## 8. 문서 기준

핵심 문서:

- `AI_CHARTER.md`: AI 협업 철학과 역할
- `PROJECT_CONTEXT.md`: 현재 상태의 단일 기준
- `DEV_LOG.md`: 실제 기술 작업 기록
- `HYB_Development_Journal.md`: 프로젝트 역사와 의사결정 이야기
- `README.md`: 전체 문서 탐색 인덱스

기존 번호 문서는 상세 설계와 장기 계획 자료로 유지한다. 다만 일부 문서는 파일명과 실제 내용이 일치하지 않으므로, 삭제하거나 즉시 이름을 바꾸지 않고 문서 인덱스에서 상태를 표시한다.

---

## 9. 새 채팅 인수인계 순서

새 채팅에서는 다음 순서로 확인한다.

1. `docs/AI_CHARTER.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/DEV_LOG.md`
4. `docs/HYB_Development_Journal.md`
5. 최신 Git 로그와 `git status`
6. 최신 pytest 결과
7. 현재 수정 중인 코드

확인 후 다음 다섯 항목을 먼저 정리한다.

- 현재 버전
- 마지막 완료 작업
- 현재 작업
- 테스트 상태
- 이번 세션의 핵심 목표 한 가지

---

## 10. 즉시 다음 작업

```text
AI Analyst 요구사항 확정
↓
tests/test_ai_analyst.py
↓
engine/ai_analyst.py
↓
Orchestrator 연결
↓
pytest
↓
Commit
↓
Push
```
