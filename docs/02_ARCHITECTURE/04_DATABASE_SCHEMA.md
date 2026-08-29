# HYB Database Schema

Domain Model과 Database Model은 명확히 분리한다.

관리 대상:
Product
Price History
Opportunity History
Recommendation History

Product 모델 중복 문제는 통합 대상으로 관리한다.

## eBay Account Deletion Receipt Persistence

`ebay_account_deletion_receipts` is the append-only PR1 compliance inbox. Its
primary key is `notification_id`; an index on `(processing_status, received_at)`
supports operational review. The row stores only:

- current topic/schema/deprecated metadata;
- normalized event time and first publish time/attempt;
- the provided `username`, `user_id`, and/or `eias_token` subject identifiers;
- a deterministic semantic fingerprint;
- fixed `VERIFIED` authenticity and `PENDING_DELETION_REVIEW` processing status;
- the server receipt time.

The fingerprint binds stable notification semantics and intentionally excludes
retry-varying publish time/attempt metadata. A repeat notification ID with the
same semantics returns the original row; different semantics conflict. UPDATE
and DELETE triggers make the table immutable. Reads reconstruct and validate
the current envelope, fingerprint, and closed statuses and fail closed on
corruption.

No raw notification JSON, HTTP signature, verification token, OAuth token, or
client secret is persisted. No deletion queue, completion marker, anonymization
claim, or mutation of Product, price history, Discovery, or Actual Sale records
exists in PR1.

## ADR-0068 Shadow Registration/Baseline Persistence

Shadow PR3 adds three Opportunity-owned, append-only SQLite authorities, and
Shadow PR4 adds one request-level replay authority:

- `shadow_validation_registration_history` stores one canonical PR2
  `ShadowValidationRegistration` per `shadow_validation_id`, with unique
  `baseline_snapshot_id`, exact O2/screening query identities, schema version,
  Domain integrity fingerprint, and a SHA-256 fingerprint of the canonical
  payload.
- `shadow_baseline_snapshot_history` stores one canonical
  `ShadowBaselineSnapshot` per `baseline_snapshot_id`, with unique
  `shadow_validation_id`, source-manifest fingerprint, cutoff/creation times,
  schema version, Domain integrity fingerprint, and canonical-payload
  fingerprint.
- `shadow_registration_receipts` stores command fingerprint, exact
  Registration/Baseline IDs and fingerprints, explicit commit time, and receipt
  schema version. Multiple command IDs may identify the same exact immutable
  bundle, but a changed payload for an existing command or authoritative ID is
  a conflict.
- `shadow_registration_request_receipts` stores the canonical Founder request
  fingerprint, command ID, generated Registration/Baseline IDs, and exact commit
  time. It is inserted after the PR3 receipt but before the same commit, so
  request replay can return the original bundle before O2/Screening reads,
  identity generation, or clocks.

The Registration row has a unique composite
`(shadow_validation_id, baseline_snapshot_id)` authority key. Baseline and
receipt and request-receipt rows use foreign keys to that exact pair; receipts
also bind the inverse Baseline pair, and request receipts bind the exact PR3
receipt command. All four tables reject UPDATE and DELETE with triggers. One
repository-owned connection executes replay/conflict validation, Registration
insert, Baseline insert, both receipt inserts, and commit inside one `BEGIN
IMMEDIATE` transaction, so any insert, injected fault, or commit failure rolls
back the complete boundary.

Reads are exact-ID only and strictly reconstruct the PR2 contracts from stored
canonical payloads. They fail closed on malformed JSON/datetime/enums, schema or
payload fingerprint changes, query-column drift, O2/screening mismatch,
Registration/Baseline mismatch, corrupt receipts, and orphans. Replay does not
read current O2, screening, policy, marketplace, identity generation, or clock.
No cross-domain upstream foreign key is added because those authorities are not
guaranteed to share every repository database; PR4 resolves their exact IDs and
fingerprints before persistence. There is no mutable current Shadow table,
checkpoint/scheduler state, or Actual Outcome/commerce field.

## Decision Composition Finalization

Production Decision inputs are finalized after admission and authoritative market assessment. `decision_composition_history` is append-only and stores exact source IDs, five evidence metadata values, supported schema/policy versions, and a provenance fingerprint. `decision_composition_current` is an atomic latest projection; Dashboard GET reads it without writes and reconstructs every referenced source from immutable history.

Metadata policy `decision-composition-metadata-v1` uses a 30-day freshness window at explicit finalization `as_of`. Economics and Safety preserve unknown confidence when no authoritative confidence exists. External confidence is the minimum selected-signal confidence; freshness is stale if any selected signal is stale, unknown if timestamps are insufficient, and unavailable when no signal is selected.

## ReviewSession Persistence

`review_session_history` is the authoritative append-only workflow ledger. Each row has a unique event ID and command ID, the command fingerprint, session ID, monotonically increasing aggregate revision, transition type/time, prior and resulting status, and a deterministic complete aggregate payload. UPDATE and DELETE are blocked by SQLite triggers.

`review_session_current` contains one replaceable projection per session ID. A transition updates it only when its stored revision equals the command's expected revision. Creation starts at revision 1; every successful start, Candidate review/skip, completion, or cancellation advances the revision by exactly one. History and current are committed in one `BEGIN IMMEDIATE` transaction.

Approve and Correct share a single SQLite connection and transaction across `human_verification_history/current`, `market_observation_history/current`, and `review_session_history/current`. A failure in any insert, projection update, or commit rolls back all three durable areas. Skip writes only ReviewSession history/current and preserves its Candidate ID, operator, reason, time, event ID, and resulting revision.

An identical command ID and fingerprint resolves to its existing committed snapshot without inserting another history fact. Reusing a command ID with different input is a conflict; a different command based on an old revision is a version conflict. Reads reconstruct immutable Candidate membership/status order and Skip metadata and never write.

Existing Verification or External Signal ledger facts are not backfilled or guessed into ReviewSessions. A missing persisted session remains an explicit not-found condition. Founder Review API/UI remains a later layer over this repository and Application boundary.

Production Review commands cross the Application boundary using IDs and an expected aggregate revision, never a caller-supplied Session snapshot. The service loads `review_session_current` and the OCR Candidate ledger before applying Domain transitions. Legacy aggregate commands remain compatibility adapters only.

`review_session_current` can be deleted and deterministically rebuilt from the highest immutable history revision per Session. Rebuild validates every payload and commits the replacement projection atomically. History insertion, current projection, and transaction commit failures retain distinct error categories for future HTTP mapping.

`review_command_context_history` is the append-only authoritative provenance accepted for each Session Candidate; `review_command_context_current` is its immutable lookup projection. Both preserve the complete market observation identity, signal name/direction, artifact identity, creation time, and schema version. UPDATE and DELETE are blocked.

`review_command_receipts` stores the exact committed response facts for each command ID, including resulting revision, optional Candidate/Verification/External Signal IDs, transition and completion timestamps, and schema version. An identical fingerprint replays this receipt without Domain execution or fact generation; a changed fingerprint conflicts. Approve/Correct insert the receipt between Signal projection and ReviewSession history in the shared transaction, so receipt failure rolls back Verification, Signal, Receipt, and Session state.

`review_cancel_metadata` stores one immutable cancellation audit fact per Session with reason, operator, cancellation time, resulting revision, and schema version. Context, Receipt, and Cancel queries are read-only and restart-safe; all three tables reject UPDATE and DELETE through triggers.

Trusted Review creation commits its Create Receipt, ReviewSession history/current, and exactly one immutable Review Command Context for every Session Candidate in one `BEGIN IMMEDIATE` transaction. Context membership and artifact identity use the existing repository validation. Any Receipt, Session, Context, or commit failure rolls back the complete admission; identical command and Context payload replays without adding rows after restart.

## Opportunity–Review Binding

`opportunity_review_binding_history` is the append-only provenance ledger for an explicit Opportunity-to-ReviewSession association. `opportunity_review_binding_current` is its immutable lookup projection keyed by Session ID and indexed by Opportunity ID. The payload preserves binding ID, Opportunity ID, Session ID, authoritative discovery reference, complete authoritative MarketObservationIdentity, originating Review Create command ID, bound time, and schema version `opportunity-review-binding-v1`.

A trusted Review Create request may include `opportunity_id`. The shared `BEGIN IMMEDIATE` transaction loads the existing Validation Queue subject and Opportunity Market Identity binding, requires every Review Command Context to carry exactly that identity, then commits Receipt, Session, Contexts, and Opportunity–Review binding together. Missing sources, identity conflicts, duplicate Session bindings, projection failure, and commit failure leave all Review admission areas unchanged. Neither title, query, artifact ID, nor Market identity alone is used to discover an Opportunity.

Decision composition source selection uses External Signal IDs recorded by command receipts belonging to ReviewSessions explicitly bound to the requested Opportunity. When a binding exists, omitted signal IDs select only those bound Review Signals and explicitly supplied IDs outside that set conflict. Legacy Opportunities without an Opportunity–Review binding retain their pre-foundation signal selection contract.
### `verified_economics_admission_receipts`

Immutable, append-only idempotency receipts for post-admission Verified Economics.
`command_id` is the primary key and `opportunity_id` is unique, matching the single-snapshot
contract. The receipt stores the canonical command fingerprint, operator, snapshot time,
and fixed receipt schema version. The snapshot insert and receipt insert commit atomically.
### `competition_admission_receipts`

Immutable idempotency receipts for Opportunity-bound operational Competition admission.
The receipt binds one command fingerprint to its Opportunity, raw observation, generated
assessment snapshot, operator, and fixed receipt schema. Receipt, observation history/current,
and assessment history/current commit in one SQLite transaction.
### `demand_admission_receipts`

Immutable idempotency receipts for Opportunity-bound operational Demand admission. The
receipt links its canonical command fingerprint to the Opportunity, raw Demand observation,
generated assessment snapshot, operator, and fixed receipt schema. Receipt, observation
history/current, and assessment history/current commit atomically.
# Discovery Correlation Persistence Status

## Current Implementation Status

The paragraphs below preserve the incremental PR34-B history. In the current
production composition, `discovery_command_history`/receipts,
`discovery_collected_observation_history`, finalized Group history/members, and
`discovery_execution_result_history` are all implemented and wired through
`app.web` to the configured SQLite database. Completed replay reads this durable
lineage without live collection. The execution-result row stores ordered
finalized Group IDs, not the complete transient ranked opportunity payload.

Candidate issuance also has its separate durable history/context/receipt tables
and explicit API. It is not automatically written by Discovery completion.
There is no Discovery attempt/phase/failure/resume table or state machine.

PR34-B.0 adds no database objects. `DiscoveryCommand`, collector observation,
finalized ProductGroup, command result, and Candidate issuance replay-key
contracts are currently in-memory immutable Domain language only. A follow-up
PR may add append-only command/result/group and issuance receipt tables after ID
generation and transaction ownership are approved. Existing databases are not
migrated, seeded, or backfilled by this contract foundation.

PR34-B.1 adds Application repository Protocols and an immutable command receipt
contract but still adds no database objects. `save_command` is defined as the
future atomic command/receipt boundary; replay validation, group queries, and
result queries are technology-neutral. SQLite tables, triggers, transactions,
and durable replay remain a follow-up infrastructure PR.

PR34-B.2 adds `discovery_command_history` and
`discovery_command_receipts`. Both are append-only and reject UPDATE and DELETE
through triggers. Command ID and execution ID are independently unique, and a
composite foreign key binds each receipt to exactly one command/execution pair.
The history row stores deterministic canonical JSON plus the authoritative
Domain fingerprint; reads reconstruct and validate the complete typed command.

`save_command` uses one `BEGIN IMMEDIATE` transaction for history and receipt.
History, receipt, and commit failures are distinct and roll back the entire
pair. Same-command/same-fingerprint concurrency converges on the first exact
receipt; changed payload or reused execution identity conflicts. There is no
current projection because a command/receipt pair has no mutable latest state.
No legacy command is inferred or backfilled. Group and execution-result
persistence, Candidate issuance, and production discovery wiring remain absent.

PR34-B.3 adds `discovery_collected_observation_history`,
`discovery_finalized_group_history`, and
`discovery_finalized_group_members`. Each observation is bound by foreign key to
a previously committed command execution and preserves the complete immutable
Product, Collector provenance, optional explicit Market identity, observation
time, and schema version in deterministic JSON. Source marketplace/item is
indexed but not unique: repeated observations of one listing require distinct
observation IDs and remain independent facts.

Each finalized group belongs to one committed execution. Its ordered IDs are
stored both as deterministic JSON and as normalized member rows with contiguous
positions, per-group observation uniqueness, and observation foreign keys.
Save validates that every member exists in the same execution and that the
representative is a member. Observation membership is not globally exclusive;
one observation may belong to multiple finalized groups. Membership fingerprint
is indexed rather than unique because the Domain query contract permits multiple
opaque group IDs for the same immutable membership fact.

Observation save and Group-plus-members save each use their own
`BEGIN IMMEDIATE` transaction. Exact ID/payload replay adds no rows; changed
payload conflicts. All three tables reject UPDATE and DELETE. They have no
current projection because they contain immutable historical facts. Command and
receipt are already committed before these transactions; DiscoveryExecutionResult
and zero-result completion persistence remain deliberately absent.

PR34-B.4 adds `discovery_execution_result_history`, with one immutable row per
unique command ID and execution ID. Its composite foreign key binds the result
to the exact committed command/execution pair. The row preserves ordered
finalized Group IDs, an explicit zero-result flag, Domain-supplied completion
time, fixed schema version, and deterministic Domain fingerprint. Non-zero
results are accepted only when every referenced Group exists in the same
execution; an empty ordered tuple is authoritative successful zero-result
completion.

Result save uses `BEGIN IMMEDIATE`, one history INSERT, and COMMIT. Exact
command/fingerprint replay returns the original result without regenerating
time or fingerprint; changed completion facts conflict. UPDATE and DELETE are
blocked and no current projection is created. Result reads validate command
identity, Group lineage, zero-result consistency, schema version, and
fingerprint without opening write transactions. Candidate issuance and
production discovery wiring remain absent.

That final sentence is the historical PR34-B.4 scope statement. Subsequent
production wiring is summarized in `Current Implementation Status` above.

## ADR-0067 PR5 Discovery Screening Completion Foundation

PR5 adds three append-only Discovery tables without changing existing result
rows or production composition:

- `discovery_screening_evaluation_history` stores one canonical PR4 evaluation
  payload and integrity fingerprint per execution/finalized-Group identity;
- `discovery_screening_ranking_publication_history` stores exactly one canonical
  ranked/not-ranked publication and fingerprint per command/execution; and
- `discovery_screening_completion_binding_history` binds the exact execution
  result schema/fingerprint to the publication ID/fingerprint and explicit
  `RECORDED` state.

The composite repository adds unique parent indexes needed for exact composite
foreign keys, enables SQLite foreign keys, and commits evaluations,
publication, `discovery_execution_result_history`, and binding through one
connection and one `BEGIN IMMEDIATE` transaction. UPDATE and DELETE are blocked
on all three new histories. Identity/query-critical lineage stays in columns;
the authoritative screening semantics remain in the PR4 canonical JSON rather
than being duplicated into convenience columns.

Reads reserialize reconstructed values to require canonical payloads and
revalidate Domain fingerprints, command/execution identity, finalized-Group
membership fingerprints, publication evaluation references, result binding,
and zero-result semantics. There is no current projection, ranking backfill, or
synthetic screening for an existing unbound v1 result. PR6 owns production
construction, composition, and runtime-free screening replay.

## Opportunity Candidate Issuance

`opportunity_candidate_history` stores exactly one immutable Candidate per
`(discovery_command_id, finalized_group_id)` with opaque Candidate ID, explicit
discovery reference, execution lineage, initial issuance time, schema version,
and subject fingerprint. `opportunity_candidate_context_history` is a one-to-one
Candidate foreign-key table preserving the complete explicit Market identity,
Discovery command/execution context, request time, and context version.

`opportunity_candidate_issuance_receipts` stores one immutable receipt per
issuance command. Candidate ID is deliberately non-unique in this table, allowing
multiple alias receipts to reference the same Candidate. Command fingerprint
includes subject intent plus request time; subject fingerprint excludes command
and result values and identifies the Candidate provenance. Candidate ID,
Candidate issuance time, and receipt commit time are never fingerprint inputs.

Initial issuance uses one `BEGIN IMMEDIATE` transaction for Candidate, Context,
and Receipt. An equivalent command for an existing Group validates the same
authoritative Discovery lineage and stores only a new alias Receipt. Concurrent
initial writers converge to one Candidate/Context and one receipt per valid
issuance command. All tables reject UPDATE and DELETE and have no current
projection. No Candidate is backfilled and no Opportunity lifecycle is created.
# PR34-E Candidate Promotion

`opportunity_candidate_promotion_history` is an immutable one-to-one bridge from
persisted Candidate to Validation-created Opportunity. Candidate ID and
Opportunity ID are independently unique. It stores exact Discovery and Market
identity provenance plus the initial promotion command and subject fingerprint.

`opportunity_candidate_promotion_receipts` is append-only and keyed by promotion
command ID. Multiple exact-subject alias receipts may reference the same binding.
Both tables reject UPDATE and DELETE. Initial promotion is committed in the same
`BEGIN IMMEDIATE` transaction as lifecycle current/history, Validation admission
snapshot, and Opportunity market identity binding. No current projection or
Snapshot-chain placeholder is created.

## Candidate Product Observation Snapshot history (PR35-B)

`product_observation_snapshot_history` stores one immutable Product Observation
Snapshot v2 per opaque Snapshot ID. It references `opportunity_candidate_history`,
duplicates the Candidate discovery reference for corruption checks, and stores
canonical JSON for complete Market identity, Product fields, and Collector
provenance plus observation time, schema version, integrity fingerprint, and
insertion time. UPDATE and DELETE triggers enforce append-only history.

The fingerprint is not unique: different Snapshot IDs may record repeated
observations of the same Product/source. There is no current projection and no
Price, Economics, Safety, or handoff row is created.

## Candidate PriceIntelligence Snapshot history (PR35-C)

`price_intelligence_snapshot_history` stores one immutable Analyzer fact per
opaque Price Snapshot ID. It preserves Candidate/discovery reference, canonical
Market identity JSON, ordered Product Snapshot ID JSON, Analyzer version,
currency, every Decimal price result as text, stability, sample size,
timezone-aware generation time, schema version, integrity fingerprint, and
insertion time.

Save validates every referenced Product Snapshot against its authoritative
history before insert. UPDATE and DELETE are blocked. Fingerprint and cohort are
not unique business keys, and no current projection exists.

## Opportunity EconomicsCalculation Snapshot history (PR35-D)

`economics_calculation_snapshot_history` stores immutable Opportunity-scoped
calculation facts. It references lifecycle Opportunity, Candidate/Opportunity
promotion binding, and Verified Economics Opportunity source. Canonical JSON
preserves calculation results, profitability, parameters, and Economics analysis;
Decimal values are text. Analysis and full Snapshot fingerprints are both stored.

The calculator contract contains no authoritative Price Snapshot ID, so this
table deliberately has no inferred Price reference. UPDATE and DELETE are
blocked, repeated calculations use distinct Snapshot IDs, and no current
projection exists.

## Product Snapshot owner source binding (PR35-E1)

`product_snapshot_source_binding_history` links each Product Snapshot to its
exact persisted collector observation, Candidate, and first capture command.
`(candidate_id, collected_observation_id)` is unique. The append-only
`product_snapshot_capture_receipts` table stores command fingerprint, ordered
Snapshot IDs, Candidate, commit time, and schema version. Snapshot rows, source
bindings, and receipt share one `BEGIN IMMEDIATE`; neither table has a current
projection.

## Price Intelligence analysis receipts (PR35-E2)

`price_intelligence_analysis_receipts` stores command ID/fingerprint, Candidate,
finalized group, resulting Price Snapshot ID, exact ordered Product Snapshot IDs,
Analyzer version, fallback multiplier, and request/generation/commit timestamps.
The receipt and Price Snapshot history row share one `BEGIN IMMEDIATE` transaction.
UPDATE and DELETE are blocked, and no current projection is created.

## Economics calculation owner receipts (PR35-E3)

`economics_calculation_snapshot_history` v3 adds exact Candidate ID and
PriceIntelligence Snapshot ID to the Opportunity-scoped calculation fact.
`economics_calculation_receipts` preserves command/source IDs, promotion binding,
Price analysis command, Verified Economics source, resulting Snapshot,
calculation version, fingerprint, and request/generation/commit timestamps.
Snapshot and receipt share one `BEGIN IMMEDIATE`; UPDATE/DELETE are blocked and
no v2 migration or backfill is performed.

## Complete Opportunity Snapshot Chain binding (PR35-E4)

`opportunity_snapshot_chain_binding_history` is the append-only authoritative
chain fact. It stores the promotion bridge, Candidate and Opportunity IDs, chain
version, ordered Product IDs, exact Price/Economics/Verified source IDs, full
Market identity, command, timestamp, schema, and integrity fingerprint.

`opportunity_snapshot_chain_product_members` normalizes the ordered Product
cohort by `(binding_id, position)` and preserves Product Snapshot foreign-key
membership. `opportunity_snapshot_chain_binding_receipts` stores deterministic
command replay facts and permits alias commands to reference the same binding.
All three tables block UPDATE/DELETE and commit in one `BEGIN IMMEDIATE`. No
current projection, migration, backfill, or latest-source query exists.

## Operational Production Safety evaluation (PR36-A)

`production_safety_evaluation_history` stores immutable versioned engine results.
`production_safety_evaluation_provenance` binds each result to exact chain,
promotion, Candidate, selected Product, Price, Economics, Verified Economics, and
Market identity facts. `production_safety_evaluation_receipts` supports exact
command replay and alias commands. These append-only tables reject UPDATE/DELETE.

`production_safety_evaluation_current` is a controlled projection advanced only
inside the evaluation transaction. It is not a latest-source inference mechanism.
The legacy `production_safety_snapshots` admission table is unchanged.
