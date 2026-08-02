# HYB Changelog

## PR19-B - External Signal Ledger Foundation

- Persist OCR candidates and human verifications as append-only SQLite facts.
- Maintain non-regressing latest projections atomically with history insertion.
- Reject provenance fingerprints duplicated across candidate or verification history.

---

## PR19-A - External Signal Trust Foundation

- Add immutable artifact, unverified OCR candidate, and human verification facts.
- Enforce an explicit human-verification boundary before external signal creation.
- Keep OCR engines, persistence, recommendation, and decision behavior out of scope.

---

## PR18-B.1 - Demand Availability Contract Hardening

- Assess available demand evidence independently instead of requiring all five proxies.
- Add complete/partial availability metadata and average confidence only across usable evidence.
- Remove the misspelled demand/competition balance field before it becomes a public contract.

---

## PR18-B - Demand Intelligence Foundation

- Add immutable demand-only assessments with explicit search, review, and rating thresholds.
- Preserve ranking signals as independent demand proxies and exact Decimal confidence evidence.
- Reuse the PR17 observation repository without adding recommendation or decision behavior.

---

## PR18-A - Competition Intelligence Foundation

- Add immutable competition-only assessments and explicit MVP threshold policies.
- Calculate price pressure from relative price spread and preserve Decimal confidence averages.
- Reuse the PR17 observation repository without adding scoring or recommendation behavior.

---

## PR17-3 - Market Observation Repository Foundation

- Add application use cases and a common repository port for immutable market observations.
- Persist append-only SQLite history and update a separate latest-observation projection atomically.
- Reject duplicate provenance fingerprints and calculate freshness only at query time.

---

## PR17-2 - Market Observation Contracts

- Add immutable Competition and Demand observation snapshots with strict metric validation.
- Add immutable external reference signals with human-verification and artifact provenance rules.
- Keep scoring, recommendation, persistence, collectors, OCR, and presentation unchanged.

---

## PR17-1 - Market Evidence Contract

- Add immutable market evidence status and provenance contract.
- Add scope-aware market observation identity and time-window validation.
- Keep Competition, Demand, External Signal, persistence, and presentation out of scope.

---

## PR16-A.1 - Variance Snapshot Contract Hardening

- Preserve original tax-rate evidence separately from calculated tax-cost evidence.
- Require complete economic evidence metadata when an estimated snapshot is created.
- Preserve required evidence keys through SQLite baseline round trips.

---

## PR16-A — Estimated vs Actual Variance Foundation

- immutable Estimated Economics admission baseline과 evidence/version 보존 추가
- Actual Economics와 baseline을 비교하는 side-effect-free Variance Domain 계산 추가
- signed/absolute/relative difference, ROI percentage-point 및 comparability 상태 구현
- Lifecycle, admission snapshot, estimated baseline의 SQLite atomic admission 경로 추가
- Variance 결과는 저장하지 않고 source version으로 조회 시 계산

---

## PR15-A.2 — Actual Economics Ledger Final Hardening

- 최초 Purchase event에 currency를 기록하고 Aggregate currency와의 binding 검증 추가
- Event history currency를 보존하는 additive SQLite column migration 추가
- malformed event version은 semantic error, 실제 persisted version 충돌은 optimistic conflict로 분리

---

## PR15-A.1 — Actual Economics Ledger Contract Hardening

- Purchase, Sale, Settlement event의 action별 필수/금지 fact 검증 추가
- Event fact를 Aggregate 및 기존 persisted state와 대조해 current/history 불일치 차단
- 숫자 0을 유효한 actual fact로 보존하고 `None`만 누락으로 처리
- `EMPTY`/version 0을 DB row가 없는 transient-only 상태로 명시
- sale price는 fee 차감 전 gross 값이며 settlement는 계산에 사용하지 않는 보존 사실임을 명시

---

## PR15-A — Actual Economics Foundation

- Verified Economics의 예상값과 분리된 Actual Economics Aggregate 추가
- Purchase, Sale, Settlement 실제 사실과 계산된 actual profit/ROI 계약 추가
- Lifecycle 상태를 읽기 사전조건으로만 사용하는 Application use case 추가
- current state와 append-only event history를 원자적으로 저장하는 additive SQLite repository 추가
- 기존 Recommendation, Lifecycle, Validation Queue 및 Presentation 계약은 변경하지 않음

---

## PR14-B.1 — Validation Queue Contract Hardening

- Discovery reference를 trim/lowercase/stable `:` separator 형식으로 canonicalize
- non-archived Lifecycle 전체에 canonical discovery reference uniqueness 적용
- archive 후 동일 reference 재등록은 허용하되 restore/return 충돌은 명시적 duplicate conflict로 반환
- 기존 Queue/Lifecycle/Snapshot reference를 transaction migration에서 canonical 형식으로 정규화

---

## PR14-B — Founder Validation MVP

- OpportunityLifecycle 기반 Validation Queue read model과 immutable admission snapshot projection 추가
- 선택한 Opportunity만 명시적으로 등록하는 `AddToValidationQueue` 및 조회/Review/Approve/Reject/ReturnToReview use case 추가
- Lifecycle current state, CREATE history, admission snapshot을 하나의 SQLite transaction으로 저장
- active Queue discovery reference에 대한 동시 중복 등록 방지
- 기존 Search, CLI, Dashboard DTO를 유지하는 additive Validation Queue FastAPI 추가

---

## PR14-A.1 — Lifecycle Contract Hardening

- Lifecycle status, version, identity, timestamp를 외부에서 직접 대입할 수 없도록 캡슐화
- SQLite 복원을 전용 internal reconstruction path로 분리
- transition 저장 전 previous/new status, version, timestamp, action 및 event completeness 검증
- semantic validation 실패 시 current state와 append-only history를 그대로 보존

---

## PR14-A — Opportunity Lifecycle Foundation

### Added

- Validation Queue에 명시적으로 저장된 Opportunity만 관리하는 별도 Lifecycle Aggregate
- Founder Approve/Reject 결정을 AI Recommendation과 분리한 불변 Domain Contract
- 허용 상태 전이, SOLD terminal, archive/restore metadata 및 optimistic version 규칙
- 현재 상태와 append-only 전이 이력을 원자적으로 저장하는 additive SQLite repository

### Compatibility

- 기존 OpportunityResult, RecommendationResult 및 opportunity_history는 변경하지 않음
- Discovery, CLI, FastAPI, Dashboard에 자동 Lifecycle 생성 또는 출력 변경을 추가하지 않음

---

이 문서는 Sprint 및 PR별 주요 변경사항을 최신 항목부터 기록합니다.

---

## PR13-C — Verified Economics Contract

### Added

- Opportunity Domain의 경제 입력 provenance 계약
- `verified`, `estimated`, `default`, `calculated`, `missing`,
  `unsupported` evidence 상태
- 기존 Product와 orchestrator 인자를 contract로 조립하는 mapper
- 기존 `calculate_opportunity(dict)` 결과를 typed calculation으로 감싸는
  호환 wrapper
- Safety Gate의 contract 우선 평가 및 기존 `*_known` fallback

### Compatibility

- 기존 Opportunity, ROI, score, trend, recommendation 공식은 변경하지 않음
- CLI, Dashboard, FastAPI, opportunity history 외부 계약은 변경하지 않음
- 기존 `calculate_opportunity(dict)` 및 `calculate_product_opportunity()` 유지

### Validation

- PR13-C Domain/Opportunity/Safety feature tests: `32 passed`
- Full pytest: `1203 passed`
- Warning: 기존 FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR5 — Release Candidate and Sprint Completion

### Added

- Production Composition Release Candidate E2E coverage
- Actual `--watch-monitor` CLI integration with WatchList and Price History
- Sprint 11 Completion Report

### Audit

- Repository, Change Detector, Observation Recorder, and Monitor wiring verified
- Domain and WatchList Application dependency directions verified
- No circular dependency, Infrastructure leak, or Domain rule violation found

### Validation

- Release Candidate E2E: `1 passed`
- Production Composition: `3 passed`
- CLI: `31 passed`
- WatchList: `96 passed`
- Price History: `34 passed`
- Change Detection: `30 passed`
- Full pytest: `1160 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR4-B — Price Observation Idempotency

### Added

- Observation identity based on canonical product, marketplace, item, and
  observation time
- Idempotent retry returning the existing Price History record ID
- Explicit `PriceObservationConflictError` for different data under one
  observation identity
- ADR-0002 documenting idempotency and partial-failure policy

### Architecture

- Price remains observation data rather than identity
- Existing records remain append-only and are never overwritten
- SQLite `BEGIN IMMEDIATE` serializes the repository identity check and insert
- Price History and WatchItem writes remain separate transactions
- A retained observation allows WatchItem save to recover on retry

### Validation

- Price History tests: `34 passed`
- WatchList tests: `94 passed`
- Change Detection tests: `30 passed`
- CLI tests: `30 passed`
- Full pytest: `1158 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR4-A — WatchList Price Observation Recording

### Added

- Narrow `PriceObservationRecorder` Application port
- `PriceHistoryObservationRecorder` adapter backed by the existing
  `PriceHistoryRepository`
- WatchList Monitor recording of successful current-price observations

### Architecture

- Execution order is change detection, observation recording, then WatchItem save
- Changed and unchanged successful observations are both appended
- Price History and WatchItem writes remain separate transactions
- Deduplication and detailed partial-failure policy remain PR4-B scope

### Validation

- Monitor feature tests: `23 passed`
- Recorder adapter tests: `2 passed`
- Composition tests: `3 passed`
- WatchList regression: `92 passed`
- Change Detection and Price History regression: `57 passed`
- CLI regression: `30 passed`
- Full pytest: `1148 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR3 — WatchList Monitor CLI Entry Point

### Added

- Existing argparse-style `--watch-monitor` CLI mode
- CLI connection from `create_watchlist_monitor()` to one monitor execution
- Total, Updated, Unchanged, Failed, and Not Found summary output
- Isolated CLI tests with fake and real empty SQLite composition

### Architecture

- Existing search and history CLI flows remain unchanged
- No Worker, Scheduler, Dashboard, notification, or Snapshot storage changes

### Validation

- New WatchList Monitor CLI tests: `2 passed`
- Existing CLI, Presentation, and Composition tests: `18 passed`
- Full pytest: `1140 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR2 — WatchList Monitor Composition Root

### Added

- Public `create_watchlist_monitor()` Infrastructure factory
- Actual SQLite WatchList repository, eBay/Amazon lookup adapter,
  Price History provider, and latest-price detector composition
- Public-behavior composition tests using an isolated SQLite database

### Architecture

- Factory construction does not call Marketplace APIs
- Existing Domain, Application, Adapter, and Reader contracts are unchanged
- CLI/Worker execution and current Snapshot storage remain outside this PR

### Validation

- New composition tests: `2 passed`
- Existing WatchList tests: `76 passed`
- Change Detection and Price History tests: `72 passed`
- Full pytest: `1138 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR1 — Marketplace Reader Integration

### Added

- `EbayListingReader` using `marketplaces.ebay.get_product_by_id()`
- `AmazonListingReader` using `marketplaces.amazon.get_product_by_id()`
- eBay/Amazon reader registry factory for
  `MarketplaceListingLookupAdapter`
- Concrete reader contract and registry dispatch tests

### Architecture

- Existing reader and lookup adapter contracts remain unchanged
- No Composition Root, CLI, worker, Snapshot storage, or Dashboard changes

### Validation

- Reader, dispatcher, adapter, and exact lookup tests: `43 passed`
- Full pytest: `1136 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR0 — Context Pack Automation

### Added

- PowerShell scripts to create and clean Quick and Full Context Packs
- Generated Context manifest and documented archive exclusions
- Context Pack usage guide and persistent `context/.gitkeep`

### Changed

- Generated Context Pack artifacts are ignored by Git
- Context Pack refresh is part of the project Definition of Done

### Validation

- Create and cleanup scripts executed in PowerShell
- Quick Context: `6` expected files, `0` missing or unexpected
- Full Context: `375` files, `0` excluded entries
- Full pytest: `1131 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 10 Finalization — Audit Report

### Added

- Official Sprint 10 audit covering PR1 and PR2A through PR2D
- Architecture impact, validation, limitations, lessons learned, outcome,
  and Sprint 11 planning direction

### Status

- Sprint 10 completed
- Current focus moved to Sprint 11 planning
- Final FastAPI feature validation: `10 passed`
- Final full regression: `1131 passed`

---

## Sprint 10 PR2D — Dashboard UX Polish

### Added

- Initial empty state prompting the user to search
- Result summary using the returned query and opportunity count
- Centered, responsive dashboard layout with improved spacing
- Status and alert roles for loading, summary, and error states
- Dashboard UX accessibility HTML contract test

### Architecture

- Existing browser fetch and search API remain unchanged
- No backend, API route, or business logic changes
- No external frontend dependency was added

### Validation

- FastAPI feature tests:
  - `10 passed`
- Full pytest:
  - `1131 passed`

---

## Sprint 10 PR2C — Opportunity Dashboard MVP

### Added

- Semantic opportunity card rendering from existing `dashboard_cards` JSON
- Product title, Marketplace, final score, ROI, expected selling price,
  and net profit display
- Minimal card styling with emphasized score
- Searching, no-results, and error states
- Opportunity dashboard HTML contract test

### Architecture

- Existing search API and JSON response are reused without backend changes
- Dashboard rendering remains browser-side
- No API route or external UI dependency was added

### Validation

- FastAPI feature tests:
  - `9 passed`
- Full pytest:
  - `1130 passed`

---

## Sprint 10 PR2B — API-First Opportunity Search

### Added

- Vanilla JavaScript `searchOpportunities()` function
- Existing `POST /api/v1/opportunities/search` integration
- Loading, error, and results containers
- Simple title, marketplace, and final opportunity score rendering
- Landing page search-control test

### Architecture

- Search results are rendered in the browser without server-side result rendering
- Existing search API and business logic remain unchanged
- No new search route or external frontend dependency was added

### Validation

- FastAPI feature tests:
  - `8 passed`
- Full pytest:
  - `1129 passed`

---

## Sprint 10 PR2A — Initial Web Landing Page

### Added

- `GET /` HTML landing page
- FastAPI `Jinja2Templates` configuration
- `templates/index.html` with a minimal search form
- Landing page response test

### Dependencies

- `jinja2 3.1.6`

### Architecture

- HTML endpoint renders a template only and contains no business logic
- No Marketplace API is called
- Existing JSON endpoints, including `POST /api/v1/opportunities/search`, are unchanged
- Engine, Domain, Application, CLI, Storage, Presentation, and Marketplace layers are unchanged

### Validation

- FastAPI feature tests:
  - `7 passed`
- Full pytest:
  - `1128 passed`
- Warning:
  - FastAPI TestClient의 `httpx` fallback 관련
    `StarletteDeprecationWarning` 1건

---

## Sprint 10 PR1 — FastAPI JSON MVP

### Added

- FastAPI application entry point
- `GET /health`
- `GET /version`
- `POST /api/v1/opportunities/search`
- 기존 `find_best_opportunities()` 호출
- 기존 Opportunity List와 Dashboard Presentation Builder 기반 JSON 응답
- 외부 Marketplace 호출을 mock한 FastAPI TestClient 테스트

### Dependencies

- `fastapi 0.141.1`
- `uvicorn 0.52.0`
- `httpx 0.28.1`

위 버전은 프로젝트 Python 3.14.6 환경에서 실제 설치하고 검증했다.

### Architecture

- Engine, Domain, Application, CLI 변경 없음
- Engine 객체를 직접 JSON으로 반환하지 않음
- 기존 `OpportunityListCard.to_dict()`와 `DashboardCard.to_dict()` 재사용

### Validation

- FastAPI feature tests:
  - `4 passed`
- Full pytest:
  - `1125 passed`
- Warning:
  - FastAPI TestClient의 `httpx` fallback에 대한
    `StarletteDeprecationWarning` 1건

---

## Sprint 9 PR3 — Price History Integration for Opportunity Intelligence

### Added

- 일반 CLI 검색에서 `PriceHistoryRepository` 생성
- 동일 Repository 인스턴스를 기존 Orchestrator와 신규 Opportunity
  Intelligence Adapter에 공유
- 저장된 가격 이력 기반 Trend Assessment와 Final Recommendation 출력

### Compatibility

- 기존 CLI 인수, Orchestrator 계약, Presentation 출력과 기존
  Recommendation 유지
- `_evaluate_opportunity_intelligence()`의 Repository 인자는 선택적이며
  기본값은 `None`
- `--no-save`에서는 Repository를 생성하거나 전달하지 않아 기존 비저장
  동작 유지

### Validation

- Feature tests:
  - `34 passed`
- Full pytest:
  - `1121 passed`

---

## Sprint 9 PR2 — Existing CLI Opportunity Intelligence Output

### Added

- 기존 CLI 결과 뒤에 Opportunity Intelligence 상태와 평가 결과 추가 출력
- 신규 Opportunity Score, Decision, Grade, Confidence, Risk 표시
- Trend와 신규 Final Recommendation이 존재할 때만 선택적으로 표시
- `OpportunityResult` 단위 Intelligence 실패 격리

### Changed

- 기존 Orchestrator의 `OpportunityResult` → `DiscoveryResult` 변환을
  CLI와 Gateway가 함께 재사용할 수 있는 함수로 추출
- 기존 CLI 인수, Orchestrator 호출, Dashboard, 기존 Recommendation 유지

### Validation

- Feature tests:
  - `44 passed`
- Full regression:
  - `1119 passed`
- 기존 `.venv` 실행 파일은 프로세스를 생성하지 못해 프로젝트 기반
  Python 3.14 런타임으로 테스트 실행

### Known Limitation

- 기본 CLI는 신규 Intelligence Adapter에 Price History Repository를
  주입하지 않으므로 Trend와 신규 Final Recommendation은 기본 실행에서
  생성되지 않는다.

---

## Sprint 8 PR3-B2 — Marketplace Item Lookup APIs

### Added

- eBay exact item lookup API
- eBay raw item response to validated `Product` conversion
- Amazon deterministic exact item lookup contract
- Amazon lookup result to `Product` conversion
- Exact lookup validation and error-handling tests

### Changed

- Search와 single-item lookup 책임을 명확히 분리
- Amazon 개발용 item catalog를 search와 lookup에서 공통 사용하도록 정리
- WatchList monitoring이 검색 첫 결과를 추정값으로 사용하지 않도록 기반 강화

### Validation

- Full regression: **1053 passed**
- Commit: `3806736 feat: add marketplace item lookup APIs`
- Branch: `main`

---

## Sprint 8 PR3-B1 — Marketplace Listing Lookup Dispatcher

### Added

- `MarketplaceListingLookupAdapter`
- Marketplace reader protocol
- Marketplace name normalization and dispatch
- Unsupported Marketplace handling
- Reader result contract validation
- Dispatcher tests

### Decisions

- Application layer는 Marketplace 구현을 직접 알지 않음
- Infrastructure dispatcher가 Marketplace별 reader를 선택
- Reader exception은 숨기지 않고 상위 호출자가 처리할 수 있도록 유지

### Git

- Commit: `97b60e7 feat: add marketplace listing lookup dispatcher`

---

## Sprint 8 PR3-A — WatchList Monitor Foundation

### Added

- Listing lookup application port
- Monitor request/result models
- WatchList monitor use case foundation
- WatchList monitoring tests

### Direction

- WatchList entry를 Marketplace의 최신 `Product`로 조회
- 이후 Change Detection과 연결할 수 있는 Application boundary 확보

---

## Sprint 8 — WatchList Foundation

### Added

- WatchList domain models and aggregate behavior
- SQLite WatchList repository
- Infrastructure mapper
- Repository and domain tests

### Architecture

- WatchList state와 Marketplace 조회 책임 분리
- 저장소 구현은 Infrastructure에 유지
- Monitoring은 Application use case로 구성

---

## Sprint 7 — Marketplace and Presentation Expansion

### Added / Changed

- eBay marketplace adapter integration
- Marketplace adapter contract tests
- Marketplace validation strengthening
- Dashboard utilities and component extraction
- Hero summary
- Opportunity list ViewModel
- Opportunity list CLI presentation

### Recent Commits

- `6972c7e feat: integrate eBay marketplace adapter`
- `0980269 test: add marketplace adapter contract tests`
- `df23ee0 refactor(presentation): extract dashboard utilities and restore decision timeline`
- `95a3570 refactor(presentation): extract dashboard component builders`
- `2655753 feat(presentation): add dashboard hero summary`
- `1efe197 feat(presentation): add opportunity list view model`
- `448b443 feat(presentation): render opportunity list in cli`

---

## Sprint 7 PR-3 — Documentation Quality Audit

### Added

- Documentation audit report
- Sprint 6 summary
- Documentation inventory and cross-reference audit

### Changed

- Project status, Sprint history, document index, documentation policy, and changelog

### Validation

- Markdown UTF-8 validation passed
- Inspectable relative links: no broken links found
- Last code regression at that point: **853 passed**

---

## Sprint 6 — Explainable Decision Pipeline

### Added

- Market Adjustment explanation
- Decision Report integration
- AI Partner decision explanation
- Dashboard Decision Timeline

### Validation

- Full regression at Sprint 6 completion: **853 passed**

## PR13-B — Production Safety Gate

### Added

- Explicit `production`, `test`, `demo`, and `unspecified` product data sources.
- A post-score Safety Gate that preserves scores while preventing incomplete
  `BUY` and `STRONG_BUY` recommendations.
- `INSUFFICIENT_DATA` safety status with explicit missing-field reasons.
- `PROFITABILITY_FAILED` as a distinct hard-gate status, plus original and
  effective recommendation grades.
- Shipping-cost provenance so an omitted cost is distinct from confirmed free
  shipping.
- Per-component verification metadata for marketplace, payment, and fixed fees.
- Structured Safety Gate fields in Dashboard/API output and opportunity history.

### Changed

- The fixed Amazon catalog remains available for demo and tests but is no
  longer part of production opportunity discovery.
- A production BUY now requires a production source, purchase price, currency,
  known shipping cost, at least two price observations, fee inputs, net profit,
  and ROI.
- Known New and Used conditions are treated as a high comparable conflict.

### Compatibility

- Opportunity scores, weights, thresholds, ROI formulas, and trend formulas
  are unchanged.
- Existing non-BUY recommendations are not upgraded or recalculated by the
  Safety Gate.

Sprint 13

PR13-B
- Production Safety Gate
- Provenance
- Profitability Hard Gate
- Founder Validation Safety

PR13-C
- Verified Economics Contract
- Economics Domain Model
- Legacy Wrapper
- Typed Economics Contract
