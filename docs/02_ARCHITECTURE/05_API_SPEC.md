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

For a Candidate-eligible representative, the same item also contains an
additive `candidate_handoff` object. It exposes the exact representative
`observation_id`, the complete `market_observation_identity`, the dedicated
`discovery_reference`, handoff `policy_name` and `policy_version`, `observed_at`,
and the external Collector `source_reference`. Decimal display fields remain
strings and all timestamps are timezone-aware. Historical or unsupported
representatives return `candidate_handoff: null`; the read never synthesizes,
backfills, or mutates handoff facts.

The Candidate POST request remains explicit. A client selects a Finalized Group
and copies the complete Market identity and discovery reference verbatim from
that exact Group's `candidate_handoff`. Candidate issuance rejects a changed
market, scope, item, observation window, reference, unsupported policy, or
cross-Group representative lineage. The response contract therefore supplies
every machine-known source value needed for Candidate admission without private
repository access, SQLite reads, URL parsing, or caller-created identity.

## Candidate Promotion v2

`POST /api/v1/candidate-promotions` supports the explicit
`contract_version = "2.0.0"` request alongside historical v1 compatibility. V2
accepts only command, Candidate, finalized Group, representative Product
Snapshot, operator, reason, requested time, and optional note. It reconstructs
the exact capture receipt, ordered Product cohort, source bindings, Candidate
Context, issuance, and representative relationship before issuing a
server-identified O1 in lifecycle state `discovered` version 1.

The v2 response returns the O1, binding, admission, capture, ordered Snapshot,
representative Snapshot, Market identity, display, lifecycle, and Founder-
selection facts. It contains no recommendation, score, ROI, or safety signal.
Display currency is copied from the representative persisted Product Snapshot;
it is not an admission or economic judgment. Fresh success is 201, exact
replay/alias is 200, missing source is 404, lineage/cardinality conflict is 409,
invalid structure is 422, and bounded persistence failure is 503.

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

## Capital execution production path

CR-1B5D2L exposes the existing Capital authorities through six independent
production commands:

- `POST /api/v1/opportunities/{opportunity_id}/intended-order-quantities`
- `POST /api/v1/deployable-capital-snapshots`
- `POST /api/v1/opportunities/{opportunity_id}/planned-acquisition-capital-requirements`
- `POST /api/v1/opportunities/{opportunity_id}/capital-gate-assessments`
- `POST /api/v1/opportunities/{opportunity_id}/founder-capital-approvals`
- `POST /api/v1/opportunities/{opportunity_id}/real-money-execution-intents`

Intended Order Quantity requires caller-owned `command_id`, exact Sourcing
Admission ID/revision, exact Quote ID/revision, positive quantity and unit,
operator, `declared_at`, and `requested_at`. It derives the complete O2 identity
from that exact Admission and never derives quantity from MOQ, quoted quantity,
or a shipping denominator.

Deployable Capital Snapshot requires `command_id`, Decimal-string `amount`,
currency, factual `as_of`, operator, and `requested_at`. Explicit zero is valid.
The server fixes semantics to `founder-declared-reserve-adjusted-v1`; the same
route creates both historical Gate snapshot A and a distinct post-Approval
snapshot B. Snapshot B must name the approving Founder as operator and satisfy
the existing Approval/confirmation/evaluation temporal rules.

Planned Requirement requires the exact Intended Quantity and Acquisition
Normalization IDs plus explicit upfront scope status `complete` or `unresolved`,
operator, verification time, and request time. The server fixes arithmetic
policy and reconstructs Landed Cost, Binding, Admission, and Quote lineage.
`calculable` and `blocked` are successful business responses; the server never
assumes that upfront scope is complete.

Capital Gate requires exact Capital Readiness, Planned Requirement, and
Deployable Capital snapshot IDs. The server fixes policy
`domestic-commerce-capital-gate/1.0.0`; callers cannot provide thresholds.
`pass`, `rejected`, and `blocked` are committed 2xx outcomes. Pass means only
eligibility for the separate Founder Approval request.

Founder Capital Approval requires an exact Gate ID, Founder ID, Decimal-string
approved amount, currency, `requested_at`, and factual `approved_at`. Only Gate
`pass` may be approved and v1 requires exact equality with the full Planned
Requirement in the authoritative currency. Approval is never automatic and is
historical authorization, not proof of transferred or spent funds.

Real-Money Execution Intent v2 requires explicit `contract_version: "2.0.0"`,
the exact Approval, Quote ID/revision, post-Approval snapshot B, quantity/unit,
Decimal-string `proposed_supplier_order_committed_amount`, Quote-currency
`supplier_order_currency`, checkout evidence reference, Founder, explicit
current confirmation, and confirmation/request times. The server reconstructs
and returns `authorized_acquisition_capital_amount/currency`; it never accepts
that authority from the caller or converts supplier money.
`ready_for_manual_execution` and `blocked` are
successful business results. Equivalent READY actions under a new command alias
the existing READY intent and return 200; a different second READY action for
the same Approval conflicts. The response preserves the exact Approval, Gate,
Requirement, Intended Quantity, Admission, Quote, current snapshot, and action
manifest needed to join back to Supplier/Product references already exposed by
the Sourcing Admission response.

All six routes use exact persisted IDs only. They do not select latest sources,
fall back to O1, or share a workflow-wide transaction. A fresh commit returns
201, exact replay returns 200, and a READY alias returns 200. Missing sources
return 404; command, O2-lineage, or READY-cardinality conflicts return 409;
invalid request/domain data returns 422; bounded persistence failure returns
503. Monetary JSON values are strings and authoritative timestamps are
timezone-aware.

This is a private Founder-operated MVP. `founder_id` and `operator_id` are
caller-provided factual audit references, not authenticated identities. HYB
authority ends at `READY_FOR_MANUAL_EXECUTION`; the Founder performs the
external purchase manually. READY does not mean ordered, paid, purchased, or
executed. `PurchaseExecutionRecord` remains the next required authority for
recording the actual commercial event. V1 payloads are accepted only for exact
historical command replay; new production writes use v2.

## Purchase Execution Record

`POST /api/v1/opportunities/{opportunity_id}/purchase-execution-records`
records the Founder-reported external purchase against one exact persisted
`READY_FOR_MANUAL_EXECUTION` v2 intent. The request requires explicit
`contract_version: "2.0.0"`, `command_id`, exact intent and Quote ID/revision,
positive actual quantity/unit, Decimal-string `supplier_order_committed_amount`,
Quote-currency `supplier_order_currency`, opaque external order reference, Founder ID,
timezone-aware `executed_at` and `requested_at`, and one or more evidence
references with timezone-aware observation times.

The server reconstructs O2 and the exact Approval/Gate/Requirement/Intended
Quantity/Sourcing/Supplier/Product/Quote chain. Quantity, unit, supplier amount/currency,
Quote, and Founder must exactly match READY. Supplier/Product identities are not
caller claims. A fresh record returns 201. Exact replay or a new command for the
identical event returns 200 with the same record; changed-command payload,
route/source mismatch, deviation, BLOCKED intent, or one-intent cardinality
conflict returns 409. Missing exact intent returns 404, invalid fields return
422, and bounded persistence failure returns 503. Money is serialized as JSON
string and all authoritative times are timezone-aware.

The response exposes record ID, O2, exact intent and Capital/Sourcing/Quote
lineage, actual facts, external reference, evidence, Founder, admission and
receipt times, policy/schema versions, and replay. The route does not place an
order, transfer funds, track shipment, admit goods receipt, update inventory,
or calculate Actual Economics. Software tests simulate Founder submission;
only a genuine Founder order and real reference/evidence can validate the
real-world procedure.

### Purchase monetary v2

ADR-0058 and CR-1B7B2A replace the v1 monetary conflation for new writes. V1
rows and exact command replay remain historical and are never migrated or
aliased to v2.

The versioned v2 Execution Intent exposes server-reconstructed
`authorized_acquisition_capital_amount/currency` separately from Founder-owned
`proposed_supplier_order_committed_amount/currency` and checkout evidence. The
v2 Purchase Execution request/response uses explicit
`supplier_order_committed_amount/currency` and exact-match those facts to the
READY v2 proposal. It will not compare CNY supplier money numerically to a KRW
cap, apply planned FX, or relabel planned capital as actual. Historical v1
requests, records, and replay retain their original contracts without aliases,
migration, or reinterpretation. Checkout drift is 409; partial or malformed v2
money is 422.

## Actual Acquisition Settlement

`POST /api/v1/opportunities/{opportunity_id}/actual-acquisition-settlements`
admits one immutable actual-acquisition settlement revision for one exact
persisted Purchase Execution Record. The request supplies `command_id`, exact
Purchase Execution Record ID, optional exact predecessor settlement ID,
explicit target currency, five canonically ordered fixed cost facts, an
explicit other-mandatory-cost scope with ordered items, operator, and
timezone-aware `requested_at`. The caller cannot submit settlement identity,
revision number, state, blocking reasons, normalized totals, or server times.

Each fixed fact explicitly states `known`, `not_applicable`, or `unknown`.
Known facts require Decimal-string batch amount, currency, settled time, and
actual evidence. Non-applicability requires evidence and carries no money.
Unknown facts never become zero. Other mandatory costs require an explicit
scope state; known items remain ordered and scoped, while an empty list is not
an implicit zero. Cross-currency facts use embedded actual payment/charge FX
provenance with no planned `FXObservation`, latest rate, provider lookup, or
implicit conversion. Same-currency facts carry no FX object.

The server reconstructs O2, quantity/unit, external order, Capital,
Supplier/Product, and exact Quote lineage from the Purchase Execution Record.
It calculates deterministic ordered reasons and returns `blocked` without final
batch/per-unit totals when facts remain unresolved. A complete revision stores
target-currency category amounts, batch total, and per-executed-unit total under
the 34-significant-digit `ROUND_HALF_EVEN` Decimal policy. Actual item amount
may factually differ from the Purchase Execution committed amount.

Revision 1 may be blocked or complete. A later revision must name the exact
blocked chain tip, preserves target currency, and cannot regress resolved facts
to unknown. COMPLETE is terminal. Fresh blocked or complete commits return 201;
exact replay returns 200. Missing Purchase Execution/predecessor returns 404;
changed commands, route/source mismatch, stale predecessor, fork, or terminal
conflict returns 409; malformed input returns 422; bounded persistence failure
returns 503. Money is serialized as strings and authoritative times are
timezone-aware.

This route does not create Goods Receipt, update inventory, mutate legacy
Actual Economics, calculate sales/profit/margin/ROI, or create Actual Outcome
or Variance.

The generated OpenAPI contract exposes the five fixed acquisition categories
and `known`, `not_applicable`, `unknown` as closed enum values. The scoped-other
container uses the same availability enum. `unknown` means unresolved and is
never a zero fallback; `not_applicable` is an evidenced factual assertion; a
known zero is supplied as Decimal string `"0"` with the evidence required by
the authority. The request schema includes a synthetic example showing exact
category order, same-currency facts without an FX object, and an unresolved
cross-currency fact without inventing conversion evidence.

## Goods Receipt

`POST /api/v1/opportunities/{opportunity_id}/goods-receipts` admits one
immutable physical receipt event for one exact persisted Purchase Execution
Record. The request requires `command_id`, exact Purchase Execution Record ID,
positive `received_quantity`, explicit matching `quantity_unit`, non-negative
`sellable_quantity` and `damaged_quantity`, one or more dedicated evidence
references, operator, and timezone-aware received, inspected, and requested
times. Optional `delivery_reference` is opaque and is neither identity nor a
deduplication key. Extra request fields are forbidden.

The server reconstructs O2, Supplier, sourcing product and external
product/option/SKU references, exact Quote revision, executed quantity/unit,
external order, Founder, and Purchase Execution provenance. It requires
`sellable_quantity + damaged_quantity == received_quantity`; zero receipt,
unclassified remainder, unit conversion, MOQ/Quote substitution, and inferred
sellable quantity are rejected. Different commands may create legitimate
partial events for the same purchase.

Before every fresh insert, the SQLite owner starts `BEGIN IMMEDIATE`, repeats
the exact replay and Purchase Execution checks, sums all committed immutable
receipt quantities for that Purchase Execution through an indexed lookup, and
requires cumulative quantity plus the new event to remain at or below executed
quantity. Event history and command receipt commit atomically. No mutable
accumulated balance or fulfilled flag exists.

A fresh event returns 201 and exact command replay returns 200 with the same
record, evidence, and historical times. Changed command, route/source or unit
conflict, and cumulative over-receipt return 409. Missing Purchase Execution
returns 404, structural input returns 422, and bounded persistence failure
returns 503. The response exposes the immutable event and reconstructed source
manifest but no marketplace or owned-inventory balance.

The route does not require or mutate Actual Acquisition Settlement, does not
change marketplace `InventorySnapshot` or legacy Actual Economics, and does not
calculate order completion, inventory balance, refunds, sale economics, Actual
Outcome, or Variance. The rebuildable owned-inventory projection consumes
sellable receipt quantities without changing this event authority.

## Owned Inventory Projection

`GET /api/v1/opportunities/{opportunity_id}/owned-inventory` is a read-only,
Opportunity-scoped projection over committed immutable Goods Receipt Records.
It has no request body or manual quantity parameters. One O2 may own more than
one exact stock key, so the response contains an ordered `positions` collection
rather than one ambiguous balance.

Each current-production v2 position key contains the exact O2 identity, source platform, Supplier ID,
sourcing product ID, external product/option/SKU references, and quantity unit.
Only complete identical keys aggregate across Purchase Executions and COMPLETE
sale windows. Position and source ordering is deterministic; every contributing
Purchase Execution, Goods Receipt, and COMPLETE Actual Sale Settlement ID is
returned with separate inbound and outbound source-event counts.

The production GET returns integer `total_received`, `total_sellable_received`,
`total_damaged_received`, `total_outbound_quantity`, and
`sellable_on_hand == total_sellable_received - total_outbound_quantity` under
policy `receipt-and-complete-sale-derived-owned-inventory` version `2.0.0` and
schema `owned-inventory-position-v2`. Only committed COMPLETE
`ActualSaleSettlement.fulfilled_outbound_quantity` contributes outbound.
BLOCKED revisions are excluded; zero-sale COMPLETE sources remain listed with
zero quantity. Historical v1 remains `receipt-derived-owned-inventory / 1.0.0`,
schema `owned-inventory-position-v1`, with outbound zero and is not
reinterpreted. No marketplace availability, reservation, adjustment, financial
amount, refund, or return adds or subtracts inventory.

An existing Opportunity with no Goods Receipt events returns 200 with an empty
positions collection and no fabricated product identity. Missing Opportunity
returns 404, exact source conflict returns bounded 409, and persistence or
reconstruction failure returns bounded 503. The request-owned connection closes
for every result. The GET performs no writes, creates no materialized inventory
table, selects no latest business source, and rebuilds the same result after
restart from immutable receipt and COMPLETE sale history. A reconstructed
negative position or COMPLETE sale without a matching exact receipt key fails
closed rather than being clamped or ignored.

## Actual Sale Settlement

`POST /api/v1/opportunities/{opportunity_id}/actual-sale-settlements` admits one
immutable actual marketplace-sale settlement revision for one exact Goods
Receipt-anchored O2/product and explicit half-open evaluation window. The first
manual validation path uses `marketplace=COUPANG`; the route performs no Coupang
network request. Extra request fields are forbidden.

The request supplies command and optional exact predecessor IDs, one exact Goods
Receipt anchor, marketplace seller/listing provenance, opaque external
report/cycle and optional ordered transaction references, timezone-aware
`period_start`/`period_end`, explicit fulfilled/cancelled/refunded/returned
integer quantities and matching unit, settlement currency, 15 canonically
ordered monetary facts, explicit other-sale-cost scope/items, payout and
reconciliation facts, finality, operator, and requested time. Money is accepted
and returned as Decimal strings. Caller state, reasons, settlement identity,
server times, inventory balance, profit, margin, and ROI are not accepted.

Each monetary fact is `known`, evidenced `not_applicable`, or `unknown`.
Canonical gross means completed merchandise proceeds after seller-funded
discount, before refunds/fees, excluding buyer shipping and collected tax.
Marketplace/payment/fixed fees, refund, cancellation reversal, return fee,
advertising, fulfillment, storage, and sale-side handling remain distinct.
Unknown material scope derives ordered BLOCKED reasons and never becomes zero.
`RECONCILED` payout is verified against ADR-0054's exact component expression;
`not_scope_comparable` preserves evidenced payout timing/scope without fabricated
equality. Cross-currency actual facts remain BLOCKED without planned FX reuse.

The server reconstructs the complete `OwnedInventoryProductKey` and eligible
Goods Receipt/Purchase Execution lineage. Only COMPLETE contributes the explicit
fulfilled outbound quantity, effective at `period_end`; BLOCKED contributes
zero. Inside one `BEGIN IMMEDIATE` transaction, persistence repeats replay,
linear revision/terminality, external reference/transaction reuse, overlapping
COMPLETE-window, and chronological inventory checks. At every outbound boundary,
cumulative COMPLETE outbound must not exceed Goods Receipt sellable quantity
with `inspected_at < period_end`. Different SKU/option keys never share stock,
and negative inventory is never clamped.

Fresh BLOCKED or COMPLETE revisions return 201, exact replay returns 200, and a
zero-fulfilled COMPLETE window is valid. Missing anchor/predecessor returns 404;
changed replay, route/product/unit, stale/fork/terminal revision, overlap,
duplicate reference, or oversale returns 409; malformed structures return 422;
bounded persistence failure returns 503. History and command receipt are
append-only, integrity checked, atomically committed, and restart-replayable.

This route does not update receipt-only Owned Inventory policy v1, Goods Receipt,
Actual Acquisition Settlement, marketplace `InventorySnapshot`, legacy Actual
Economics, Actual Outcome, or Variance. A separate small change may introduce
Owned Inventory v2 as receipts minus COMPLETE sale outbound.

The generated OpenAPI contract exposes all 15 canonical monetary categories,
the `known`, `not_applicable`, `unknown` availability enum, and the exact payout
reconciliation states `reconciled`, `not_scope_comparable`, and `unresolved`.
Payout is an independent reconciliation fact: it replaces neither canonical
components nor gross revenue and does not prove completeness. Reconciled means
the canonical expression matches; not-scope-comparable preserves a genuine
payout whose timing or scope cannot be compared exactly; unresolved blocks.
Return finality remains an explicit factual object, not an inference from payout.

The request schema includes a synthetic example covering every canonical slot.
Swagger descriptions and the operational runbook distinguish unknown, evidenced
not-applicable, and known zero without adding API-only business values.

## First controlled real-world run

The authoritative Founder procedure is
[`FIRST_REAL_WORLD_VALIDATION_RUNBOOK.md`](../05_OPERATIONS/FIRST_REAL_WORLD_VALIDATION_RUNBOOK.md).
It records the exact route order, request/response archive, non-authoritative run
manifest, ID handoffs, essential pre-purchase freeze, checkout STOP rules, and
post-purchase acquisition/sale worksheets. Most append-only command results do
not have broad list/read endpoints; therefore every first-run request and
response JSON is archived immediately. No raw SQLite recovery step is supported.

## Actual Outcome

`POST /api/v1/opportunities/{opportunity_id}/actual-outcomes` calculates and
persists one immutable cumulative Actual Outcome. The strict request contains
only `command_id`, one exact `actual_acquisition_settlement_id`, a non-empty
ordered `actual_sale_settlement_ids` tuple, and timezone-aware `requested_at`.
Caller-supplied product, Purchase Execution, receipts, quantities, money, COGS,
profit, ratios, state, resolution, reasons, identity, or server times are
forbidden.

The server reconstructs one exact O2/product/Purchase Execution, all committed
Goods Receipts for that purchase with `inspected_at < evaluation_through`, and
the complete chronological COMPLETE-sale prefix through the selected terminal
window. Omission, duplication, reordering, wrong lineage, or impossible
quantity history fails closed. A named non-COMPLETE source, currency mismatch,
or unsupported multi-purchase attribution creates a deterministic BLOCKED
result with no profitability values. Negative profit, remaining inventory, and
zero-denominator ratio unavailability remain CALCULABLE.

CALCULABLE responses expose integer executed/received/sellable/damaged/sold/
remaining/returned/unreceived quantities; six category-level acquisition
allocations and exact batch conservation; 15 sale component totals and ordered
other cost total; sale credits/costs, COGS, remaining inventory basis, damaged
loss, unreceived exposure, profit, explicit margin/ROI availability, payout
reconciliation facts, and `PARTIAL`/`FULLY_RESOLVED` resolution. All Decimal
values are strings. Customer tax, seller-funded discount, and cancellation
reversal remain traceable source facts but are not double-counted; payout is
reconciliation only.

Fresh CALCULABLE/BLOCKED results return 201 and exact command replay returns
200. Missing exact sources return 404; changed replay, prefix/lineage/quantity
conflicts return 409; malformed structures return 422; bounded persistence
failure returns 503. Equivalent exact source manifests under the same policy
alias one persisted outcome while receiving a distinct command receipt.
History, receipts, and complete canonical upstream source snapshots are
append-only and integrity checked. Reads/replay do not select latest sales,
consult current inventory, perform FX, or recalculate from current upstream
state.

This route does not mutate Acquisition/Sale Settlement, Goods Receipt, Owned
Inventory, Conservative Economics, legacy Actual Economics, or legacy
Variance. Variance v2 consumes this exact immutable result through its own
separate contract.

## Conservative vs Actual Economics Variance v2

`POST /api/v1/opportunities/{opportunity_id}/economics-variances` persists one
immutable comparison between an explicit Conservative Economics result and an
explicit Actual Outcome. The strict request contains only `command_id`,
`conservative_economics_result_id`, `actual_outcome_id`, and timezone-aware
`requested_at`; caller-supplied metrics, state, eligibility, reasons,
favorability, contributors, or server times are forbidden.

The server reconstructs the exact Economics Source Composition, Acquisition
Cost Normalization, Landed Cost Composition, Sourcing Economics Binding,
Sourcing Admission/Quote revision, Capital Requirement, Purchase Execution,
and complete Actual Outcome product key. It rejects O2, product, currency,
unit, policy, or exact-lineage disagreement and never selects latest history,
copies current values, or recalculates either source authority.

The response exposes O2/product identity, scenario and actual sale scope,
ordered eight core metrics, four aligned acquisition component comparisons,
actual-only contributors, predicted-only context, inventory/capital exposure,
comparison and calibration states/reasons, source policy/schema/timestamps,
and variance policy/schema/timestamps. Decimal values are strings. Unavailable
or scope-mismatched values are null with explicit classification and reasons;
zero sales never creates a synthetic sale price or profit-per-unit value.

Fresh source-pair results return 201; exact replay and equivalent source-pair
aliases return 200. Missing exact sources return 404; changed replay or
O2/product/currency/source conflicts return 409; malformed structures return
422; bounded persistence failure returns 503. PARTIALLY_COMPARABLE and negative
actual performance remain normal 2xx business results. History, source
snapshots, and command receipts are append-only, integrity checked, atomically
committed, restart-replayable, and concurrency safe.

This route does not mutate Conservative Economics, Actual Outcome,
Acquisition/Sale Settlement, Goods Receipt, Owned Inventory, legacy Actual
Economics, or legacy Economics Variance. It does not calibrate, train, update a
policy, execute commerce, call a marketplace, or provide UI behavior.
