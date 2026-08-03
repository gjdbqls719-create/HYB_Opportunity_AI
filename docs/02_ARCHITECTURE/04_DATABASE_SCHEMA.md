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
