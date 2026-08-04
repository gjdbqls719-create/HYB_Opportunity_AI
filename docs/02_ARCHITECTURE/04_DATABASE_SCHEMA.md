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
