# HYB AI Development Log

**Last Updated:** 2026-07-31

## Purpose

이 문서는 Product Owner와 AI Partner가 함께 내린
주요 설계 판단, 협업 방식, 개발 연속성을 기록합니다.

상세 구현 명세와 명령 로그는 `DEV_LOG.md`,
프로젝트 여정과 학습은 `DEVELOPMENT_JOURNAL.md`,
사용 가능한 변경 결과는 `CHANGELOG.md`에 기록합니다.

---

## 2026-07-31 — Sprint 11 Release Candidate

Sprint 11 PR5 validated the complete WatchList monitoring path without adding
new business behavior. A Production Composition E2E test exercises first,
changed, unchanged, retry, partial failure, conflict, recovery, and multi-item
processing against one isolated SQLite database.

The actual `--watch-monitor` CLI path was verified to resolve Production
Composition, execute the Monitor, update WatchItem state, append Price History,
and render the expected summary.

The architecture audit found no reverse Domain dependency, Infrastructure
dependency in the WatchList Application package, circular dependency, or
Domain rule violation. Full regression completed with `1160 passed` and the
existing FastAPI TestClient warning.

Sprint 11 is complete and the current focus moves to Sprint 12 planning.

---

## 2026-07-31 — Price Observation Idempotency

Sprint 11 PR4-B made `save_product_price()` idempotent for the observation
identity `(canonical_product_id, marketplace, item_id, observed_at)`.
Identical data returns the existing record ID; different data raises an
explicit conflict without changing history.

The repository uses `BEGIN IMMEDIATE` so separate SQLite repository instances
serialize the identity check and insert. This preserves existing schemas and
data while preventing duplicate inserts through this API. Direct SQL and other
write APIs remain outside this guarantee.

Price History and WatchItem writes remain non-atomic. If WatchItem persistence
fails after recording, retrying the same observation reuses the existing row
and proceeds to WatchItem save. ADR-0002 records this policy and its limits.

Validation completed with `34 passed` for Price History, `94 passed` for
WatchList, `30 passed` for Change Detection, `30 passed` for CLI, and
`1158 passed` for the full regression suite. The existing FastAPI TestClient
warning remains.

---

## 2026-07-31 — WatchList Price Observation Recording

Sprint 11 PR4-A connected successful WatchList Monitor observations to the
existing append-only Price History through a narrow Application port and an
Infrastructure adapter.

```text
Marketplace lookup
→ current PriceSnapshot
→ change detection
→ observation recording
→ WatchItem update and save
```

The Production Composition Root shares one `PriceHistoryRepository` instance
between the snapshot provider and observation recorder. Successful changed and
unchanged observations are both appended. Price History and WatchItem writes
remain separate transactions; duplicate prevention and the complete
partial-failure policy remain PR4-B work.

Validation completed with `23 passed` for Monitor tests, `2 passed` for the
recorder adapter, `3 passed` for Composition, and `1148 passed` for the full
regression suite. The existing FastAPI TestClient warning remains.

---

## 2026-07-31 — WatchList Monitor CLI Entry Point

Sprint 11 PR3 exposed one WatchList Monitor execution through the existing
argparse CLI style:

```text
--watch-monitor
→ create_watchlist_monitor(database_path)
→ WatchListMonitorUseCase.execute()
→ aggregate CLI output
```

The mode branches before query resolution and Opportunity search repository
creation, so it does not require a search query or execute the search flow.
Worker scheduling, Dashboard integration, notification, and current Snapshot
storage remain outside this scope.

Validation completed with `2 passed` for the new CLI tests, `18 passed` for
existing CLI/Presentation/Composition tests, and `1140 passed` for the full
regression suite.

---

## 2026-07-31 — WatchList Monitor Composition Root

Sprint 11 PR2 added a small WatchList Infrastructure factory because the
repository has no general bootstrap or DI-container pattern. The factory
follows the existing Marketplace adapter factory style and composes:

```text
SQLiteWatchListRepository
MarketplaceListingLookupAdapter with eBay/Amazon readers
PriceHistoryRepository
→ PriceHistorySnapshotProvider
→ DetectLatestPriceChangeUseCase
→ WatchListMonitorUseCase
```

The database path and the three Application dependencies remain optionally
injectable for isolated tests. Factory construction performs no Marketplace
lookup. CLI/Worker execution and current Snapshot persistence remain pending.

Validation completed with `2 passed` for the new composition tests, `76 passed`
for the existing WatchList suite, `72 passed` for Change Detection and Price
History, and `1138 passed` for the full regression suite.

---

## 2026-07-31 — Marketplace Reader Integration

Sprint 11 PR1 connected the existing eBay and Amazon exact-item lookup
functions to the existing `MarketplaceListingReader` contract. A small
Infrastructure factory now creates `MarketplaceListingLookupAdapter` with both
readers registered.

The PR does not construct `WatchListMonitorUseCase` or add an execution entry
point. Composition Root, CLI, worker scheduling, Snapshot storage, and
Dashboard integration remain outside this scope.

Validation completed with `43 passed` for the focused reader/dispatcher suite
and `1136 passed` for the full regression suite.

---

## 2026-07-31 — Context Pack Automation

Sprint 11 PR0 added repository scripts that generate Quick and Full Context
ZIPs from the current project state. Generation removes the previous two
Context ZIPs and manifest first; cleanup removes only those three generated
artifacts and preserves `context/.gitkeep`.

PowerShell execution and archive-entry validation confirmed the Quick and Full
contents. The full regression result remained `1131 passed`.

---

## 2026-07-29 — Sprint 8 PR3-B2 Completion

### Context

WatchList Monitor가 등록 상품을 정확히 다시 조회하려면
Marketplace별 single-item lookup 기능이 필요했습니다.
기존 eBay와 Amazon 모듈에는 search 기능만 있고 exact item lookup이 없었습니다.

### Decision

검색 결과 첫 항목을 감시 대상 상품으로 사용하는 방식은 채택하지 않았습니다.

```python
search_items(...)[0]
```

이 방식은 정확한 동일 상품을 보장하지 못하고,
투자 판단 시스템의 신뢰도를 훼손할 수 있기 때문입니다.

Search와 Lookup을 별도 책임으로 유지하고,
Marketplace item ID를 이용한 exact lookup API를 추가했습니다.

### Implementation Direction

- eBay: exact item endpoint 기반 조회
- Amazon: production API 연결 전까지 deterministic exact-ID contract 유지
- Marketplace raw response는 기존 adapter의 normalization/validation을 재사용
- WatchList Application layer는 HTTP 구현을 알지 않음

### Validation

- 전체 회귀 테스트를 실제 재실행
- Result: **1053 passed**
- Commit: `3806736 feat: add marketplace item lookup APIs`

### Next

Sprint 8 PR3-B3에서 Marketplace Reader를 구현하고
`MarketplaceListingLookupAdapter`와 실제 lookup API를 연결합니다.

---

## 2026-07-29 — Sprint 8 PR3-B1 Dispatcher Design

### Context

WatchList Monitor가 eBay, Amazon 등 Marketplace별 구현을 직접 분기하면
Application 계층이 Infrastructure 세부사항에 결합될 위험이 있었습니다.

### Decision

Infrastructure dispatcher를 두고 Marketplace별 Reader를 등록하는 구조를 선택했습니다.

```text
WatchListMonitorUseCase
→ ListingLookupPort
→ MarketplaceListingLookupAdapter
→ Marketplace Reader
```

### Key Rules

- Marketplace 이름 정규화
- 지원하지 않는 Marketplace는 명확한 오류
- Reader는 `Product | None` 계약 준수
- item ID 또는 URL 없이 조회하지 않음
- Reader의 실제 예외를 무조건 삼키지 않음

### Commit

`97b60e7 feat: add marketplace listing lookup dispatcher`

---

## 2026-07-29 — Context Continuity Improvement

### Problem

새 채팅에서 `PROJECT_STATUS.md`가 Sprint 7, 853 passed 상태로 남아 있어
현재 Sprint 8 진행 상황을 잘못 해석했습니다.

### Decision

프로젝트 인수인계 정확도를 높이기 위해 다음 6개 문서를
Current Context Pack으로 함께 유지합니다.

- `PROJECT_STATUS.md`
- `PROJECT_CONTEXT.md`
- `DOCUMENT_STATUS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `AI_DEVELOPMENT_LOG.md`

### Rule

현재 상태가 변할 때 Context ZIP 생성 전에 이 문서들을 최신화합니다.
새 채팅에서는 코드 구현 전에 Context 문서와 실제 Git/소스 상태를 함께 확인합니다.

---

## Long-Term Collaboration Principles

- User is Product Owner and final decision-maker.
- AI Partner acts as architect, co-developer, reviewer, PM, QA, and continuity partner.
- Robust and reliable architecture is preferred over shortcuts.
- Business value and real seller outcomes guide technical priorities.
- Major decisions should be documented through ADRs when appropriate.
- Every PR should be small, testable, documented, and transferable through Context ZIPs.
- Major work should keep `DEVELOPMENT_PRINCIPLES.md` synchronized with architecture, code, tests, and project documentation.
