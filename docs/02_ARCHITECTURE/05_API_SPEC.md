# HYB API Specification

## Domestic Selling Opportunity Admission API

`POST /api/v1/opportunities/{source_opportunity_id}/domestic-selling-admissions`
admits one exact persisted foreign/source Opportunity O1 as the source of a
distinct KR domestic-selling Opportunity O2. The strict request contains the
command ID, exact source Product Snapshot ID, exact KR listing or canonical-
product Market identity, explicit product-equivalence confirmation and evidence,
operator ID, verification/request times, and supported policy identity/version.
O2 identity, admission identity, lifecycle, binding, and server times are not
caller fields.

The response is serialized from the committed or restart-reconstructed
publication and includes the O1/O2 identities, admission ID, O2 `DISCOVERED`
version 1 lifecycle, exact KR Market binding, equivalence verification, policy,
timestamps, receipt versions, and replay state. Fresh creation returns 201,
exact replay returns 200, command/cardinality/lineage conflict returns 409,
missing source facts return 404, invalid request or policy facts return 422, and
bounded SQLite failure returns 503 without storage details.

This is a Founder-operated local/private boundary. `operator_id` is retained as
a caller-supplied factual audit value; the route does not provide authentication,
authorization, or multi-user security. It does not create Sourcing, Market
Validation, Economics, Capital, or execution facts automatically.

## Conservative Economics API

`POST /api/v1/opportunities/{opportunity_id}/conservative-economics` executes
the existing Conservative Economics authority against one exact persisted
`EconomicsSourceComposition`. The strict request contains `command_id`, the
exact `source_composition_id`, timezone-aware `requested_at`, and an explicit
scenario name, version, assumption owner, and Decimal `sale_price_factor`.
There is no default haircut or latest-source lookup. Result identity,
calculation/commit times, policy identity/version, and all financial outputs are
server-owned and rejected as extra request fields.

The response is serialized from the committed or restart-reconstructed result
and receipt. It preserves exact Opportunity/source lineage, scenario manifest,
policy, evidence, Decimal unit economics, ordered blockers, schema versions,
and replay status. The only ROI field is
`conservative_acquisition_roi`; legacy ROI aliases and Capital readiness or
investment recommendations are absent. A committed `BLOCKED` result and a
CALCULABLE result with negative economics are both successful business results.

Fresh commits return 201 and exact replay returns 200 without new identity,
clock calls, or rows. Missing exact source returns 404, Opportunity/source or
changed-command conflict returns 409, DTO/Domain validation returns 422, and
bounded persistence failure returns 503 without SQLite details. The endpoint
does not call legacy Economics calculators, mutate its exact source, or perform
Capital Readiness/Gate/approval.

## Founder-Assisted Sourcing Authority API

`POST /api/v1/sourcing/admissions` commits one Founder-verified Supplier,
Sourcing Product, quote revision, selling-product lineage, Product Match
Verification, and evidence graph. `POST
/api/v1/sourcing/admissions/{admission_id}/quote-revisions` appends the next
immutable quote revision while retaining Admission, Supplier, Sourcing Product,
quote, and verified-match identities.

Requests contain only caller factual data, including command ID, requested and
verified times, exact selling lineage, supplier/product references, explicit
KNOWN/UNKNOWN/NOT_APPLICABLE commercial facts, and evidence. Sourcing opaque
identities, `admitted_at`, and `committed_at` are server-owned and rejected as
extra input. Decimal amounts are JSON strings. Responses are serialized from
the committed or reconstructed authoritative Domain result rather than echoed
request data.

The legacy Candidate-Promotion lineage object is accepted unchanged. An
additive domestic variant is selected explicitly with
`{"kind":"domestic_selling_admission","domestic_selling_admission_id":"..."}`.
No nullable-field inference is used. The Application reconstructs the exact O1,
O2, KR Market, source Product Snapshot, and equivalence provenance from that
persisted admission; callers do not repeat those claims. The resulting Sourcing
Admission is owned by O2 and its response exposes the domestic lineage kind and
exact admission reference. Existing `VERIFIED_MATCH` Supplier Product Match is
still mandatory and is not implied by domestic product-equivalence confirmation.

Fresh commits return 201 and exact restart-safe replay returns 200 without new
identities, clocks, or rows. Changed command payloads and revision conflicts
return 409, missing Admission returns 404, DTO/Domain validation returns 422,
and bounded persistence failures return 503 without raw SQLite details. The
routes do not run Economics, Capital policy, matching algorithms, OCR, or
supplier discovery/deduplication.

## Discovery Result Read API

`GET /api/v1/discovery/executions/{discovery_execution_id}` returns the
persisted `DiscoveryExecutionResult`. `GET
/api/v1/discovery/executions/{discovery_execution_id}/finalized-groups`
returns its Finalized Groups in the exact result order.

Each Finalized Group read item includes a Founder-facing representative
observation preview loaded by the persisted
`representative_observation_id`. The preview copies only `title`, `image_url`,
`marketplace`, `price`, `currency`, and `url` from the immutable collected
Product observation. `observation_count` is the persisted Group membership
count. The read model does not calculate a price range, score, minimum,
maximum, or other aggregate. A committed zero-result returns an empty Group
tuple.

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

Production finalization requires exactly one persisted Opportunity–Review binding before source composition. The binding's Opportunity ID, discovery reference, schema, and complete Market identity must match the authoritative Opportunity and Market identity records; a missing or conflicting binding returns HTTP 409 and writes no composition. The binding is a finalization prerequisite rather than a field in `DecisionCompositionSnapshot`: the existing manifest continues to preserve the exact selected HUMAN_VERIFIED External Signal IDs, while isolated legacy finalizers that do not opt into the production Review repository retain their compatibility contract.

## Founder Review Read API

`GET /api/v1/reviews` returns a deterministic list DTO with `items` and `total_count`. `GET /api/v1/reviews/{session_id}` returns one Session summary or HTTP 404 when no authoritative current projection exists. Persistence and malformed-storage failures return HTTP 503.

Each item contains `session_id`, `status`, `revision`, `candidate_count`, `pending_count`, `completed_count`, `created_at`, `started_at`, `completed_at`, and `schema_version`. `completed_count` counts APPROVED, CORRECTED, and SKIPPED Candidates. The API never exposes the ReviewSession aggregate and delegates reads exclusively to `ReviewSessionQueryService`; handlers perform no SQL, repository access, transaction, or Domain transition.

## Founder Review Start / Cancel API

`POST /api/v1/reviews/{session_id}/start` starts an authoritative OPEN ReviewSession. The request contains `expected_revision`, `command_id`, `operator_id`, and timezone-aware `started_at`. `POST /api/v1/reviews/{session_id}/cancel` cancels an allowed Session state and additionally requires non-empty `reason` and timezone-aware `cancelled_at`.

Both endpoints delegate exclusively to `ReviewWorkflowService` using the production ID/revision command boundary. The handlers do not load repositories directly, execute SQL, calculate revisions, or reproduce Domain transition rules. Successful commands and identical command replays return HTTP 200 with the existing immutable `ReviewSessionResponseDTO`. Missing Sessions return 404; revision, command, operator, and transition conflicts return 409; malformed input and naive timestamps return 422; persistence, projection, commit, malformed-storage, and SQLite failures return 503.

Start writes only ReviewSession history/current and its command Receipt. Cancel additionally writes immutable Cancel metadata. Neither endpoint may modify Verification, External Signal, Opportunity Lifecycle, Decision, or Dashboard facts.

## Trusted Review Create API

`POST /api/v1/reviews` admits a trusted ReviewSession and returns HTTP 201 with `ReviewSessionResponseDTO`. The request requires `session_id`, `artifact_id`, non-empty `candidate_ids`, `operator_id`, timezone-aware `created_at`, `command_id`, and a non-empty `contexts` collection. Every Context contains its Candidate ID, complete `MarketObservationIdentity`, signal name/direction, artifact identity, and timezone-aware creation time.

The optional `opportunity_id` creates an authoritative immutable Opportunity–Review binding in the same transaction. The Opportunity and its Market Identity binding must already exist, and every supplied Context identity must exactly match that authoritative identity. Missing sources return 404, identity or duplicate binding conflicts return 409, and persistence failures return 503. Omitting `opportunity_id` preserves legacy unbound Review admission.

The endpoint constructs the existing `CreateReviewSession`, `ReviewCommandContext`, and market identity values and delegates to `ReviewWorkflowService`. The Application boundary requires Context Candidate IDs to match the Session Candidate set exactly. Existing repository validation remains authoritative for Candidate existence, Session membership, artifact identity, and immutable Context conflicts.

Create Receipt, Session history/current, and Context history/current are committed in one SQLite transaction. An identical command and payload returns the exact HTTP 201 DTO after restart without additional facts. Duplicate Sessions, changed command payloads, Context conflicts, and untrusted Candidate/Context admission return 409; malformed input and naive timestamps return 422; persistence and commit failures return 503. The handler contains no SQL, transaction, revision calculation, or Domain transition logic.

## Founder Review Write API

`POST /api/v1/reviews/{session_id}/approve` and `/correct` require `candidate_id`, `expected_revision`, `command_id`, `verification_id`, `operator_id`, timezone-aware `verified_at`, and `signal_id`; optional `comment` and confidence defaulting to 1 are supported. Correct additionally requires `corrected_value`. Market identity, signal name, and signal direction are never accepted from the caller and come from the persisted authoritative `ReviewCommandContext`.

`POST /api/v1/reviews/{session_id}/skip` requires Candidate ID, expected revision, command ID, operator, non-empty reason, and timezone-aware skip time. It writes no Verification or External Signal. `POST /api/v1/reviews/{session_id}/complete` requires expected revision, command ID, operator, and timezone-aware completion time; the existing Domain rule rejects completion while Candidates remain pending.

All four endpoints return HTTP 200 with `ReviewSessionResponseDTO` and delegate exclusively to `ReviewWorkflowService`. Approve/Correct atomically persist Verification, External Signal, Receipt, and Session transition. Skip and Complete atomically persist only their Receipt and Session transition. Identical commands replay the committed result after restart without writes. Missing Sessions return 404; revision, command, operator, transition, membership, and duplicate conflicts return 409; malformed input and naive times return 422; persistence, projection, commit, and SQLite failures return 503 without raw SQLite details.

## Founder Review UI and Detail Read API

`GET /reviews` renders the Founder Review Queue and reads `GET /api/v1/reviews`. `GET /reviews/{session_id}` renders the operational detail page and reads `GET /api/v1/reviews/{session_id}/detail`. Page GET requests never execute workflow commands; every mutation requires an explicit native button submission and is followed by an authoritative detail refetch.

`GET /opportunities` and `GET /opportunities/{opportunity_id}` render the operational Opportunity list and detail workflow. Their read endpoints are `GET /api/v1/opportunities` and `GET /api/v1/opportunities/{opportunity_id}/review-detail`, composed from the existing Validation Queue subject, Opportunity Market Identity binding, Opportunity–Review binding, ReviewSession projection, and OCR Candidate ledger current projection.

The Opportunity Detail form never infers Candidate ownership from text, Artifact ID, or Market identity. It presents authoritative ledger Candidates for explicit operator selection, requires one shared authoritative Artifact, takes explicit signal name/direction, and submits the existing trusted Review Create request with `opportunity_id` and the server-provided Opportunity Market identity. Successful creation navigates to `/reviews`. When a binding already exists, the read DTO exposes that Review and the UI offers only its detail link; the persistence boundary rejects a second bound Review.

`GET /api/v1/opportunities/{opportunity_id}/decision-readiness` reports read-only source readiness for Opportunity Market Identity, Opportunity–Review binding, Verified Economics, Production Safety, Competition assessment, Demand assessment, bound External Signals, and the latest Decision Composition. It validates only persisted identity and supported schema/policy versions; it never reruns economics, safety, competition, demand, or Decision formulas. Required missing/error sources produce blocking reasons and disable finalization. External Signals are optional when none are bound.

Opportunity Detail renders the readiness result and enables its explicit Finalize button only when every required source is ready. Clicking performs the existing Decision Composition POST, then refetches readiness and the Decision Dashboard. Page GET and readiness GET never finalize. HTTP 409 reports duplicate/conflicting provenance truthfully; 404, 422, and 503 remain bounded without persistence internals.

For local operational validation only, `python -m app.founder_review_validation --database <new-path> --confirm-local-demo` creates a labelled, isolated demo SQLite database and executes the existing Review Application commands. It refuses the production default database and existing files. `--prepare-only` stops after trusted Candidate, Context, and Session admission for browser-driven mutation. This is not an OCR ingestion endpoint and does not create or infer an Opportunity identity.

`python -m app.founder_review_validation_server --database <demo-path>` serves the existing web composition root against that explicit local validation file. It also refuses the default DB and missing files; it does not seed on startup.

The detail read DTO preserves Session Candidate order and combines the authoritative Session projection, OCR Candidate ledger entry, persisted Review Command Context, optional Skip metadata, and immutable Artifact metadata. It exposes raw/normalized OCR values, confidence, Candidate status, signal context, artifact ID/origin/source/MIME/dimensions/capture time, and explicitly reports `preview_available: false`. Artifact bytes remain external and no binary retrieval or image URL route exists.

The vanilla JavaScript client renders API values with `textContent`, uses the current authoritative revision, and retains command ID, command timestamp, Verification ID, Signal ID, and exact payload across failed retries. A successful command clears retry state and refetches detail. HTTP 404/409/422/503 states receive bounded user-facing messages; raw persistence details are never rendered.
## Verified Economics operational admission

`POST /api/v1/opportunities/{opportunity_id}/verified-economics` admits the existing
`VerifiedEconomicsInput` as the Opportunity's single immutable authoritative snapshot.
Opportunity eligibility is established by the exact persisted non-archived lifecycle
and immutable Market binding, not by Validation Queue membership. A Domestic Selling
O2 therefore submits its own new Economics facts through this route without copying or
relabeling O1 Economics and without creating a queue admission snapshot.
All money amounts and rates are JSON strings so Decimal scale is preserved. Every input
contains its existing evidence status, source, optional reference, and optional aware
`observed_at`. The command additionally requires `command_id`, `operator_id`, and an aware
`snapshot_at`; clients cannot supply readiness, decision, formula, or schema metadata.

The first commit returns 201. An exact restart-safe replay returns 200 with the same DTO.
Missing Opportunities return 404, existing snapshot or changed-command conflicts return
409, malformed/domain-invalid input returns 422, and bounded persistence failures return
503.

In the production Founder Journey this admission is an explicit prerequisite between
Candidate Promotion and Economics Calculation:

```text
Candidate Promotion
    -> Verified Economics Admission
    -> Economics Calculation
    -> Complete Snapshot Chain
```

The Promotion response supplies the authoritative `opportunity_id` used in the admission
path. Economics loads the immutable Verified Economics snapshot by that same Opportunity
identity and returns 404 when it is absent; it never creates or infers the source. The
Opportunity Detail page exposes the admission form, and Decision Readiness reports the
persisted source as `missing`, `ready`, or `error` without performing admission or
calculation.

## Competition operational admission

`POST /api/v1/opportunities/{opportunity_id}/competition-observations` accepts only an
authoritative raw `CompetitionObservation`, its `MarketEvidence` provenance, and command
metadata. The observation identity must exactly equal the Opportunity Market Identity.
The Opportunity must have an exact non-archived lifecycle, but it need not be a Validation
Queue member; this permits an admitted O2 while retaining the same immutable identity
comparison and creating no queue snapshot.
Count metrics are JSON integers; price metrics and confidence are exact Decimal strings.
Observation/evidence/assessment schema and Competition policy versions are server-owned.

The server reuses `analyze_competition`; clients cannot submit level, confidence result,
availability, freshness, readiness, or Decision metadata. Observation history/current,
assessment history/current, and the command receipt are atomic. First commit returns 201;
exact replay returns 200. Missing Opportunity returns 404, identity/provenance/command
conflicts return 409, malformed domain input returns 422, and bounded infrastructure
failures return 503.
## Demand operational admission

`POST /api/v1/opportunities/{opportunity_id}/demand-observations` accepts an authoritative
raw `DemandObservation`, metric-level `MarketEvidence`, and command metadata. Identity must
exactly equal the Opportunity Market Identity. Counts/ranks are JSON integers; rating,
sales proxy, and confidence use exact Decimal strings. Schema and policy versions are
server-owned.

The Opportunity eligibility rule is the same exact non-archived lifecycle plus immutable
Market binding used by Competition; Validation Queue membership is neither inferred nor
created for O2.

The server reuses `analyze_demand`; clients cannot provide demand/popularity level, review
quality result, confidence result, availability, freshness, readiness, or Decision metadata.
Observation history/current, assessment history/current, and receipt are one transaction.
First commit returns 201, exact replay 200, missing Opportunity 404, identity/provenance/
command conflict 409, malformed domain input 422, and bounded infrastructure failure 503.

## Domestic Market Validation production entry

`POST /api/v1/opportunities/{opportunity_id}/domestic-market-validations` submits one
explicit validation command against exact persisted Competition observation/assessment and
Demand observation/assessment IDs. The server reconstructs the exact non-archived
Opportunity lifecycle and immutable KR Market binding, verifies that both source pairs have
that identity, and delegates all evidence, provenance, timing, completeness, and state
decisions to `ValidateDomesticMarketForCapital`. It never selects latest sources, reads
Verified Economics, creates Validation Queue membership, or creates Capital state.

The caller supplies factual Founder/operator review inputs: `operator_id`, ordered
`reviewed_source_ids`, `current_use_confirmed`, `verified_at`, `requested_at`, and the
current policy name/version. This private Founder-operated MVP has no authentication or
multi-user trust enforcement yet. The caller cannot submit an assessment ID, final state,
blocking reasons, evaluation time, or commit time; `VALIDATED_FOR_CAPITAL` and `BLOCKED`
are Application-derived committed outcomes and both are successful responses.

Fresh commit returns 201 and exact replay returns 200 with the original identity, manifest,
state, reasons, and timestamps. Missing Opportunity or exact source returns 404; changed
command or Opportunity/source/Market lineage conflict returns 409; malformed request or
domain validation returns 422; bounded persistence failure returns 503 without SQLite
details. The response exposes the assessment ID, exact Opportunity/KR Market and source
manifest, ordered reasons, operator verification facts, policy/times/schema versions, and
replay indicator, but no internal fingerprint or SQLite payload.

## O2 acquisition and authoritative Economics production chain

CR-1B5D2H exposes the existing exact-source financial authorities through six
independent request-scoped boundaries:

- `POST /api/v1/opportunities/{opportunity_id}/sourcing-economics-bindings`
- `POST /api/v1/opportunities/{opportunity_id}/landed-cost-compositions`
- `POST /api/v1/opportunities/{opportunity_id}/shipping-allocation-authorities`
- `POST /api/v1/fx-observations`
- `POST /api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations`
- `POST /api/v1/opportunities/{opportunity_id}/economics-source-compositions`

Every Opportunity-scoped route derives the complete `OpportunityIdentity` from its
named persisted source and requires the path Opportunity to match. O2 works through
the same generic owners and repositories as legacy Candidate sourcing; O1 is never a
fallback. Each boundary commits independently, uses exact IDs only, and returns 201
for a fresh authority or 200 for an exact replay. Missing named sources return 404,
changed commands or lineage/source-manifest conflicts return 409, invalid factual
input returns 422, and bounded persistence failures return 503.

The allocation request is an explicit Founder/operator fact. An `UNSPECIFIED`
shipping component remains `UNRESOLVED` unless the caller names an effective basis;
`PER_ORDER` also requires an explicit denominator, while
`PER_QUOTED_QUANTITY` may use only the exact composition quoted quantity. No MOQ,
latest allocation, or default basis is inferred. `UNRESOLVED` is a successful 2xx
authority result, but it cannot be consumed by normalization.

FX admission preserves the exact Decimal-string rate, pair, observation time and
provenance. It performs no provider lookup or inverse-observation fabrication.
Normalization takes ordered exact allocation and FX IDs plus an explicit target
currency; a same-currency path requires no fake FX observation. All financial values
are serialized as Decimal strings.

Economics Source Composition combines one exact normalization with the exact O2
Verified Economics snapshot time/schema and excludes legacy purchase/shipping fields
to prevent double counting. `READY` and `BLOCKED` remain successful business results.
The existing Conservative Economics endpoint consumes the resulting composition
without formula changes. Critical Cost is not an input to normalization or source
composition.

## Critical Cost and Capital Readiness production chain

CR-1B5D2J exposes the existing authorities through two independent,
request-scoped boundaries:

- `POST /api/v1/opportunities/{opportunity_id}/critical-cost-assessments`
- `POST /api/v1/opportunities/{opportunity_id}/capital-readiness-assessments`

The Critical Cost route always creates the current v2 contract. The caller names
one exact Landed Cost Composition, Acquisition Cost Normalization, and Verified
Economics Opportunity/time/schema tuple. Allocation and FX IDs are not caller
claims: the owner reconstructs and validates them from the exact normalization
manifest. The response exposes the committed assessment identity, O2 and exact
Sourcing/Quote/Verified Economics lineage, ordered reasons, normalization,
allocation and FX IDs, policy/schema/times, and replay state. `COMPLETE` and
`INCOMPLETE` are both successful authoritative results.

The Capital Readiness route accepts exact persisted Conservative Economics,
Domestic Market Validation, and Critical Cost assessment IDs. Its production
entry requires all three terminal sources to have the route Opportunity, then
delegates reconstruction of the complete Economics/Normalization/Sourcing
manifest, Quote validity, and deterministic state to `EvaluateCapitalReadiness`.
It never recalculates any terminal source or selects latest data. The response
includes both the Economics-manifest normalization and the Critical Cost
normalization so an exact mismatch remains visible as the existing
`SOURCING_LINEAGE_MISMATCH` blocker. `READY_FOR_CAPITAL_REVIEW` and `BLOCKED`
are both successful results; negative but calculable Economics is not rejected.

Fresh commits return 201 and exact replay returns 200 without reevaluation or
new identities/times/rows. Missing exact sources return 404, changed commands or
route/source lineage conflicts return 409, invalid requests return 422, and
bounded persistence failures return 503 without SQLite details. Each route owns
one SQLite connection and closes it on every outcome. Historical Critical Cost
v1 and Capital Readiness v1 replay remain unchanged. These routes do not expose
Capital Gate, quantity, capital facts, Founder approval, or execution.

# Operational Production Safety

`GET /api/v1/opportunities/{opportunity_id}/production-safety-evaluations`
returns persisted complete bindings, ordered Product metadata, and the current
operational evaluation. It is read-only and performs no source selection.

`POST /api/v1/opportunities/{opportunity_id}/production-safety-evaluations`
accepts `command_id`, `snapshot_chain_binding_id`,
`selected_product_snapshot_id`, and timezone-aware `requested_at`. Initial commit
returns 201; exact replay returns 200. Missing Opportunity/chain/Product is 404,
lineage or command conflict is 409, malformed input is 422, and genuine
persistence failure is 503. Raw SQLite details are never returned.
