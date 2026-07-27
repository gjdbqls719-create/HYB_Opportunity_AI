# HYB Changelog


## Sprint 5.1 PR-5 — Discovery Factor Provider

### Added

- 기존 Discovery 분석값을 `OpportunityFactors`로 변환하는 `DiscoveryFactorPolicy`
- Factor 원천값별 명시적 0~100 정규화 정책
- 완전한 원천 데이터로 기본 Opportunity Intelligence 실행을 검증하는 통합 테스트 4개

### Changed

- Discovery Gateway metadata에 `trend_score_adjustment` 전달
- Adapter가 전체 누락 고정값 대신 실제 누락 Factor만 보고하도록 확장

## Sprint 5.1 PR-4 — Discovery Workflow Intelligence Integration

### Added

- Discovery Workflow의 선택적 Opportunity Intelligence 실행 단계
- Discovery 결과 순서를 보존하는 `intelligence_results` 응답 계약
- 항목 단위 Intelligence 실패 격리 테스트

### Changed

- Intelligence 실패가 Discovery 및 Publish 성공을 중단하지 않도록 Workflow 경계를 확장

버전별 변경 내용을 기록한다.

## Sprint 5.1 PR-1 — Architecture Alignment v1

- 최신 실제 코드 기준 계층 및 Dependency Boundary Audit 완료
- Discovery Workflow / Use Case / Gateway / Ranking 책임 확정
- Ranking Strategy 조기 도입 보류 결정
- Opportunity Dataset 조기 도입 보류 결정
- 기존 Opportunity Score/Decision과 Discovery의 통합 계약을 다음 우선순위로 확정
- 안정 영역과 기술 부채 우선순위(P1~P3) 문서화
- 런타임 및 공개 API 변경 없음
- 관련 Architecture 테스트 145개 통과
- 전체 테스트는 현재 실행 환경에서 Snapshot 상속 오류로 734 passed / 92 failed 확인

## 관리 항목

- 기능 추가
- 구조 변경
- 버그 수정
- 문서 변경

## Sprint 5.1 PR-2 — Opportunity Intelligence Integration Contract

- Discovery → Opportunity Factors Source Map 문서화
- confidence만 직접 재사용 가능함을 확정
- 불완전 Factor의 임의 0/50 대체 금지
- `unavailable` 결측 상태 정책 확정
- 기존 Recommendation과 신규 Evaluation 병행 운영 결정
- Application Service / Infrastructure Adapter 경계 확정
- ADR-0001 추가

## Sprint 5.1 PR-3 — Minimal Opportunity Intelligence Integration

- `OpportunityIntelligenceStatus` (`evaluated`, `unavailable`, `failed`) 추가
- Application 입력/결과 계약 및 Adapter Port 추가
- `OpportunityIntelligenceService`로 Score/Decision Engine 오케스트레이션 추가
- 기존 `DiscoveryResult`에서 confidence를 엄격하게 Decimal로 변환하는 Infrastructure Adapter 추가
- 5개 Factor가 준비되지 않은 현재 상태를 임의 기본값 없이 `unavailable`로 반환
- 완전한 Factor Adapter가 주입된 경우에만 신규 Score와 Evaluation 생성
- 기존 Recommendation 필드와 Discovery 공개 동작 변경 없음
- 신규 통합 테스트 6개 추가
