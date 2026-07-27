# Sprint 4.6 PR-2 — Opportunity Domain Models

## 목적

Opportunity Score V2가 사용할 최소 불변 도메인 계약을 정의한다.
이번 PR은 계산 정책과 엔진을 포함하지 않으며, 데이터 구조와 유효성
경계만 확정한다.

## 추가된 공개 API

- `OpportunityGrade`
- `OpportunityFactors`
- `OpportunityScore`

## 설계 결정

- 금액 및 점수 계산의 일관성을 위해 모든 점수는 `Decimal`을 사용한다.
- 모든 점수 범위는 `0` 이상 `100` 이하로 제한한다.
- `NaN`과 `Infinity`는 도메인 결과로 허용하지 않는다.
- 결과 객체는 `frozen=True`, `slots=True`로 만들어 생성 후 변경할 수 없다.
- `generated_at`은 시간대가 포함된 `datetime`만 허용한다.
- `risk_score`는 위험량이 아니라 **위험 안전성 점수**다. 값이 높을수록
  더 안전하고 기회 점수에 긍정적이다.
- 등급 산정, 가중치, 최종 점수 계산은 후속 PR의 정책 및 엔진 책임으로 남긴다.

## 변경 파일

- `app/domain/opportunity/__init__.py`
- `app/domain/opportunity/models.py`
- `tests/test_opportunity_domain.py`
- `docs/04_DEVELOPMENT/sprints/SPRINT_4_6_PR2.md`

## 테스트 범위

- Enum 공개 값
- 정상 객체 생성
- 불변성
- Decimal 타입 계약
- 0~100 범위 및 경계값
- 유한값 검증
- 중첩 도메인 타입 검증
- timezone-aware 생성 시각 검증

## 후속 작업

Sprint 4.6 PR-3에서 가중치와 등급 임계값을 담당하는 정책 객체를 설계한다.
