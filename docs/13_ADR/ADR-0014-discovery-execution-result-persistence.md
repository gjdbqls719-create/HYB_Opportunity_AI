# ADR-0014: Discovery Execution Result SQLite Persistence

## Status

Accepted

## Context

Commands, collected observations, and finalized groups are durable after
ADR-0012 and ADR-0013, but their existence does not prove that a Discovery
execution completed. In particular, a successful execution with no finalized
groups cannot be distinguished from an execution that stopped before grouping
finished.

## Decision

Persist one immutable `DiscoveryExecutionResult` in
`discovery_execution_result_history` for each committed command/execution pair.
The result stores ordered finalized Group IDs, explicit zero-result state,
Domain-supplied completion time, schema version, and deterministic Domain
fingerprint. Command ID and execution ID are independently unique and jointly
foreign-key bound to command history.

For a non-zero result every referenced Group must already exist and belong to
the same execution. Group order remains exactly as supplied by the Domain. An
empty tuple is a successful zero-result completion; it is not inferred from the
temporary absence of groups.

## Replay and Atomicity

Save uses `BEGIN IMMEDIATE`, inserts one history row, and commits. Insert or
commit failure rolls back the new row and preserves previously committed facts.
The same command and exact fingerprint replays the stored result. Reusing the
command or execution for changed completion facts conflicts. Separate SQLite
connections provide concurrency control without process-local locks or silent
retry.

The Repository does not own a clock. `completed_at` and the result fingerprint
already belong to the immutable Domain value. Restart and response-loss replay
therefore cannot generate a new timestamp or fingerprint.

## No Current Projection

Execution completion is one immutable authoritative fact rather than evolving
state. The table rejects UPDATE and DELETE and has no current projection.
Queries by execution or command are deterministic and read-only.

## Isolation and Deferred Work

Result persistence reads command and Group lineage but writes only its result
history table. It does not write observations, groups, Candidates, receipts,
Snapshots, Safety, Decision, Dashboard, or presentation state. Candidate ID
issuance and receipt persistence, Snapshot ownership wiring, production
Collector/orchestrator wiring, migration, and backfill remain deferred.
