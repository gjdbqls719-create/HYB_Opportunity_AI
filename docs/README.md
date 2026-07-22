# HYB Opportunity AI Documentation

이 문서는 HYB Opportunity AI의 문서 탐색 인덱스다.

현재 상태를 빠르게 이해하려면 모든 문서를 처음부터 읽기보다 아래 **핵심 문서 순서**를 따른다.

---

## 1. 새 채팅 및 새 개발 환경에서 읽는 순서

1. [`AI_CHARTER.md`](AI_CHARTER.md) — AI 협업 철학과 역할
2. [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — 현재 프로젝트 상태의 단일 기준
3. [`DEV_LOG.md`](DEV_LOG.md) — 실제 기술 작업과 테스트 기록
4. [`HYB_Development_Journal.md`](HYB_Development_Journal.md) — 프로젝트 역사, 방향 전환, 배운 점
5. [`00_PROJECT_NORTH_STAR.md`](00_PROJECT_NORTH_STAR.md) — 변하지 않는 장기 비전
6. 필요한 상세 설계 문서

---

## 2. 핵심 운영 문서

| 문서 | 역할 | 갱신 시점 |
|---|---|---|
| `AI_CHARTER.md` | 협업 철학, AI 역할, 변경 금지 원칙 | 철학이 실제로 바뀔 때만 |
| `PROJECT_CONTEXT.md` | 현재 버전, 구현 상태, 다음 작업 | 주요 기능·마일스톤 완료 후 |
| `DEV_LOG.md` | 수정 파일, 테스트, 문제와 해결 과정 | 개발 세션 또는 Audit 종료 시 |
| `HYB_Development_Journal.md` | 프로젝트 역사와 의사결정 이야기 | 중요한 방향 전환·마일스톤 후 |
| `README.md` | 문서 인덱스 | 문서 추가·이동·역할 변경 시 |

`PROJECT_CONTEXT.md`를 현재 상태의 단일 기준으로 사용한다. 다른 상태 문서와 충돌하면 최신 코드·테스트·Git 기록을 확인한 뒤 `PROJECT_CONTEXT.md`를 갱신한다.

---

## 3. 프로젝트 방향과 현재 상태

| 문서 | 내용 |
|---|---|
| [`00_PROJECT_NORTH_STAR.md`](00_PROJECT_NORTH_STAR.md) | 최종 목표와 비협상 원칙 |
| [`01_MASTER_CONTEXT.md`](01_MASTER_CONTEXT.md) | 제품 정의, 시장, 처리 파이프라인 |
| [`02_PROJECT_STATUS.md`](02_PROJECT_STATUS.md) | 2026-07-21 기준 상태 기록. 최신 상태는 `PROJECT_CONTEXT.md` 우선 |
| [`06_ROADMAP.md`](06_ROADMAP.md) | 장기 개발 단계와 우선순위 |
| [`20_FUTURE_IDEAS.md`](20_FUTURE_IDEAS.md) | 향후 아이디어 저장소 |

---

## 4. 아키텍처와 모듈

| 문서 | 내용 | 상태 |
|---|---|---|
| [`03_ARCHITECTURE.md`](03_ARCHITECTURE.md) | 모듈식 파이프라인 아키텍처 | 유지 |
| [`04_SYSTEM_FLOW.md`](04_SYSTEM_FLOW.md) | 현재 및 미래 처리 흐름 | 유지 |
| [`05_MODULE_REFERENCE.md`](05_MODULE_REFERENCE.md) | 모듈별 책임 규칙 | 일부 미래 폴더 포함 |
| [`12_MARKETPLACE_INTERFACE.md`](12_MARKETPLACE_INTERFACE.md) | Marketplace 연동 계약과 경계 | 유지 |

---

## 5. 개발·운영 기준

| 문서 | 내용 | 상태 |
|---|---|---|
| [`13_CODING_STANDARD.md`](13_CODING_STANDARD.md) | Python 코딩 기준 | 유지 |
| [`14_TESTING_GUIDE.md`](14_TESTING_GUIDE.md) | 테스트 원칙과 미래 테스트 구조 | 현재 실제 구조와 일부 차이 있음 |
| [`15_DEPLOYMENT.md`](15_DEPLOYMENT.md) | 미래 배포 기준 | 아직 배포 인프라 미구현 |
| [`16_SECURITY.md`](16_SECURITY.md) | Secret 및 보안 원칙 | 유지 |
| [`17_ENVIRONMENT.md`](17_ENVIRONMENT.md) | 개발 환경 구성 | 일부 도구는 아직 requirements에 없음 |
| [`18_TROUBLESHOOTING.md`](18_TROUBLESHOOTING.md) | 문제 해결 기록 | 지속 갱신 |
| [`19_RELEASE_CHECKLIST.md`](19_RELEASE_CHECKLIST.md) | 미래 Release 체크리스트 | 현재 도구 도입 상태 확인 필요 |

---

## 6. 변경·인수인계 기록

| 문서 | 내용 |
|---|---|
| [`07_CHANGELOG.md`](07_CHANGELOG.md) | 버전 단위 변경 기록 형식 |
| [`08_HANDOVER.md`](08_HANDOVER.md) | 다른 컴퓨터와 새 환경 인수인계 |
| [`HYB_AUDIT_REPORT_2026-07-23.md`](HYB_AUDIT_REPORT_2026-07-23.md) | Project Audit v1 결과 |

---

## 7. 현재 파일명과 내용이 일치하지 않는 문서

아래 문서는 내용 유실을 막기 위해 이번 Audit에서 삭제하거나 이름을 바꾸지 않았다.

| 현재 파일명 | 실제 주요 내용 | 권장 처리 |
|---|---|---|
| `09_DATABASE_SCHEMA.md` | 코드 기준 전체 아키텍처 도식 | 실제 DB Schema 작성 후 분리 또는 이름 변경 검토 |
| `10_API_SPEC.md` | 1차 코드 리뷰 보고서 | API 구현 시 실제 API Spec으로 교체하고 기존 내용은 Review 문서로 이동 검토 |
| `11_AI_ENGINE_SPEC.md` | v0.5 CLI·SQLite 기능 사용법 | 실제 AI Engine Spec 작성 후 기존 내용은 Release/Usage 문서로 이동 검토 |

이 작업은 별도의 문서 정리 세션에서 한 문서씩 수행한다.

---

## 8. 문서 관리 원칙

- 현재 구현과 미래 계획을 명확히 구분한다.
- 완료하지 않은 기능을 완료된 것처럼 기록하지 않는다.
- 코드·테스트·문서가 충돌하면 실제 코드와 테스트를 우선 확인한다.
- 문서를 삭제하거나 이름을 바꾸기 전에 링크와 참조를 검색한다.
- 큰 기능이 끝나면 `PROJECT_CONTEXT`, `DEV_LOG`, 필요 시 Development Journal을 갱신한다.
- 새 문서를 만들기 전에 기존 문서와 역할이 겹치는지 확인한다.
