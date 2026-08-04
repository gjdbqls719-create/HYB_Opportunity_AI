# HYB Database Schema

Domain Model과 Database Model은 명확히 분리한다.

관리 대상:
Product
Price History
Opportunity History
Recommendation History

Product 모델 중복 문제는 통합 대상으로 관리한다.

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
