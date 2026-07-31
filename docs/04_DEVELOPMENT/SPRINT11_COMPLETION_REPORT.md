# Sprint 11 Completion Report

## Sprint Goal

Sprint 11 made WatchList monitoring operational and connected current
Marketplace observations to durable, retry-safe Price History.

## Completed Features

- Context Pack creation and cleanup automation
- eBay and Amazon Marketplace listing readers and registry
- WatchList Monitor Production Composition Root
- `--watch-monitor` CLI execution entry point
- Compare-before-record Price Observation persistence
- Idempotent observation retry and explicit conflict handling
- Partial-failure recovery when WatchItem persistence is retried

## Architecture Changes

The existing Application Port and Infrastructure Adapter direction was
preserved:

```text
CLI
→ create_watchlist_monitor()
→ WatchListMonitorUseCase
   ├─ WatchListRepository
   ├─ ListingLookupPort
   ├─ LatestPriceChangeDetector
   └─ PriceObservationRecorder
→ SQLite / Marketplace adapters
```

Production Composition provides the same `PriceHistoryRepository` instance to
the latest-snapshot provider and observation recorder. Change Detection runs
before observation recording, followed by WatchItem update and persistence.

The Release Candidate audit found no reverse Domain dependency, Infrastructure
import in the WatchList Application package, circular dependency, or Domain
rule violation in this flow.

## ADR

- ADR-0001: Opportunity Intelligence Integration Boundary
- ADR-0002: Price Observation Idempotency and Partial Failure

ADR-0002 records observation identity, append-only conflict handling,
non-atomic Price History and WatchItem writes, and retry recovery.

## Release Candidate Validation

The Production Composition E2E test covers:

- First observation
- Changed price
- Unchanged price
- Idempotent observation retry
- WatchItem save failure and retry
- Observation conflict
- Recovery after failure
- Consecutive processing of multiple WatchItems

Each phase verifies Monitor/Change Detection results, Price History rows, and
persisted WatchItem state.

Validation results:

- Release Candidate E2E: `1 passed`
- Production Composition: `3 passed`
- CLI: `31 passed`
- WatchList: `96 passed`
- Price History: `34 passed`
- Change Detection: `30 passed`
- Full regression: `1160 passed`
- Warning: one existing FastAPI TestClient `StarletteDeprecationWarning`

## Technical Debt

- Price History and WatchItem writes remain separate transactions.
- Existing historical duplicate observations are not migrated or rewritten.
- `BEGIN IMMEDIATE` serializes SQLite writers and may create contention at
  higher write volume.
- Direct SQL and write APIs other than `save_product_price()` are outside the
  observation-idempotency guarantee.
- Worker/Scheduler, notifications, and WatchList Dashboard remain future work.

## Sprint 12 Readiness

The WatchList execution path now has concrete Marketplace readers, Production
Composition, CLI execution, durable observation history, idempotent retry, and
Release Candidate coverage. Sprint 12 can plan operational execution or user
experience work without changing the current Domain/Application contracts.

Unit of Work, Outbox, migration framework, and performance optimization should
only be introduced when operational requirements demonstrate the need.

## Release Readiness

**Ready for Sprint 11 release review.**

All required feature, integration, related regression, and full regression
tests pass. No new business behavior was added during RC finalization. The
remaining limitations are documented and do not block the current
single-process SQLite CLI release boundary.
