# HYB Changelog

이 문서는 Sprint 및 PR별 주요 변경사항을 최신 항목부터 기록합니다.

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
