# HYB API Specification

API는 Engine 외부 계층이다.

API
↓
Service
↓
Engine
↓
Marketplace / Storage

Route에 분석 로직을 넣지 않는다.

## Decision Composition Finalization

`POST /api/v1/opportunities/{opportunity_id}/decision-compositions` explicitly finalizes one immutable production Decision Composition and returns HTTP 201. The optional request fields are `external_signal_ids`, timezone-aware `generated_at`, and `requested_by`; `requested_by` is an audit hint and is not persisted by the current snapshot contract. Omitted or null signal IDs select all latest HUMAN_VERIFIED series, while an empty list selects none.

The endpoint delegates all source selection, metadata, provenance, versioning, and atomic persistence to the application/repository boundaries. It writes only `decision_composition_history` and `decision_composition_current`. Repeated identical provenance returns HTTP 409. The existing Dashboard GET remains read-only and returns HTTP 200 after successful finalization.

## Founder Review Read API

`GET /api/v1/reviews` returns a deterministic list DTO with `items` and `total_count`. `GET /api/v1/reviews/{session_id}` returns one Session summary or HTTP 404 when no authoritative current projection exists. Persistence and malformed-storage failures return HTTP 503.

Each item contains `session_id`, `status`, `revision`, `candidate_count`, `pending_count`, `completed_count`, `created_at`, `started_at`, `completed_at`, and `schema_version`. `completed_count` counts APPROVED, CORRECTED, and SKIPPED Candidates. The API never exposes the ReviewSession aggregate and delegates reads exclusively to `ReviewSessionQueryService`; handlers perform no SQL, repository access, transaction, or Domain transition.

## Founder Review Start / Cancel API

`POST /api/v1/reviews/{session_id}/start` starts an authoritative OPEN ReviewSession. The request contains `expected_revision`, `command_id`, `operator_id`, and timezone-aware `started_at`. `POST /api/v1/reviews/{session_id}/cancel` cancels an allowed Session state and additionally requires non-empty `reason` and timezone-aware `cancelled_at`.

Both endpoints delegate exclusively to `ReviewWorkflowService` using the production ID/revision command boundary. The handlers do not load repositories directly, execute SQL, calculate revisions, or reproduce Domain transition rules. Successful commands and identical command replays return HTTP 200 with the existing immutable `ReviewSessionResponseDTO`. Missing Sessions return 404; revision, command, operator, and transition conflicts return 409; malformed input and naive timestamps return 422; persistence, projection, commit, malformed-storage, and SQLite failures return 503.

Start writes only ReviewSession history/current and its command Receipt. Cancel additionally writes immutable Cancel metadata. Neither endpoint may modify Verification, External Signal, Opportunity Lifecycle, Decision, or Dashboard facts.

## Trusted Review Create API

`POST /api/v1/reviews` admits a trusted ReviewSession and returns HTTP 201 with `ReviewSessionResponseDTO`. The request requires `session_id`, `artifact_id`, non-empty `candidate_ids`, `operator_id`, timezone-aware `created_at`, `command_id`, and a non-empty `contexts` collection. Every Context contains its Candidate ID, complete `MarketObservationIdentity`, signal name/direction, artifact identity, and timezone-aware creation time.

The endpoint constructs the existing `CreateReviewSession`, `ReviewCommandContext`, and market identity values and delegates to `ReviewWorkflowService`. The Application boundary requires Context Candidate IDs to match the Session Candidate set exactly. Existing repository validation remains authoritative for Candidate existence, Session membership, artifact identity, and immutable Context conflicts.

Create Receipt, Session history/current, and Context history/current are committed in one SQLite transaction. An identical command and payload returns the exact HTTP 201 DTO after restart without additional facts. Duplicate Sessions, changed command payloads, Context conflicts, and untrusted Candidate/Context admission return 409; malformed input and naive timestamps return 422; persistence and commit failures return 503. The handler contains no SQL, transaction, revision calculation, or Domain transition logic.

## Founder Review Write API

`POST /api/v1/reviews/{session_id}/approve` and `/correct` require `candidate_id`, `expected_revision`, `command_id`, `verification_id`, `operator_id`, timezone-aware `verified_at`, and `signal_id`; optional `comment` and confidence defaulting to 1 are supported. Correct additionally requires `corrected_value`. Market identity, signal name, and signal direction are never accepted from the caller and come from the persisted authoritative `ReviewCommandContext`.

`POST /api/v1/reviews/{session_id}/skip` requires Candidate ID, expected revision, command ID, operator, non-empty reason, and timezone-aware skip time. It writes no Verification or External Signal. `POST /api/v1/reviews/{session_id}/complete` requires expected revision, command ID, operator, and timezone-aware completion time; the existing Domain rule rejects completion while Candidates remain pending.

All four endpoints return HTTP 200 with `ReviewSessionResponseDTO` and delegate exclusively to `ReviewWorkflowService`. Approve/Correct atomically persist Verification, External Signal, Receipt, and Session transition. Skip and Complete atomically persist only their Receipt and Session transition. Identical commands replay the committed result after restart without writes. Missing Sessions return 404; revision, command, operator, transition, membership, and duplicate conflicts return 409; malformed input and naive times return 422; persistence, projection, commit, and SQLite failures return 503 without raw SQLite details.

## Founder Review UI and Detail Read API

`GET /reviews` renders the Founder Review Queue and reads `GET /api/v1/reviews`. `GET /reviews/{session_id}` renders the operational detail page and reads `GET /api/v1/reviews/{session_id}/detail`. Page GET requests never execute workflow commands; every mutation requires an explicit native button submission and is followed by an authoritative detail refetch.

The detail read DTO preserves Session Candidate order and combines the authoritative Session projection, OCR Candidate ledger entry, persisted Review Command Context, optional Skip metadata, and immutable Artifact metadata. It exposes raw/normalized OCR values, confidence, Candidate status, signal context, artifact ID/origin/source/MIME/dimensions/capture time, and explicitly reports `preview_available: false`. Artifact bytes remain external and no binary retrieval or image URL route exists.

The vanilla JavaScript client renders API values with `textContent`, uses the current authoritative revision, and retains command ID, command timestamp, Verification ID, Signal ID, and exact payload across failed retries. A successful command clears retry state and refetches detail. HTTP 404/409/422/503 states receive bounded user-facing messages; raw persistence details are never rendered.
