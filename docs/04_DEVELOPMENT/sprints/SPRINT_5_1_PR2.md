# Sprint 5.1 PR-2 — Opportunity Intelligence Integration Contract

## 목표

Discovery 결과와 신규 Opportunity Score/Decision Engine 사이의 공식 통합
계약을 코드 구현 전에 확정한다.

## 작업 성격

- 문서 전용 PR
- 런타임 동작 변경 없음
- 공개 API 변경 없음
- 기존 Recommendation 제거 없음

## 실제 코드 분석 결과

- `DiscoveryResult.opportunity_score`는 기존 aggregate float 점수다.
- `OpportunityFactors`는 의미가 분리된 5개의 0~100 Decimal 점수를 요구한다.
- 현재 직접 재사용 가능한 값은 `confidence_score`뿐이다.
- Trend adjustment, competitor count, risk 문자열, ROI/순이익은 별도 정규화
  정책 없이 Factor로 사용할 수 없다.

## 핵심 결정

1. Factor가 하나라도 없으면 신규 Score를 생성하지 않는다.
2. 결측값에 임의의 0/50 기본값을 넣지 않는다.
3. Application Service가 준비 상태와 오케스트레이션을 담당한다.
4. Infrastructure Adapter가 기존 결과에서 원시 Source를 추출한다.
5. 기존 Recommendation은 Source of Truth로 유지한다.
6. 신규 Evaluation은 병행 결과로 제공한다.
7. 계산 불가능은 예외가 아니라 `unavailable` 상태로 표현한다.

## 변경 파일

- `docs/02_ARCHITECTURE/OPPORTUNITY_INTELLIGENCE_INTEGRATION_CONTRACT.md`
- `docs/02_ARCHITECTURE/ARCHITECTURE_INDEX.md`
- `docs/13_ADR/ADR-0001-opportunity-intelligence-integration-boundary.md`
- `docs/04_DEVELOPMENT/CHANGELOG.md`
- `docs/04_DEVELOPMENT/sprints/SPRINT_5_1_PR2.md`

## 완료 기준

- Source Map 작성
- 필수/선택 및 결측 정책 확정
- 기존 Recommendation과 신규 Decision 공존 정책 확정
- Application/Infrastructure 책임 경계 확정
- PR-3 최소 구현 범위 확정

## 다음 PR

Sprint 5.1 PR-3 — Minimal Opportunity Intelligence Integration

예정 범위:

- Application 상태/결과 모델
- Factor Input Adapter Port
- 기존 DiscoveryResult Adapter
- confidence 엄격 변환
- missing factor 보고
- 완전한 Provider가 있을 때만 Score + Evaluation 실행
- 기존 Discovery 공개 동작 유지
