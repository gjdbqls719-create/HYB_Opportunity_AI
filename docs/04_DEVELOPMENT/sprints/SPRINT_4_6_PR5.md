# Sprint 4.6 PR-5 — Opportunity Decision Engine

## 목표

PR-4에서 확정한 `OpportunityEvaluation` 도메인을 실제로 생성하는 정책 기반
Decision Engine을 구현한다. `OpportunityScore`의 공개 API는 변경하지 않는다.

## 설계 결정

- `OpportunityDecisionEngine`은 `OpportunityScore`를 입력받는다.
- 총점 구간으로 `STRONG_BUY`, `BUY`, `WATCH`, `SKIP`을 판정한다.
- 요소 점수는 긍정·부정 경계와 비교해 구조화된 `OpportunityReason`으로 변환한다.
- 이유의 순서는 가격 → 추세 → 수요 → 경쟁 → 위험으로 고정한다.
- 중립 구간의 요소는 이유에서 제외한다.
- 모든 요소가 중립이면 `BALANCED_FACTORS`를 사용해 Evaluation의 근거 최소 1개 계약을 지킨다.
- Confidence는 이번 PR에서 의사결정을 강제 조정하지 않는다. 미측정 기본값 0과 실제 저신뢰를 아직 구분하지 못하기 때문이다.
- 국가·Marketplace·Category별 기준은 `OpportunityDecisionPolicy` 교체로 확장한다.

## 기본 정책

### Decision

- 90 이상: `STRONG_BUY`
- 75 이상: `BUY`
- 60 이상: `WATCH`
- 그 미만: `SKIP`

### Reason

- 요소 점수 70 이상: 긍정 근거
- 요소 점수 30 이하: 부정 근거
- 30 초과 70 미만: 중립으로 생략

`competition_score`와 `risk_score`는 값이 높을수록 각각 경쟁 환경과 위험
안전성이 유리하다는 기존 Opportunity Domain 의미를 따른다.

## 변경 파일

- `app/engine/opportunity_decision.py`
- `app/engine/__init__.py`
- `app/domain/opportunity/reasons.py`
- `tests/test_opportunity_decision_engine.py`
- `docs/04_DEVELOPMENT/sprints/SPRINT_4_6_PR5.md`

## 범위 제외

- Confidence 기반 Decision downgrade
- 사용자용 자연어 문장 생성 및 현지화
- Marketplace·Category 정책 선택기
- 알림과 자동 구매 후보 연결
- Score Engine과 Decision Engine의 단일 orchestration API
