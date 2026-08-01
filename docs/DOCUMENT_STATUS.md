# HYB Documentation Status

**Last Updated:** 2026-07-29  
**Status Basis:** Sprint 8 PR3-B2 repository snapshot

## Purpose

이 문서는 HYB 문서 체계의 현재 신뢰도와 최신화 상태를 빠르게 확인하기 위한 문서입니다.
각 문서의 상세 내용 자체보다 “어떤 문서가 현재 기준이며 무엇을 갱신해야 하는가”를 관리합니다.

## Current Documentation Baseline

- Official documentation root: `docs/`
- Official structure: 기존 번호 기반 디렉터리 구조 유지
- Encoding: UTF-8
- Architecture baseline: Sprint 4.4
- Current development baseline: Sprint 8 PR3-B2 completed
- Latest full regression: **1053 passed**

## Current-State Documents

| Document | Path | Status | Update Trigger |
|---|---|---|---|
| Project Status | `docs/01_CONTEXT/PROJECT_STATUS.md` | Current | Sprint/PR 상태 또는 회귀 테스트 기준 변경 |
| Project Context | `docs/01_CONTEXT/PROJECT_CONTEXT.md` | Current | 새 채팅 인수인계 정보 또는 개발 규칙 변경 |
| Document Status | `docs/DOCUMENT_STATUS.md` | Current | 문서 추가·이동·감사 결과 변경 |
| Roadmap | `docs/07_ROADMAP/ROADMAP.md` | Current | 우선순위 또는 Sprint 계획 변경 |
| Changelog | `docs/04_DEVELOPMENT/CHANGELOG.md` | Current | 기능 PR 또는 문서 Pack 완료 |
| AI Development Log | `docs/04_DEVELOPMENT/AI_DEVELOPMENT_LOG.md` | Current | AI와 수행한 주요 설계·구현 결정 발생 |

## Stable Foundation Documents

다음 문서는 프로젝트 목적과 장기 원칙을 담고 있으므로,
단기 Sprint 상태 변경만으로 수정하지 않습니다.

- `docs/00_FOUNDATION/`
- `docs/03_ENGINEERING/DEVELOPMENT_PRINCIPLES.md`
- Core architecture documents under `docs/02_ARCHITECTURE/`
- ADR records

수정 시에는 목적, 책임, 장기 영향과 함께 검토해야 합니다.

## Documentation Update Rules

### Every PR

- `CHANGELOG.md`
- 관련 Sprint 기록
- 필요 시 `AI_DEVELOPMENT_LOG.md`

### Current State Change

- `PROJECT_STATUS.md`
- `PROJECT_CONTEXT.md`
- `ROADMAP.md`

### Major Architecture or Engineering Practice Change

- Architecture documents
- ADR
- `DEVELOPMENT_PRINCIPLES.md`
- Tests and examples

### Sprint Completion

- Sprint summary/history
- Project status
- Roadmap
- Changelog
- AI development log
- Release notes when applicable

## Known Documentation Debt

- Sprint 8 세부 PR 기록 문서가 아직 `docs/04_DEVELOPMENT/sprints/`에 충분히 축적되지 않음
- 기존 `DEV_LOG.md`와 신규 `AI_DEVELOPMENT_LOG.md`의 역할 경계를 지속적으로 유지해야 함
- `DOCUMENT_INDEX.md`에 신규 `DOCUMENT_STATUS.md`와 `AI_DEVELOPMENT_LOG.md` 링크를 추가해야 함
- WatchList 및 Marketplace Lookup 아키텍처 문서가 구현 완료 범위에 맞춰 후속 최신화되어야 함

## Role Separation

- `DEV_LOG.md`: 실제 기술 작업과 검증 결과의 상세 시간순 기록
- `DEVELOPMENT_JOURNAL.md`: 프로젝트 여정과 학습, 방향성 기록
- `AI_DEVELOPMENT_LOG.md`: AI Partner와 함께 내린 주요 설계 판단과 협업 연속성 기록
- `CHANGELOG.md`: 사용 가능한 변경 결과를 Sprint/PR 단위로 요약
- `PROJECT_STATUS.md`: 지금 현재의 단일 스냅샷
- `PROJECT_CONTEXT.md`: 새 AI/개발자가 빠르게 이어가기 위한 압축 맥락

## Validation Policy

문서에 테스트 결과를 기록할 때는 다음을 구분합니다.

- 이번 변경에서 실제로 실행한 테스트
- 이전 문서에서 인용한 마지막 확인 테스트
- 예상 테스트 수

실행하지 않은 테스트는 통과했다고 기록하지 않습니다.

Last Updated

Sprint 13

Added

Verified Economics Domain
Production Safety Documentation