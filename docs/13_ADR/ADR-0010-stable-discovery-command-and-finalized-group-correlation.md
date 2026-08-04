# ADR-0010: Stable Discovery Command and Finalized Group Correlation

## Status

Accepted as a contract foundation; persistence and production wiring are pending

## Context

PR34-B could not persist Candidate issuance receipts because the discovery path
had no Application command ID, execution ID, canonical request payload,
collector observation identity, or stable ProductGroup reference. ProductGroup
contained only a mutable Product list. Group order followed collector order and
greedy grouping, so list index was not a retry-safe key.

## Discovery Command

`DiscoveryCommand` separates command identity from canonical payload identity.
Its immutable typed parameters cover the existing `find_best_opportunities`
inputs that can affect collection, grouping, price/economics analysis, and final
results. Decimal values remain Decimal, boolean and integer fields remain
distinct, and injected policy/source dependencies are represented only by
explicit sorted immutable references. Runtime repository, converter, callback,
history, or arbitrary object instances are not embedded.

The command fingerprint excludes command ID. Therefore the same command ID and
changed payload can conflict, while a different command ID with identical intent
remains a new live discovery execution. Business-level deduplication across
different commands is not introduced.

## Collector Observation Identity

`CollectedProductObservation` preserves a server-supplied observation ID,
execution ID, exact marketplace and listing item source keys, immutable Product
facts, collector provenance, observation time, and schema version. Existing
collector adapters remain unchanged.

Current query-based collectors cannot authoritatively supply the complete
LISTING or CANONICAL_PRODUCT MarketObservationIdentity window. The envelope may
therefore retain an explicitly unresolved Candidate Market identity. If an
identity is supplied, scope and source marketplace/listing equality are checked.
Titles, queries, categories, lowest-price representatives, and Product text are
never promoted into Market identity.

## Finalized Group Correlation

`FinalizedProductGroup` is created immediately after grouping succeeds and before
PriceIntelligence, Economics, or Candidate issuance. It has two separate facts:

- a server-owned opaque finalized group ID; and
- a canonical membership fingerprint over ordered collector observation IDs,
  grouping policy/version, representative observation ID, execution ID, and
  contract version.

The group ID is not derived from the fingerprint. The fingerprint does not use
group index, title, representative item ID alone, runtime hash, unordered sets,
or mutable prices. Failed downstream analysis does not erase the finalized group
fact. Persistence and retention policy belong to later PRs.

## Command-level Result

`DiscoveryExecutionResult` preserves command/execution IDs, ordered finalized
group IDs, completion time, schema version, and canonical result fingerprint. An
empty tuple is a successful zero-result. The current orchestrator propagates an
unhandled group analysis failure, so this foundation models only complete
successful results; partial-success semantics are not invented.

Once a command result is durably committed, replay of that command must return
the committed result without calling the marketplace again. A different command
ID is a new live observation and may legitimately produce different Products or
groups.

## Candidate Issuance Replay Key

The authoritative future lookup key is `(command_id, finalized_group_id)`. Its
conflict fingerprint combines the canonical command fingerprint, finalized
membership fingerprint, explicit Candidate MarketObservationIdentity, and
issuance schema version.

Candidate ID is not derived from this fingerprint. The first durable issuance
uses a future injected opaque generator; receipt replay returns the stored ID.
Opportunity lifecycle and admission remain independent.

## Retry, Restart, and Concurrency

Future persistence must serialize same-command execution through SQLite and
store the command result before acknowledging success. Same command/payload
replays exactly, changed payload conflicts, and concurrent losers load the
winner's durable result. No process-local registry or lock is introduced here.

## Automatic Discovery Compatibility

The command, observation, group, and result chain provides durable correlation
without treating runtime objects or mutable market values as identity. Multiple
groups per execution and repeated live observations under different commands
remain valid. Candidate and Opportunity identity semantics from ADR-0009 remain
unchanged.

## Out of Scope

- SQLite, receipt persistence, migration, backfill, or transactions
- ID generator and Candidate issuance
- Collector adapter or grouping algorithm changes
- Snapshot persistence or subject changes
- Admission, lifecycle, Safety, Decision, Dashboard, API, or UI changes
