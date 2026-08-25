# ADR-0012: Discovery Command SQLite Persistence

## Status

Accepted

## Implementation Status

Implemented and production-wired. The `Deferred Work` section below is the
historical scope boundary of ADR-0012; subsequent ADRs/PRs implement and compose
observation, finalized-Group, execution-result, and Candidate persistence.

## Context

ADR-0011 defines durable Discovery command replay at the Application boundary
but deliberately leaves infrastructure open. File-backed operation requires an
exact command and receipt to survive process restart and concurrent writers
without calling Collector or grouping logic again.

## Decision

SQLite owns two additive tables: immutable `discovery_command_history` and
immutable `discovery_command_receipts`. One command ID identifies one execution,
and one execution ID belongs to one command. Both identities are unique and the
receipt is foreign-key bound to the exact command/execution pair.

The command is stored as explicitly typed, deterministic canonical JSON together
with its Domain fingerprint. `repr`, pickle, arbitrary Python objects, inferred
provenance, and legacy backfill are prohibited. Reconstitution validates the
payload, duplicated columns, schema versions, receipt, and fingerprint.

## Atomic Replay

The first save uses `BEGIN IMMEDIATE`, inserts command history, inserts its
receipt, and commits. Any history, receipt, or commit failure rolls back both
facts. Separate SQLite connections serialize competing writers:

- the same command and fingerprint returns the first exact receipt;
- the same command with a changed fingerprint conflicts;
- a reused execution ID under another command conflicts; and
- another command with another execution remains independent.

No process-local lock or silent retry is used. Read methods do not begin write
transactions.

## No Current Projection

A Discovery command and its receipt are single immutable facts, not aggregates
with evolving latest state. A current table would duplicate history without a
projection lifecycle, so this boundary intentionally has no current projection.
UPDATE and DELETE triggers protect both tables.

## Ownership and Isolation

The Discovery Application boundary owns replay meaning; SQLite owns atomic
durability only. This repository does not collect products, group observations,
calculate Economics or Safety, issue Candidates, create Snapshots, or wire
existing web/CLI discovery flows.

## Deferred Work

Finalized-group persistence, execution-result persistence, Collector observation
persistence, Candidate issuance receipts, Snapshot owner wiring, migrations,
and production orchestration remain separate later decisions.
