# HYB Changelog

이 문서는 버전 및 Sprint별 주요 변경사항을 기록한다.

---

## Sprint 7 PR-3 — Documentation Quality Audit

### Added

- `docs/11_AUDIT/HYB_DOCUMENTATION_AUDIT_2026-07-28.md`
- `docs/04_DEVELOPMENT/sprints/SPRINT_6_SUMMARY.md`
- 실제 문서 구조를 반영한 Documentation Inventory 및 Cross-reference 감사 결과

### Changed

- `PROJECT_STATUS.md`에 문서 상태, 감사 근거, 마지막 확인 테스트 기준을 명시
- `SPRINT_HISTORY.md`를 Sprint 6 완료 및 Sprint 7 진행 상태까지 최신화
- `DOCUMENT_INDEX.md`를 실제 파일 링크 중심의 탐색 문서로 확장
- `DOCUMENT_POLICY.md`에 문서 책임, 검증, 테스트 기록 및 Deliverable 규칙을 추가
- CHANGELOG와 Sprint 상세 문서의 연결 규칙을 명시

### Validation

- `docs/` Markdown 문서 78개 UTF-8 읽기 확인
- 검사 가능한 Markdown 상대 링크 기준 깨진 링크 0개
- 코드 테스트는 재실행하지 않음
- 마지막 확인 전체 회귀 테스트 기준: **853 passed**

---

## Sprint 7 PR-2 — Development Documentation Recovery

### Changed

- 깨진 한글 인코딩이 포함된 개발 문서를 UTF-8 기준으로 복구
- `CHANGELOG.md`, `DEV_LOG.md`, `DEVELOPMENT_JOURNAL.md`의 역할과 기록 형식을 정리
- Sprint 6 완료 상태와 853개 전체 회귀 테스트 통과 결과를 문서에 반영
- 문서별 책임 중복을 줄이기 위한 Documentation Architecture 원칙을 적용

### Notes

- 후속 실제 저장소 Audit에서 `docs/04_DEVELOPMENT/sprints/SPRINT_HISTORY.md`가 존재함을 확인했다.
- PR-2의 경로 확인 메모는 PR-3에서 정정하고 Sprint History를 최신화했다.

---

## Sprint 6 — Explainable Decision Pipeline

### Added

- Market Adjustment 결과 설명
- Decision Report와 Market Adjustment 연결
- AI Partner의 Decision Report 기반 시장 설명 사용
- Dashboard Decision Timeline
- Decision Report 전용 테스트

### Changed

- Engine, Presentation, Formatter 사이의 책임을 분리한 상태로 설명 데이터 전달 경로 강화
- 분석 결과를 단순 점수에서 판단 근거가 포함된 의사결정 정보로 확장

### Validation

- 전체 회귀 테스트: **853 passed**
- Sprint 6 변경사항 Commit 및 Push 완료

---

## Sprint 5.2 PR-1 — Profitability Score Extension Point

### Added

- ROI 기반 가격 Factor 계산을 `profitability_score()` 진입점으로 명시
- 향후 `margin_rate`, `landed_cost_roi` 등 검증된 수익성 지표로 확장할 수 있는 경계 마련
- Decimal 입력 및 유효 범위 검증 테스트 추가
- 정상 반환 및 경계 검증 테스트 4개 추가

### Changed

- 기존 `price_score()` 공개 호출은 하위 호환을 위한 위임 메서드로 유지
- 기존 ROI 점수 구간과 결과를 유지하여 기존 추천 결과에 미치는 영향 방지

---

## Sprint 5.1 PR-5 — Discovery Factor Provider

### Added

- 기존 Discovery 분석값을 `OpportunityFactors`로 변환하는 `DiscoveryFactorPolicy`
- Factor 원천값별 0~100 정규화 정책
- 실제 원천 데이터로 기본 Opportunity Intelligence 실행을 검증하는 통합 테스트 4개

### Changed

- Discovery Gateway metadata에 `trend_score_adjustment` 전달
- Adapter가 전체 가격 고정값이 아닌 실제 가격 Factor를 사용하도록 확장

---

## Sprint 5.1 PR-4 — Discovery Workflow Intelligence Integration

### Added

- Discovery Workflow에 선택적 Opportunity Intelligence 실행 단계
- Discovery 결과 순서를 유지하는 `intelligence_results` 응답 계약
- 항목 단위 Intelligence 실패 격리 테스트

### Changed

- Intelligence 실패가 Discovery 및 Publish 성공을 중단하지 않도록 Workflow 경계를 확장

---

## Sprint 5.1 PR-3 — Minimal Opportunity Intelligence Integration

### Added

- `OpportunityIntelligenceStatus`
  - `evaluated`
  - `unavailable`
  - `failed`
- Application 입력·결과 계약과 Adapter Port
- `OpportunityIntelligenceService`
- Infrastructure Adapter
- 신규 통합 테스트 6개

### Changed

- 기존 `DiscoveryResult`의 confidence 값을 Decimal로 변환
- 5개 Factor가 준비되지 않은 상태는 임의 기본값 없이 `unavailable`로 반환
- 완전한 Factor Adapter가 주입된 경우에만 신규 Score와 Evaluation 생성
- 기존 Recommendation 필드와 Discovery 공개 동작은 유지

---

## Sprint 5.1 PR-2 — Opportunity Intelligence Integration Contract

### Added

- Discovery → Opportunity Factors Source Map 문서
- `unavailable` 결과 상태 정책
- Application Service와 Infrastructure Adapter 경계
- ADR-0001

### Decisions

- confidence만 직접 사용할 수 있는 값으로 확정
- 불완전한 Factor에 임의의 0 또는 50을 채우지 않음
- 기존 Recommendation과 신규 Evaluation을 일정 기간 병행 운영

---

## Sprint 5.1 PR-1 — Architecture Alignment v1

### Changed

- 최신 실제 코드 기준 결합도 및 Dependency Boundary Audit 완료
- Discovery Workflow, Use Case, Gateway, Ranking 책임 정리
- Ranking Strategy 조기 도입 보류
- Opportunity Dataset 조기 도입 보류
- 기존 Opportunity Score 및 Decision과 Discovery의 통합 계약을 우선순위로 확정
- 안정 영역과 기술 부채 우선순위 P1~P3 문서화
- 공개 API 변경 없이 아키텍처 정렬 수행

### Validation

- 관련 Architecture 테스트 145개 통과
- 당시 전체 테스트 실행에서 Snapshot 계열 오류가 별도로 확인됨
