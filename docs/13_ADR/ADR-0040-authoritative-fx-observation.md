# ADR-0040 Authoritative FX Observation

## Status
Accepted

## Context

Cost normalization for mixed-currency acquisition costs requires an authoritative FX fact that is owned by HYB, not a caller-supplied value and not a live provider convenience.

Current sourcing/landed-cost contracts preserve source currencies and can determine that multiple currency components may need explicit FX normalization later, but there is currently no authoritative FX observation contract.

## Decision

Introduce a strict FX observation authority contract and application boundary:

- `AdmitFXObservationCommand` (caller facts)
- `AdmitFXObservation` (authoritative admission use case)
- `FXObservation` and `FXObservationProvenance`

This boundary validates caller-provided FX observation facts, creates server-owned authoritative facts, and returns deterministic replay results.

Canonical pair semantics are explicit:

- `base_currency=USD`, `quote_currency=KRW`, `rate=1380` means `1 USD = 1380 KRW`
- `base_currency != quote_currency`
- 3-letter currencies only
- Decimal `rate > 0`

## Schema and Authority

- Domain schema: `fx-observation-v1`
- Command schema: `fx-observation-command-v1`
- `observation_id` is server-owned
- Caller-provided timestamps are preserved as `observed_at`
- Server-provided `admitted_at` is authoritative for HYB acceptance time
- Repository persistence remains delegated to follow-up PR

## Replay Contract

- same command + same payload ¡æ exact replay
- same command + changed payload ¡æ conflict
- identity and clocks are not invoked during replay

## Provenance and Trust Boundary

`FXObservationProvenance` carries provider and optional source/collection metadata.

HYB authoritative fact is the only value used for future normalization; no automatic inverse rate generation, freshness policy, rounding policy, or FX conversion is performed here.

## Deferred Work

- Postgre/SQLite persistence
- Freshness policy
- Inverse observation derivation
- currency rounding behavior
- cost normalization
- Capital policy and Critical Cost integration

## Interaction with Critical Cost

The FX observation boundary only provides a fact format and provenance contract.
Critical Cost completeness and any future cost normalization logic must consume explicit observations from this contract rather than inferring with latest FX.