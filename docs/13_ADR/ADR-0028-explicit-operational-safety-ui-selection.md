# ADR-0028: Explicit Operational Safety UI Source Selection

## Status

Accepted (PR36-C)

## Decision

Operators execute Production Safety only by explicitly selecting a persisted
complete Snapshot Chain binding and one Product Snapshot member. The UI never
selects latest, first, lowest-price, or representative facts. Read DTOs expose
ordered membership and persisted Product metadata without recommendation logic.

The first committed command returns 201 and exact command replay returns 200.
The browser retains command ID, requested timestamp, binding, and Product across
failed retries; only an explicit reset generates new retry metadata. Success
triggers authoritative Safety-detail and Decision-Readiness refetch and never
automatically finalizes a Decision.

All remote text is rendered with `textContent`. The form uses labeled native
controls, an explicit confirmation, live status text, and mobile-safe layout.
Safety formula/rule changes, source inference, orchestration, migration, and
legacy fallback remain outside this decision.
