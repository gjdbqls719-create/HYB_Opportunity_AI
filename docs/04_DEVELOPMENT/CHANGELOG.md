# HYB Changelog

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
