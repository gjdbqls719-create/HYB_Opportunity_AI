# Sprint 4.6 PR-4 — Opportunity Evaluation Domain

## 목표

Opportunity Score의 공개 API를 변경하지 않고, 점수 이후의 최종 판단과
구조화된 설명 근거를 표현하는 Evaluation 도메인을 추가한다.

## 설계 결정

- `OpportunityScore`는 계산된 분석 결과만 책임진다.
- `OpportunityEvaluation`은 `OpportunityScore`를 참조하며 최종 판단을 책임진다.
- 의사결정은 `OpportunityDecision`의 안정적인 문자열 Enum으로 표현한다.
- 근거는 `OpportunityReason` 코드로 저장하고 사용자용 문구와 현지화는 상위 계층에서 처리한다.
- 근거는 최소 1개가 필요하며 중복을 허용하지 않는다.
- 모든 도메인 모델은 불변 객체와 timezone-aware datetime 원칙을 유지한다.

## 변경 파일

- `app/domain/opportunity/decision.py`
- `app/domain/opportunity/reasons.py`
- `app/domain/opportunity/evaluation.py`
- `app/domain/opportunity/__init__.py`
- `tests/test_opportunity_evaluation.py`
- `docs/04_DEVELOPMENT/sprints/SPRINT_4_6_PR4.md`

## 범위 제외

- 점수에서 Decision을 자동 산출하는 정책 엔진
- Reason 자동 선택 로직
- 사용자용 자연어 설명 생성
- 알림 및 자동 구매 후보 연결

위 기능은 Evaluation 도메인이 안정화된 뒤 후속 PR에서 구현한다.
