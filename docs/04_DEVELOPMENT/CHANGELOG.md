# HYB Changelog

## PR34-D - Opportunity Candidate Issuance Persistence

- Persist one immutable Candidate and Context per Discovery command/finalized Group while allowing one immutable issuance receipt per command and multiple alias receipts to reference the same Candidate.
- Separate Candidate subject and issuance command fingerprints from generated Candidate ID, Candidate issuance time, and receipt commit time.
- Add initial Candidate/Context/Receipt and alias-only `BEGIN IMMEDIATE` transactions with authoritative Discovery lineage revalidation, phase-specific rollback errors, and append-only triggers.
- Integrate restart-safe command replay, response-loss replay, same-subject alias convergence, distinct command/subject conflicts, and separate-connection initial issuance convergence without process-local locks.
- Keep Candidate state pre-admission and leave Opportunity lifecycle, Validation Admission, Snapshot wiring, Safety, Review, Decision, Dashboard, Web/API, migration, and backfill unchanged.

## PR34-C - Opportunity Candidate Issuance Foundation

- Add immutable Candidate issuance command and result contracts that preserve distinct issuance/Discovery command identity, explicit discovery reference, explicit Candidate Market identity, request/issuance times, and fixed schema versions.
- Add a read-only `IssueOpportunityCandidate` boundary that reloads persisted command, completed result, finalized Group, and representative Observation before validating exact command/execution/group lineage.
- Require explicit LISTING or CANONICAL_PRODUCT Market identity and exact representative source marketplace/listing agreement without deriving identity or discovery reference from Group ID, Product, title, query, category, or fingerprint.
- Generate opaque `OpportunityCandidateIdentity` and `DiscoveryOpportunityContext` only after validation through injected generator and clock dependencies, without creating an Opportunity or lifecycle state.
- Deliberately add no Candidate repository, SQLite, receipt, registry, or replay cache; repeated invocation may issue another identity until a later durable issuance PR.

## PR34-B.4 - DiscoveryExecutionResult SQLite Persistence

- Persist one immutable authoritative `DiscoveryExecutionResult` per committed command/execution pair, preserving ordered finalized Group IDs, explicit successful zero-result state, Domain completion time, schema version, and deterministic fingerprint.
- Validate every non-zero Group reference against persisted same-execution finalized Groups while keeping zero-result completion explicit rather than inferred from missing rows.
- Add exact restart and response-loss replay, separate-connection concurrency, changed-result conflict, append-only triggers, deterministic reconstruction, and read-only command/execution queries.
- Distinguish result history, commit, replay conflict, identity, malformed persistence, and unsupported-version failures while containing raw SQLite errors.
- Keep Candidate issuance/receipts, Snapshot storage and wiring, Collector/grouping changes, Safety, Decision, Dashboard, Web/API, migration, and backfill unchanged.

## PR34-B.3 - Collector Observation and Finalized Group SQLite Persistence

- Persist complete immutable `CollectedProductObservation` facts against an already committed Discovery execution, including every observed Product field, Collector provenance, exact time, and optional explicit Market identity.
- Permit repeated observations of the same source listing under distinct observation IDs; source listing remains an indexed lookup rather than invented identity or uniqueness.
- Persist finalized groups with ordered normalized membership, per-member foreign keys, exact representative and policy provenance, and verified Domain membership fingerprints without imposing global observation ownership or fingerprint uniqueness.
- Use separate `BEGIN IMMEDIATE` transactions for observation and group facts with exact replay, explicit changed-payload and execution conflicts, phase-specific rollback errors, append-only triggers, deterministic restart reconstruction, and read-only queries.
- Keep DiscoveryExecutionResult, zero-result completion, Candidate issuance, Snapshot persistence/wiring, production Collector/orchestrator, Safety, Decision, Dashboard, HTTP, migration, and backfill unchanged.

## PR34-B.2 - Discovery Command SQLite Persistence

- Add file-backed `SQLiteDiscoveryCommandRepository` for exact immutable Discovery command and receipt round-trip without Collector, grouping, Candidate, Snapshot, or production discovery wiring.
- Commit command history and its one-to-one receipt in one `BEGIN IMMEDIATE` transaction, preserving distinct history, receipt, and commit errors with complete rollback.
- Enforce append-only UPDATE/DELETE triggers plus unique command/execution identity, deterministic canonical JSON reconstitution, fingerprint integrity, and explicit malformed/unsupported persistence failures.
- Make restart and response-loss replay durable; separate-connection concurrent identical commands converge on one exact receipt while changed payload and execution reuse conflict.
- Keep finalized-group/result persistence, Candidate issuance, migration/backfill, Safety, Decision, Dashboard, and all legacy production behavior unchanged.

## PR34-B.1 - Discovery Persistence Foundation

- Add immutable `DiscoveryCommandReceipt` with exact command/execution identity, canonical payload fingerprint, timezone-aware commit time, and fixed schema version.
- Add Application repository Protocols for Discovery commands, finalized groups, and command results without selecting SQLite or defining tables, triggers, migrations, or transactions.
- Add `PersistDiscoveryCommand` to validate replay, reject changed payloads, create a receipt through an injected clock, and delegate persistence without invoking collection, grouping, Economics, Safety, Candidate issuance, or Snapshot ownership.
- Preserve same-command/same-fingerprint replay, same-command/changed-fingerprint conflict, and different-command new-execution semantics at the Application boundary.
- Add explicit missing, replay-conflict, malformed-receipt, unsupported-version, and generic persistence errors while keeping infrastructure and production discovery behavior unchanged.

## PR34-B.0 - Stable Discovery Command and Finalized Group Correlation Contract

- Add immutable, versioned `DiscoveryCommand` and typed parameters covering the existing orchestrator inputs with exact Decimal, bool/int, policy, and authoritative source-reference semantics plus a deterministic payload fingerprint independent of command ID.
- Add `CollectedProductObservation` to preserve collector-owned observation/source identity, immutable Product facts, provenance, and time without changing collectors or inferring Candidate Market identity.
- Add `FinalizedProductGroup` with a server-owned opaque group reference separated from its deterministic ordered membership/policy fingerprint; list index, title, representative item, runtime hash, and current price are not identity inputs.
- Add an ordered `DiscoveryExecutionResult`, including successful zero-result semantics, and a derivable Candidate issuance replay key over command, group membership, explicit Market identity, and issuance version.
- Keep SQLite, receipts, ID generation, collector/grouping production wiring, Snapshot persistence, admission, lifecycle, Safety, Decision, Dashboard, migration, and backfill unchanged.

## PR34-A - Discovery Identity and Snapshot Ownership Timing Contract

- Add a distinct immutable `OpportunityCandidateIdentity` for one pre-admission ProductGroup candidate; issuing it does not create an Opportunity lifecycle or imply admission.
- Add an explicit `DiscoveryOpportunityContext` carrying candidate identity, listing/canonical Market Observation identity, discovery execution ID, command correlation, request time, and schema version without global or implicit context.
- Add an immutable `AdmissionSnapshotChainHandoff` that explicitly promotes one candidate to an authoritative Opportunity identity and carries the exact ordered Product, PriceIntelligence, and Economics snapshot references.
- Select candidate identity plus explicit admission promotion over pre-issued Opportunity IDs or unbound source identity, preserving current lifecycle semantics and avoiding inferred IDs or Market identities.
- Keep persistence, schemas, migrations, Snapshot writes, production wiring, Safety execution, Decision, Dashboard, formulas, grouping, and legacy backfill unchanged.

## PR31.1 - Economics Runtime Analysis Provenance Hardening

- Preserve the complete runtime Economics `analysis` mapping as a versioned, fingerprinted, deeply immutable canonical value tree with deterministic mapping order and exact bool/int, Decimal, Enum, datetime, tuple/list, and nested-mapping semantics.
- Reject arbitrary objects, sets, non-text mapping keys, cycles, non-finite numbers, naive datetimes, and unknown Enum reconstruction instead of serializing ambiguous provenance or inventing defaults.
- Align the Economics snapshot lineage name with the real Verified Economics persistence key by recording `verified_economics_opportunity_id`, not a nonexistent snapshot ID.
- Reconstruct exact disposable EconomicsCalculation and complete Production Safety runtime inputs from persisted snapshot facts without invoking the calculator, analyzer, or `assess_production_safety`.
- Add explicit unsupported analysis-value and analysis-version failure paths while keeping SQLite, schemas, migrations, backfill, formulas, rules, statuses, Decision, Dashboard, and Safety execution unchanged.

## PR33 - Production Safety Runtime Adapter Foundation

- Add disposable Product and PriceIntelligence runtime reconstruction from exact authoritative snapshot fields without analyzer, calculator, cohort, fallback, or Safety execution.
- Add exact read-only VerifiedEconomicsSnapshot loading with identity and schema validation; the current authoritative snapshot key remains Opportunity ID.
- Add a ProductionSafetyRuntimeInputs result contract and explicit missing, identity-conflict, malformed, unsupported-version, and reconstruction error taxonomy.
- PR31.1 resolves the original Economics analysis blocker through exact canonical provenance; no missing keys, defaults, formulas, or provenance are inferred.
- Keep `assess_production_safety`, ProductionSafetyAssessment persistence, API/UI/receipts, SQLite, migration, backfill, Decision, Dashboard, collectors, analyzers, calculators, rules, formulas, and statuses unchanged.

## PR32 - Production Safety Integration Foundation

- Add an immutable ProductionSafetyEvaluationContext grouping exact Product Observation, PriceIntelligence, and EconomicsCalculation snapshots with the matching Verified Economics snapshot reference.
- Validate Opportunity identity, Market Observation identity, ordered Product cohort membership, and Verified Economics lineage without adding Safety rules or formulas.
- Add a ProductionSafetySourceRepository Protocol and read-only integration service for authoritative source loading and delegated lineage validation without SQLite, transactions, migration, API, or backfill.
- Keep `assess_production_safety` unchanged and document the remaining runtime-adaptation and VerifiedEconomicsInput-loading gap instead of creating fake Product, PriceIntelligence, or EconomicsCalculation objects.
- Assign context ownership exclusively to the Production Safety Integration Layer and keep Collector, Review, Dashboard, and Decision behavior unchanged.

## PR31 - EconomicsCalculation Snapshot Foundation

- Add an immutable EconomicsCalculation snapshot contract preserving explicit Opportunity and Market Observation identities, the exact Verified Economics snapshot reference, typed calculator outputs, profitability provenance, calculation parameters/version, generation time, and schema version.
- Preserve per-unit expected sale price as revenue and represent the current calculator's absent break-even result explicitly through existing MoneyInput evidence instead of fabricating a value.
- Preserve the existing net-profit and ROI thresholds plus all three existing profitability filter results without changing calculator formulas or policy.
- Add an Application repository Protocol for save and direct, Opportunity, and Market Observation identity lookups without persistence, wiring, migration, transactions, or backfill.
- Assign snapshot creation exclusively to the Economics Calculator and keep runtime EconomicsCalculation objects outside the persistence contract.

## PR30 - PriceIntelligence Snapshot Foundation

- Add an immutable PriceIntelligence snapshot contract preserving every existing analyzer result, explicit Opportunity and Market Observation identities, ordered Product Observation source IDs, analyzer version, generation time, and schema version.
- Require sample size to match the immutable ordered source cohort without changing grouping, fallback, stability, variation, recommendation, or price formulas.
- Add an Application repository Protocol for save and direct, Opportunity, and Market Observation identity lookups without persistence, migration, transactions, or backfill.
- Assign snapshot creation exclusively to the Price Intelligence Analyzer and keep runtime PriceIntelligence objects outside the persistence contract.
- Keep collectors, orchestrator, Economics, Production Safety, Review, Dashboard, Decision, and all existing analyzers and formulas unchanged.

## PR29 - Product Observation Snapshot Foundation

- Add an immutable Product Observation Domain contract preserving explicit Opportunity and Market Observation identities, every existing runtime Product field, collector-supplied provenance, observation time, and schema version.
- Add an Application repository Protocol for save, direct lookup, Opportunity lookup, and Market Observation identity lookup without selecting persistence or adding tables.
- Assign snapshot creation exclusively to the Marketplace Collection Boundary; Validation Admission, Review, Safety, Dashboard, and Decision cannot create snapshots.
- Record why price history cannot substitute for a complete Product observation and why mutable Product reconstruction, migration, backfill, and inferred provenance are prohibited.
- Keep collectors, PriceIntelligence, Economics, Production Safety, Review, Dashboard, Decision, formulas, and schemas unchanged.

## PR25-B - Decision Readiness and Finalization Experience

- Add a read-only Decision Readiness Application service and API that validates persisted source existence, authoritative identity, and approved schema/policy versions without rerunning any formula or assessment.
- Extend Opportunity Detail with per-source status, blocking reasons, latest composition version, Dashboard navigation, and an explicit Finalize action enabled only when required sources are ready.
- Refetch authoritative readiness and Dashboard state after successful finalization and provide bounded 404/409/422/503 UX without automatic finalization or raw persistence errors.
- Keep missing Verified Economics, Production Safety, Competition, and Demand operational entry points visible as blockers instead of fabricating READY/COMPLETE sources.

## PR25-A - Opportunity Detail and Review Create UI

- Add responsive, accessible `/opportunities` and `/opportunities/{id}` Jinja/vanilla JavaScript pages over minimal read-only operational Opportunity APIs.
- Compose Opportunity, Market identity, existing Review binding/status, and authoritative OCR Candidate ledger records without adding Candidate identity inference.
- Add explicit Candidate selection and trusted bound Review creation, redirect successful creation to the Review Queue, and link an already-bound Opportunity directly to Review Detail.
- Reject a second Opportunity-bound Review while retaining restart-safe replay for the original Create command.

## PR24-A - Opportunity–Review Authoritative Binding Foundation

- Add immutable `OpportunityReviewBinding` history/current persistence with complete Opportunity, ReviewSession, discovery, Market identity, command, timestamp, and schema provenance.
- Atomically validate and persist an optional trusted Review Create `opportunity_id` alongside Receipt, Session, and Candidate Contexts without changing Review Domain transitions.
- Restrict Decision external-signal selection to receipt-backed Signals from explicitly bound ReviewSessions when an Opportunity has Review bindings; reject explicitly selected unbound Signals.
- Prevent title, query, artifact ID, or Market identity inference and retain legacy behavior for explicitly unbound pre-foundation Reviews and Opportunities.

## PR23-C - MVP Operational E2E

- Add an explicit local-only Founder Review validation harness backed by a required new, non-default SQLite file.
- Reuse the authoritative Candidate ledger, Review Command Context, ReviewWorkflowService, receipts, Verification, and External Signal persistence with deterministic, visibly demo-labelled provenance.
- Provide a prepare-only mode for browser-driven workflow validation and report the missing authoritative Review-to-Opportunity identity as a Decision connectivity blocker instead of inferring a link.

## PR23-B - Founder Review UI

- Add responsive, accessible Jinja and vanilla JavaScript pages at `/reviews` and `/reviews/{session_id}` for Queue and operational Review Detail workflows.
- Add a read-only detail query/DTO that joins the authoritative ReviewSession, ordered OCR Candidates, Candidate statuses, persisted Review Command Contexts, Skip metadata, and Artifact metadata without adding Domain behavior.
- Support explicit Start, Approve, Correct, Skip, Complete, and Cancel forms with authoritative revision use, stable retry identities/timestamps, no optimistic state, and post-success refetch.
- Render all API values through `textContent`, provide status-specific bounded error UX, and avoid exposing raw SQLite details or stack traces.
- Keep artifact preview explicitly unavailable because no artifact-binary retrieval route exists.

## PR23-A-3 - Founder Review Write API

- Add Founder Review Approve, Correct, Skip, and Complete HTTP 200 command endpoints over `ReviewWorkflowService`.
- Resolve Approve/Correct market identity and signal semantics exclusively from persisted `ReviewCommandContext`, then atomically persist Verification, External Signal, Receipt, and Session transition through the existing workflow.
- Keep Skip free of Verification and External Signal writes and reuse existing Skip metadata, Receipt, and Session persistence.
- Preserve the existing pending-Candidate completion rule and restart-safe exact command replay.
- Map missing Sessions to 404, workflow conflicts to 409, malformed input to 422, and persistence failures to 503 without exposing raw SQLite errors.

## PR23-A-2B - Trusted Review Create API

- Add `POST /api/v1/reviews` for trusted ReviewSession admission with complete immutable Candidate Command Contexts.
- Reuse `CreateReviewSession`, `ReviewCommandContext`, `ReviewCommandReceipt`, `ReviewWorkflowService`, and the existing Session response DTO.
- Commit the Create Receipt, Session history/current, and every Context history/current row in one restart-safe SQLite transaction.
- Require the Context Candidate set to match the Session Candidate set and retain existing repository checks for Candidate existence, membership, and artifact identity.
- Replay identical commands without additional writes; map conflicts to 409, malformed input to 422, and persistence failures to 503.

## PR23-A-2A - Founder Review Start / Cancel API

- Add `POST /api/v1/reviews/{session_id}/start` and `POST /api/v1/reviews/{session_id}/cancel` as thin FastAPI adapters over the existing authoritative `ReviewWorkflowService` command boundary.
- Require expected revision, command ID, operator ID, and explicit timezone-aware transition timestamps; Cancel also preserves a non-empty immutable audit reason.
- Reuse the existing `ReviewSessionResponseDTO` for successful commands and restart-safe identical Receipt replay without exposing the ReviewSession aggregate.
- Map missing Sessions to 404, revision/command/operator/transition conflicts to 409, malformed input to 422, and persistence/projection/commit/SQLite failures to 503.
- Restrict Start writes to Session history/current plus Receipt and Cancel writes to those facts plus Cancel metadata; Verification, External Signal, Lifecycle, Decision, and Dashboard facts remain unchanged.
- Keep Review Session creation out of scope until Session creation and every authoritative Candidate Command Context can be persisted atomically.

## PR23-A-1 - Founder Review Read API

- Add read-only `GET /api/v1/reviews` and `GET /api/v1/reviews/{session_id}` endpoints over the existing `ReviewSessionQueryService` boundary.
- Return immutable API DTOs containing Session status/revision, Candidate aggregate counts, lifecycle timestamps, and schema version without exposing the ReviewSession aggregate.
- Map missing Sessions to HTTP 404 and persistence/SQLite failures to HTTP 503 while successful deterministic reads return HTTP 200.
- Verify repeated GET equality, zero open write transactions, and unchanged ReviewSession, Verification, External Signal, Receipt, and Lifecycle table state.
- Keep SQL, repositories, Domain transitions, and business rules outside the FastAPI handlers.

## PR23-A.0 - Review Command Context & Receipt Foundation

- Persist immutable Review Command Context history/current facts so Approve and Correct can load authoritative market identity, signal, and artifact provenance without client reconstruction.
- Persist one immutable Review Command Receipt per command with exact resulting revision, Verification/External Signal IDs, and committed timestamps for restart-safe response replay.
- Persist immutable Cancel audit metadata with reason, operator, cancellation time, revision, and schema version.
- Add deterministic, read-only Application queries for Context, Receipt, and Cancel metadata with explicit malformed and unsupported-version errors.
- Insert Approve/Correct receipts after Verification and External Signal projections but before ReviewSession history/current in the same `BEGIN IMMEDIATE` transaction; receipt failure rolls back every fact.
- Keep Founder Review HTTP API/UI and new Review business rules out of scope.

## PR23-P.1 - ReviewSession Persistence Hardening

- Add production command DTOs carrying only session ID, Candidate ID, expected revision, command ID, operator, and action input; services reload authoritative Session and OCR Candidate facts before every transition.
- Preserve distinct ReviewSession history, current projection, commit, version, command, operator, membership, malformed-persistence, and unsupported-version errors through the Application boundary.
- Add deterministic current-projection rebuild from the latest immutable history revision while preserving complete aggregate value equality.
- Verify Approve and Correct rollback at Verification history/current, Signal history/current, Session history/current, and commit boundaries.
- Verify create, start, skip, complete, and cancel history/current/commit rollback without revision advancement or open transactions.
- Add response-loss replay and changed-payload conflict coverage for every transition, exact Verification/Signal replay, read-only table-state comparison, terminal restart round-trips, and real multi-connection concurrency races.
- Retain the prior PR20 aggregate-based commands as compatibility adapters; persisted current and ledger facts remain authoritative.

## PR23-P - ReviewSession Persistence Foundation

- Persist immutable `ReviewSession` transition snapshots in append-only `review_session_history` with an atomic `review_session_current` projection.
- Preserve Candidate order/statuses, immutable Skip records, lifecycle timestamps, schema version, and a revision starting at 1 and advancing exactly once per transition.
- Reject stale aggregate writes across SQLite connections and persist explicit event IDs, command IDs, transition types, prior/resulting status, timestamps, and command fingerprints.
- Make explicit command retries deterministic: an identical command ID and payload reconstitutes the committed state, while changed payload conflicts and stale revisions do not create rows.
- Extend verified-signal persistence so approve/correct stores ReviewSession, HumanVerification, and ExternalMarketSignal history/current in one `BEGIN IMMEDIATE` transaction.
- Add read-only get/list/history application queries and restart-safe reconstitution without inferring sessions from legacy ledger facts.
- Keep Founder Review HTTP/UI out of scope; legacy ledger-only workflows receive no automatic ReviewSession backfill.

## PR22-D - Dashboard UI Foundation

- Add browser routes `GET /dashboard/decision` and `GET /dashboard/opportunities/{opportunity_id}/decision` using the existing FastAPI/Jinja and vanilla JavaScript presentation stack.
- Provide an explicit operator flow: load the persisted Decision Dashboard, show a truthful not-finalized state, finalize through the existing POST API only after user action, then reload the existing GET Dashboard API.
- Render DashboardResponseDTO Summary, Action, Warnings, Evidence, and Metadata fields without recalculating or reordering Decision facts.
- Support default latest, explicit none, and explicit External Signal ID selection while rejecting blank or duplicate explicit IDs before submission; server validation remains authoritative.
- Present 404/409/422/503 states without treating REJECT or INSUFFICIENT_EVIDENCE as errors.
- Add semantic headings, labels, keyboard focus, live status regions, responsive cards, visible availability/severity text, Jinja escaping, and textContent-only API rendering.
- Keep page load GET-only, add no authentication system, perform no direct persistence access, and preserve every existing API and Decision contract.

## PR22-C.5 - Decision Composition Finalization API

- Add `POST /api/v1/opportunities/{opportunity_id}/decision-compositions` as a thin command adapter over the existing `FinalizeDecisionComposition` use case; successful immutable version creation returns HTTP 201.
- Accept only optional `external_signal_ids`, timezone-aware `generated_at`, and non-persisted audit hint `requested_by`; unknown client-supplied assessment, metadata, confidence, freshness, availability, and outcome fields are rejected.
- Preserve External Signal selection semantics: omitted/null uses latest HUMAN_VERIFIED series, an explicit empty list selects none, and a non-empty list selects exactly those IDs.
- Return an immutable finalization DTO with stable ISO datetime and tuple-to-list serialization; no Dashboard result is returned from POST.
- Map opportunity/selected-signal absence to 404, duplicate/version/identity/version-support conflicts to 409, request errors to 422, and persistence/corruption/missing authoritative source failures to 503.
- Repeated identical POST returns 409 without advancing history/current; changed provenance creates the next version. POST writes only composition history/current and Dashboard GET remains read-only.

## PR22-C.3.7 - Production Composition Contract Hardening

- Replace synthetic Economics and Safety confidence with explicit unknown confidence and derive freshness from authoritative timestamps using the versioned 30-day `decision-composition-metadata-v1` window.
- Derive External Reference confidence from the minimum selected HUMAN_VERIFIED signal confidence and aggregate freshness as FRESH only when every selected signal is fresh; explicit signal ID selection supports additions and omissions across composition versions.
- Validate supported Decision, composition, metadata, snapshot, assessment-policy, Safety-rule, and External Signal versions.
- Separate duplicate, version conflict, history persistence, current projection, commit, malformed persistence, missing-source, unsupported-version, and identity-conflict errors.
- Preserve exact history-ID reconstruction and make available-but-unknown evidence confidence an additive Domain/API contract.
- Expand versioning, selection, stale metadata, malformed persistence, projection rollback, deterministic response, and full read-only persistence-state tests.

## PR22-C.3.6 - Immutable Decision Composition Finalization

- Add explicit, append-only Decision Composition finalization after admission, market assessment, and optional Human Review.
- Persist versioned composition history and an atomic latest projection with exact source snapshot IDs, external signal series IDs, five Decision evidence metadata values, and Decision schema/policy versions.
- Centralize versioned metadata policy `decision-composition-metadata-v1`; external absence is explicitly UNAVAILABLE with no fabricated signal.
- Reject identical provenance, stale composition versions, missing source rows, identity mismatches, and non-human-verified external provenance.
- Keep prior admission and assessment transactions unchanged when finalization fails; Dashboard GET remains read-only and never finalizes.
- Reconstruct DecisionInput from the latest finalized composition and run the existing Decision Matrix, explanation, Dashboard read-model, and API DTO pipeline.

## PR22-C.3.5 - Assessment Snapshot Foundation

- Add immutable Competition and Demand assessment snapshot contracts preserving bound market identity, source observation ID, availability, exact Decimal confidence, freshness, generated time, schema version, and policy version.
- Persist observation history/current and assessment snapshot history/current in one SQLite transaction with provenance identity/type validation and full rollback on snapshot failure.
- Add deterministic latest persisted Competition and Demand assessment queries without rerunning intelligence analysis.
- Add an identity-scoped query returning every latest per-signal HUMAN_VERIFIED External Market Signal without requiring callers to know signal names or returning superseded series values.
- Block duplicate assessment provenance and UPDATE/DELETE of immutable assessment history while retaining a replaceable latest projection.
- Keep Competition/Demand formulas, thresholds, Decision policy, Dashboard contracts, and existing Market Observation history semantics unchanged.

## PR22-C.3 - Production Safety Snapshot Binding

- Add an immutable authoritative `ProductionSafetyAssessment` snapshot bound during Founder Validation admission, preserving status and tuple-based missing/failed facts.
- Preserve explicit snapshot time, Safety rule version, and snapshot schema version without recalculating Safety.
- Store Safety atomically with lifecycle current/history, admission snapshot, market identity, verified economics, and the estimated baseline on the variance-ready path.
- Block duplicate rows, UPDATE, DELETE, malformed snapshots, and Opportunity identity mismatches.
- Add `GetProductionSafetySnapshot` and use it from Dashboard production composition through the application boundary.
- Preserve legacy missing-snapshot failure and advance fully bound composition to the next explicit blocker: Competition and Demand evidence sources are not connected to the provider.

## PR22-C.2 - Verified Economics Snapshot Binding

- Add an immutable authoritative `VerifiedEconomicsInput` snapshot bound to the admitted Opportunity, preserving all Decimal values and per-field evidence provenance.
- Store the snapshot atomically with lifecycle current/history, admission snapshot, market identity binding, and the estimated baseline on the variance-ready path.
- Reject identity mismatches and verified-economics admission without an explicit market identity; block duplicate rows, UPDATE, and DELETE.
- Add `GetVerifiedEconomicsSnapshot` for deterministic, read-only reconstruction without using Estimated Economics, Actual Economics, or admission ROI.
- Preserve legacy missing-snapshot behavior as an explicit Dashboard composition failure with no backfill or fabricated values.
- Advance a fully bound Dashboard composition to the next truthful blocker: no authoritative `ProductionSafetyAssessment` source.

## PR22-C.1 - Opportunity Market Identity Binding

- Add an immutable, explicit Opportunity-to-MarketObservationIdentity binding with complete LISTING/CANONICAL_PRODUCT identity fields, timezone-aware observation windows, binding time, and schema version.
- Insert the binding atomically with lifecycle current/history and the Validation admission snapshot, including the variance-ready estimated-economics baseline path.
- Reject SEARCH_QUERY/CATEGORY scopes, mismatched opportunity/reference identities, duplicates, updates, and deletes.
- Preserve legacy admission without guessing a binding; legacy Dashboard queries continue to return the explicit composition-gap 503.
- Resolve bindings through `GetOpportunityMarketIdentity`; a valid binding advances Dashboard composition to the next truthful blocker: no authoritative persisted `VerifiedEconomicsInput` source.
- Keep admission rollback semantics, Decision rules, formulas, thresholds, and all evidence contracts unchanged.

## PR22-C - Production Decision Dashboard Query Composition

- Wire the decision-dashboard endpoint to a production provider that resolves the authoritative Validation Queue/Lifecycle subject by HYB `opportunity_id`.
- Keep OpportunityIdentity separate from MarketObservationIdentity and reject mismatched persisted subjects.
- Detect the current persistence gap explicitly: admission/lifecycle storage has no listing/canonical MarketObservationIdentity link, so Competition, Demand, External Signal, verified economics, and safety composition cannot truthfully proceed.
- Return 404 for an absent Opportunity subject and 503 for the unsupported composition boundary or SQLite infrastructure failure; no evidence values are fabricated.
- Preserve the read-only query contract with no lifecycle, validation, economics, market observation, review, or decision writes.
- Leave all Decision, explanation, Dashboard, economics, safety, Competition, and Demand rules unchanged.

## PR22-B - FastAPI Dashboard Decision Endpoint

- Add `GET /api/v1/opportunities/{opportunity_id}/decision-dashboard` as a read-only Presentation adapter returning `DashboardResponseDTO.to_dict()`.
- Preserve exact Decimal strings, stable enum values, timezone-aware ISO 8601 timestamps, and schema, policy, and read-model versions.
- Treat INVEST, REVIEW, REJECT, and INSUFFICIENT_EVIDENCE as valid HTTP 200 business outcomes.
- Map missing sources to 404, identity/state conflicts to 409, invalid input to 422, and unavailable composition or infrastructure to 503.
- Add an injectable Application query/provider boundary that verifies the HYB opportunity identity before DTO assembly.
- Leave production query composition explicitly unconfigured until persisted Decision inputs/results can be reconstructed without fabricated facts.

## PR22-A - Dashboard API DTO Foundation

- Add immutable Dashboard summary, action, warning, evidence, metadata, and response DTO contracts.
- Map the existing DashboardReadModel into deterministic serialization-only DTOs without executing Decision or explanation behavior.
- Add an explicit `to_dict()` JSON boundary with stable enum values, timezone-aware ISO 8601 timestamps, and exact Decimal-as-string serialization.
- Preserve warning/evidence ordering and source values while identifying the DTO serialization contract with read-model version `1.0`.
- Keep FastAPI endpoints, routing, UI rendering, repositories, Decision Policy, and Dashboard business contracts unchanged.

## PR21-E - Dashboard Read Model Foundation

- Add immutable, UI-independent summary, action, warning, and per-dimension evidence cards for Decision Engine V2.
- Assemble deterministic Dashboard read models from matching DecisionResult and DecisionExplanation inputs without recomputing policy, confidence, or explanations.
- Preserve generated time, schema version, policy version, explanation items, and dimension evidence values.
- Provide presentation-only primary action labels and fixed evidence/warning display order without introducing Recommendation semantics.
- Keep FastAPI, REST, CLI, HTML, CSS, JavaScript, charts, and Dashboard rendering unchanged.

## PR21-D - Deterministic Decision Explanation

- Add immutable Decision summary, explanation sections/items, and per-dimension evidence summaries.
- Convert DecisionResult facts into fixed Summary, Strengths, Warnings, and Missing Evidence sections.
- Apply deterministic explanation codes, default text, severity mapping, ordering, and duplicate removal without using an LLM.
- Preserve Decision outcome, aggregate confidence, timestamps, schema version, and policy version without rerunning policy or assessments.
- Keep Dashboard, Recommendation, Founder Decision, and all Economics, Safety, Competition, and Demand calculations unchanged.

## PR21-C - Decision Matrix Foundation

- Add a policy protocol and default MVP policy that combines only immutable dimension results.
- Produce INVEST, REVIEW, REJECT, and INSUFFICIENT_EVIDENCE outcomes without recalculating Economics, Safety, Competition, Demand, or External signals.
- Aggregate exact Decimal confidence across available dimensions while preserving missing-dimension availability.
- Resolve dimension facts into blocking, supporting, and uncertainty reason categories.
- Keep External signals outcome-neutral and preserve existing Recommendation, Founder Decision, formulas, and thresholds.

## PR21-B - Decision Dimension Evaluation

- Add independent Economics, Safety, Competition, Demand, and External Reference dimension evaluators.
- Pass explicit availability, Decimal confidence, and freshness metadata into immutable dimension results without calculating a Decision outcome.
- Orchestrate the five evaluators in a stable order through an Application service and evaluator port.
- Reuse existing Competition, Demand, and Production Safety classifications without changing thresholds or formulas.
- Keep Decision Matrix, DecisionResult construction, Recommendation, Dashboard, and Founder Decision unchanged.

## PR21-A.1 - Decision Domain Contract Hardening

- Separate immutable Opportunity identity from Market Observation evidence identity.
- Restrict Decision inputs to listing and canonical-product market scopes.
- Enforce confidence availability/missing-dimension consistency and immutable Safety collections.
- Reject mutable human-verified external signal values at the Decision input boundary.
- Keep Decision calculation, Recommendation, business thresholds, and external signal storage contracts unchanged.

## PR21-A - Decision Engine V2 Domain Contract

- Add immutable Decision Engine V2 outcomes, dimensions, fact reason codes, evidence metadata, inputs, and results.
- Require Decimal confidence, timezone-aware timestamps, immutable tuples, and explicit schema/policy versions.
- Reuse verified economics, production safety, market assessments, human-verified external signals, and market observation identity without calculating a decision.
- Move the existing immutable production-safety status/result language into the Opportunity Domain while preserving the legacy engine import path and safety formula.
- Keep Decision Matrix, Recommendation, Dashboard, Founder Decision, thresholds, economics formulas, and Agreement Analysis unchanged.

## PR20-C.1 - Multi-Candidate Provenance Hardening

- Distinguish verified external signals by candidate, verification, signal name, artifact, and evidence provenance.
- Reject reused candidate IDs, verification IDs, observation IDs, and identical signal provenance.
- Maintain independent external-signal current projections per logical identity and signal name.
- Migrate legacy external current projections to deterministic per-signal series keys.
- Require SkipCandidate to validate the full persisted candidate and its artifact against the review session.
- Preserve PR20-C verification-and-signal SQLite atomicity and leave Competition/Demand projections unchanged.

## PR20-C - Verified Signal Persistence and Review Completion

- Persist approved and corrected external signals as `EXTERNAL_SIGNAL` market observations.
- Preserve candidate, verification, artifact, operator, capture, verification, and reviewed-value provenance through SQLite round trips.
- Store verification ledger facts and verified signal history/current projections in one SQLite transaction.
- Track immutable per-candidate pending, approved, corrected, and skipped review states.
- Reject review completion while any candidate remains pending and add candidate skipping without verification or signal creation.
- Keep OCR providers, Decision Engine, Recommendation, Competition, Demand, Economics, Lifecycle, Dashboard, and FastAPI unchanged.

## PR20-B - Human Review Workflow

- Add an immutable OCR review-session aggregate with explicit terminal transitions.
- Approve or correct persisted candidates into verification ledger facts and verified signals.
- Reject missing, mismatched, duplicate, and terminal-session candidate reviews.

---

## PR20-A - OCR Adapter Contract Foundation

- Add provider-neutral immutable OCR result and field-result contracts.
- Add an ExtractText adapter port and deterministic no-I/O dummy adapter.
- Convert OCR results into unverified OCR candidates without implementing an OCR engine.

---

## PR19-B - External Signal Ledger Foundation

- Persist OCR candidates and human verifications as append-only SQLite facts.
- Maintain non-regressing latest projections atomically with history insertion.
- Reject provenance fingerprints duplicated across candidate or verification history.

---

## PR19-A - External Signal Trust Foundation

- Add immutable artifact, unverified OCR candidate, and human verification facts.
- Enforce an explicit human-verification boundary before external signal creation.
- Keep OCR engines, persistence, recommendation, and decision behavior out of scope.

---

## PR18-B.1 - Demand Availability Contract Hardening

- Assess available demand evidence independently instead of requiring all five proxies.
- Add complete/partial availability metadata and average confidence only across usable evidence.
- Remove the misspelled demand/competition balance field before it becomes a public contract.

---

## PR18-B - Demand Intelligence Foundation

- Add immutable demand-only assessments with explicit search, review, and rating thresholds.
- Preserve ranking signals as independent demand proxies and exact Decimal confidence evidence.
- Reuse the PR17 observation repository without adding recommendation or decision behavior.

---

## PR18-A - Competition Intelligence Foundation

- Add immutable competition-only assessments and explicit MVP threshold policies.
- Calculate price pressure from relative price spread and preserve Decimal confidence averages.
- Reuse the PR17 observation repository without adding scoring or recommendation behavior.

---

## PR17-3 - Market Observation Repository Foundation

- Add application use cases and a common repository port for immutable market observations.
- Persist append-only SQLite history and update a separate latest-observation projection atomically.
- Reject duplicate provenance fingerprints and calculate freshness only at query time.

---

## PR17-2 - Market Observation Contracts

- Add immutable Competition and Demand observation snapshots with strict metric validation.
- Add immutable external reference signals with human-verification and artifact provenance rules.
- Keep scoring, recommendation, persistence, collectors, OCR, and presentation unchanged.

---

## PR17-1 - Market Evidence Contract

- Add immutable market evidence status and provenance contract.
- Add scope-aware market observation identity and time-window validation.
- Keep Competition, Demand, External Signal, persistence, and presentation out of scope.

---

## PR16-A.1 - Variance Snapshot Contract Hardening

- Preserve original tax-rate evidence separately from calculated tax-cost evidence.
- Require complete economic evidence metadata when an estimated snapshot is created.
- Preserve required evidence keys through SQLite baseline round trips.

---

## PR16-A — Estimated vs Actual Variance Foundation

- immutable Estimated Economics admission baseline과 evidence/version 보존 추가
- Actual Economics와 baseline을 비교하는 side-effect-free Variance Domain 계산 추가
- signed/absolute/relative difference, ROI percentage-point 및 comparability 상태 구현
- Lifecycle, admission snapshot, estimated baseline의 SQLite atomic admission 경로 추가
- Variance 결과는 저장하지 않고 source version으로 조회 시 계산

---

## PR15-A.2 — Actual Economics Ledger Final Hardening

- 최초 Purchase event에 currency를 기록하고 Aggregate currency와의 binding 검증 추가
- Event history currency를 보존하는 additive SQLite column migration 추가
- malformed event version은 semantic error, 실제 persisted version 충돌은 optimistic conflict로 분리

---

## PR15-A.1 — Actual Economics Ledger Contract Hardening

- Purchase, Sale, Settlement event의 action별 필수/금지 fact 검증 추가
- Event fact를 Aggregate 및 기존 persisted state와 대조해 current/history 불일치 차단
- 숫자 0을 유효한 actual fact로 보존하고 `None`만 누락으로 처리
- `EMPTY`/version 0을 DB row가 없는 transient-only 상태로 명시
- sale price는 fee 차감 전 gross 값이며 settlement는 계산에 사용하지 않는 보존 사실임을 명시

---

## PR15-A — Actual Economics Foundation

- Verified Economics의 예상값과 분리된 Actual Economics Aggregate 추가
- Purchase, Sale, Settlement 실제 사실과 계산된 actual profit/ROI 계약 추가
- Lifecycle 상태를 읽기 사전조건으로만 사용하는 Application use case 추가
- current state와 append-only event history를 원자적으로 저장하는 additive SQLite repository 추가
- 기존 Recommendation, Lifecycle, Validation Queue 및 Presentation 계약은 변경하지 않음

---

## PR14-B.1 — Validation Queue Contract Hardening

- Discovery reference를 trim/lowercase/stable `:` separator 형식으로 canonicalize
- non-archived Lifecycle 전체에 canonical discovery reference uniqueness 적용
- archive 후 동일 reference 재등록은 허용하되 restore/return 충돌은 명시적 duplicate conflict로 반환
- 기존 Queue/Lifecycle/Snapshot reference를 transaction migration에서 canonical 형식으로 정규화

---

## PR14-B — Founder Validation MVP

- OpportunityLifecycle 기반 Validation Queue read model과 immutable admission snapshot projection 추가
- 선택한 Opportunity만 명시적으로 등록하는 `AddToValidationQueue` 및 조회/Review/Approve/Reject/ReturnToReview use case 추가
- Lifecycle current state, CREATE history, admission snapshot을 하나의 SQLite transaction으로 저장
- active Queue discovery reference에 대한 동시 중복 등록 방지
- 기존 Search, CLI, Dashboard DTO를 유지하는 additive Validation Queue FastAPI 추가

---

## PR14-A.1 — Lifecycle Contract Hardening

- Lifecycle status, version, identity, timestamp를 외부에서 직접 대입할 수 없도록 캡슐화
- SQLite 복원을 전용 internal reconstruction path로 분리
- transition 저장 전 previous/new status, version, timestamp, action 및 event completeness 검증
- semantic validation 실패 시 current state와 append-only history를 그대로 보존

---

## PR14-A — Opportunity Lifecycle Foundation

### Added

- Validation Queue에 명시적으로 저장된 Opportunity만 관리하는 별도 Lifecycle Aggregate
- Founder Approve/Reject 결정을 AI Recommendation과 분리한 불변 Domain Contract
- 허용 상태 전이, SOLD terminal, archive/restore metadata 및 optimistic version 규칙
- 현재 상태와 append-only 전이 이력을 원자적으로 저장하는 additive SQLite repository

### Compatibility

- 기존 OpportunityResult, RecommendationResult 및 opportunity_history는 변경하지 않음
- Discovery, CLI, FastAPI, Dashboard에 자동 Lifecycle 생성 또는 출력 변경을 추가하지 않음

---

이 문서는 Sprint 및 PR별 주요 변경사항을 최신 항목부터 기록합니다.

---

## PR13-C — Verified Economics Contract

### Added

- Opportunity Domain의 경제 입력 provenance 계약
- `verified`, `estimated`, `default`, `calculated`, `missing`,
  `unsupported` evidence 상태
- 기존 Product와 orchestrator 인자를 contract로 조립하는 mapper
- 기존 `calculate_opportunity(dict)` 결과를 typed calculation으로 감싸는
  호환 wrapper
- Safety Gate의 contract 우선 평가 및 기존 `*_known` fallback

### Compatibility

- 기존 Opportunity, ROI, score, trend, recommendation 공식은 변경하지 않음
- CLI, Dashboard, FastAPI, opportunity history 외부 계약은 변경하지 않음
- 기존 `calculate_opportunity(dict)` 및 `calculate_product_opportunity()` 유지

### Validation

- PR13-C Domain/Opportunity/Safety feature tests: `32 passed`
- Full pytest: `1203 passed`
- Warning: 기존 FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR5 — Release Candidate and Sprint Completion

### Added

- Production Composition Release Candidate E2E coverage
- Actual `--watch-monitor` CLI integration with WatchList and Price History
- Sprint 11 Completion Report

### Audit

- Repository, Change Detector, Observation Recorder, and Monitor wiring verified
- Domain and WatchList Application dependency directions verified
- No circular dependency, Infrastructure leak, or Domain rule violation found

### Validation

- Release Candidate E2E: `1 passed`
- Production Composition: `3 passed`
- CLI: `31 passed`
- WatchList: `96 passed`
- Price History: `34 passed`
- Change Detection: `30 passed`
- Full pytest: `1160 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR4-B — Price Observation Idempotency

### Added

- Observation identity based on canonical product, marketplace, item, and
  observation time
- Idempotent retry returning the existing Price History record ID
- Explicit `PriceObservationConflictError` for different data under one
  observation identity
- ADR-0002 documenting idempotency and partial-failure policy

### Architecture

- Price remains observation data rather than identity
- Existing records remain append-only and are never overwritten
- SQLite `BEGIN IMMEDIATE` serializes the repository identity check and insert
- Price History and WatchItem writes remain separate transactions
- A retained observation allows WatchItem save to recover on retry

### Validation

- Price History tests: `34 passed`
- WatchList tests: `94 passed`
- Change Detection tests: `30 passed`
- CLI tests: `30 passed`
- Full pytest: `1158 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR4-A — WatchList Price Observation Recording

### Added

- Narrow `PriceObservationRecorder` Application port
- `PriceHistoryObservationRecorder` adapter backed by the existing
  `PriceHistoryRepository`
- WatchList Monitor recording of successful current-price observations

### Architecture

- Execution order is change detection, observation recording, then WatchItem save
- Changed and unchanged successful observations are both appended
- Price History and WatchItem writes remain separate transactions
- Deduplication and detailed partial-failure policy remain PR4-B scope

### Validation

- Monitor feature tests: `23 passed`
- Recorder adapter tests: `2 passed`
- Composition tests: `3 passed`
- WatchList regression: `92 passed`
- Change Detection and Price History regression: `57 passed`
- CLI regression: `30 passed`
- Full pytest: `1148 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR3 — WatchList Monitor CLI Entry Point

### Added

- Existing argparse-style `--watch-monitor` CLI mode
- CLI connection from `create_watchlist_monitor()` to one monitor execution
- Total, Updated, Unchanged, Failed, and Not Found summary output
- Isolated CLI tests with fake and real empty SQLite composition

### Architecture

- Existing search and history CLI flows remain unchanged
- No Worker, Scheduler, Dashboard, notification, or Snapshot storage changes

### Validation

- New WatchList Monitor CLI tests: `2 passed`
- Existing CLI, Presentation, and Composition tests: `18 passed`
- Full pytest: `1140 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR2 — WatchList Monitor Composition Root

### Added

- Public `create_watchlist_monitor()` Infrastructure factory
- Actual SQLite WatchList repository, eBay/Amazon lookup adapter,
  Price History provider, and latest-price detector composition
- Public-behavior composition tests using an isolated SQLite database

### Architecture

- Factory construction does not call Marketplace APIs
- Existing Domain, Application, Adapter, and Reader contracts are unchanged
- CLI/Worker execution and current Snapshot storage remain outside this PR

### Validation

- New composition tests: `2 passed`
- Existing WatchList tests: `76 passed`
- Change Detection and Price History tests: `72 passed`
- Full pytest: `1138 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR1 — Marketplace Reader Integration

### Added

- `EbayListingReader` using `marketplaces.ebay.get_product_by_id()`
- `AmazonListingReader` using `marketplaces.amazon.get_product_by_id()`
- eBay/Amazon reader registry factory for
  `MarketplaceListingLookupAdapter`
- Concrete reader contract and registry dispatch tests

### Architecture

- Existing reader and lookup adapter contracts remain unchanged
- No Composition Root, CLI, worker, Snapshot storage, or Dashboard changes

### Validation

- Reader, dispatcher, adapter, and exact lookup tests: `43 passed`
- Full pytest: `1136 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 11 PR0 — Context Pack Automation

### Added

- PowerShell scripts to create and clean Quick and Full Context Packs
- Generated Context manifest and documented archive exclusions
- Context Pack usage guide and persistent `context/.gitkeep`

### Changed

- Generated Context Pack artifacts are ignored by Git
- Context Pack refresh is part of the project Definition of Done

### Validation

- Create and cleanup scripts executed in PowerShell
- Quick Context: `6` expected files, `0` missing or unexpected
- Full Context: `375` files, `0` excluded entries
- Full pytest: `1131 passed`
- Warning: existing FastAPI TestClient `StarletteDeprecationWarning` 1건

---

## Sprint 10 Finalization — Audit Report

### Added

- Official Sprint 10 audit covering PR1 and PR2A through PR2D
- Architecture impact, validation, limitations, lessons learned, outcome,
  and Sprint 11 planning direction

### Status

- Sprint 10 completed
- Current focus moved to Sprint 11 planning
- Final FastAPI feature validation: `10 passed`
- Final full regression: `1131 passed`

---

## Sprint 10 PR2D — Dashboard UX Polish

### Added

- Initial empty state prompting the user to search
- Result summary using the returned query and opportunity count
- Centered, responsive dashboard layout with improved spacing
- Status and alert roles for loading, summary, and error states
- Dashboard UX accessibility HTML contract test

### Architecture

- Existing browser fetch and search API remain unchanged
- No backend, API route, or business logic changes
- No external frontend dependency was added

### Validation

- FastAPI feature tests:
  - `10 passed`
- Full pytest:
  - `1131 passed`

---

## Sprint 10 PR2C — Opportunity Dashboard MVP

### Added

- Semantic opportunity card rendering from existing `dashboard_cards` JSON
- Product title, Marketplace, final score, ROI, expected selling price,
  and net profit display
- Minimal card styling with emphasized score
- Searching, no-results, and error states
- Opportunity dashboard HTML contract test

### Architecture

- Existing search API and JSON response are reused without backend changes
- Dashboard rendering remains browser-side
- No API route or external UI dependency was added

### Validation

- FastAPI feature tests:
  - `9 passed`
- Full pytest:
  - `1130 passed`

---

## Sprint 10 PR2B — API-First Opportunity Search

### Added

- Vanilla JavaScript `searchOpportunities()` function
- Existing `POST /api/v1/opportunities/search` integration
- Loading, error, and results containers
- Simple title, marketplace, and final opportunity score rendering
- Landing page search-control test

### Architecture

- Search results are rendered in the browser without server-side result rendering
- Existing search API and business logic remain unchanged
- No new search route or external frontend dependency was added

### Validation

- FastAPI feature tests:
  - `8 passed`
- Full pytest:
  - `1129 passed`

---

## Sprint 10 PR2A — Initial Web Landing Page

### Added

- `GET /` HTML landing page
- FastAPI `Jinja2Templates` configuration
- `templates/index.html` with a minimal search form
- Landing page response test

### Dependencies

- `jinja2 3.1.6`

### Architecture

- HTML endpoint renders a template only and contains no business logic
- No Marketplace API is called
- Existing JSON endpoints, including `POST /api/v1/opportunities/search`, are unchanged
- Engine, Domain, Application, CLI, Storage, Presentation, and Marketplace layers are unchanged

### Validation

- FastAPI feature tests:
  - `7 passed`
- Full pytest:
  - `1128 passed`
- Warning:
  - FastAPI TestClient의 `httpx` fallback 관련
    `StarletteDeprecationWarning` 1건

---

## Sprint 10 PR1 — FastAPI JSON MVP

### Added

- FastAPI application entry point
- `GET /health`
- `GET /version`
- `POST /api/v1/opportunities/search`
- 기존 `find_best_opportunities()` 호출
- 기존 Opportunity List와 Dashboard Presentation Builder 기반 JSON 응답
- 외부 Marketplace 호출을 mock한 FastAPI TestClient 테스트

### Dependencies

- `fastapi 0.141.1`
- `uvicorn 0.52.0`
- `httpx 0.28.1`

위 버전은 프로젝트 Python 3.14.6 환경에서 실제 설치하고 검증했다.

### Architecture

- Engine, Domain, Application, CLI 변경 없음
- Engine 객체를 직접 JSON으로 반환하지 않음
- 기존 `OpportunityListCard.to_dict()`와 `DashboardCard.to_dict()` 재사용

### Validation

- FastAPI feature tests:
  - `4 passed`
- Full pytest:
  - `1125 passed`
- Warning:
  - FastAPI TestClient의 `httpx` fallback에 대한
    `StarletteDeprecationWarning` 1건

---

## Sprint 9 PR3 — Price History Integration for Opportunity Intelligence

### Added

- 일반 CLI 검색에서 `PriceHistoryRepository` 생성
- 동일 Repository 인스턴스를 기존 Orchestrator와 신규 Opportunity
  Intelligence Adapter에 공유
- 저장된 가격 이력 기반 Trend Assessment와 Final Recommendation 출력

### Compatibility

- 기존 CLI 인수, Orchestrator 계약, Presentation 출력과 기존
  Recommendation 유지
- `_evaluate_opportunity_intelligence()`의 Repository 인자는 선택적이며
  기본값은 `None`
- `--no-save`에서는 Repository를 생성하거나 전달하지 않아 기존 비저장
  동작 유지

### Validation

- Feature tests:
  - `34 passed`
- Full pytest:
  - `1121 passed`

---

## Sprint 9 PR2 — Existing CLI Opportunity Intelligence Output

### Added

- 기존 CLI 결과 뒤에 Opportunity Intelligence 상태와 평가 결과 추가 출력
- 신규 Opportunity Score, Decision, Grade, Confidence, Risk 표시
- Trend와 신규 Final Recommendation이 존재할 때만 선택적으로 표시
- `OpportunityResult` 단위 Intelligence 실패 격리

### Changed

- 기존 Orchestrator의 `OpportunityResult` → `DiscoveryResult` 변환을
  CLI와 Gateway가 함께 재사용할 수 있는 함수로 추출
- 기존 CLI 인수, Orchestrator 호출, Dashboard, 기존 Recommendation 유지

### Validation

- Feature tests:
  - `44 passed`
- Full regression:
  - `1119 passed`
- 기존 `.venv` 실행 파일은 프로세스를 생성하지 못해 프로젝트 기반
  Python 3.14 런타임으로 테스트 실행

### Known Limitation

- 기본 CLI는 신규 Intelligence Adapter에 Price History Repository를
  주입하지 않으므로 Trend와 신규 Final Recommendation은 기본 실행에서
  생성되지 않는다.

---

## Sprint 8 PR3-B2 — Marketplace Item Lookup APIs

### Added

- eBay exact item lookup API
- eBay raw item response to validated `Product` conversion
- Amazon deterministic exact item lookup contract
- Amazon lookup result to `Product` conversion
- Exact lookup validation and error-handling tests

### Changed

- Search와 single-item lookup 책임을 명확히 분리
- Amazon 개발용 item catalog를 search와 lookup에서 공통 사용하도록 정리
- WatchList monitoring이 검색 첫 결과를 추정값으로 사용하지 않도록 기반 강화

### Validation

- Full regression: **1053 passed**
- Commit: `3806736 feat: add marketplace item lookup APIs`
- Branch: `main`

---

## Sprint 8 PR3-B1 — Marketplace Listing Lookup Dispatcher

### Added

- `MarketplaceListingLookupAdapter`
- Marketplace reader protocol
- Marketplace name normalization and dispatch
- Unsupported Marketplace handling
- Reader result contract validation
- Dispatcher tests

### Decisions

- Application layer는 Marketplace 구현을 직접 알지 않음
- Infrastructure dispatcher가 Marketplace별 reader를 선택
- Reader exception은 숨기지 않고 상위 호출자가 처리할 수 있도록 유지

### Git

- Commit: `97b60e7 feat: add marketplace listing lookup dispatcher`

---

## Sprint 8 PR3-A — WatchList Monitor Foundation

### Added

- Listing lookup application port
- Monitor request/result models
- WatchList monitor use case foundation
- WatchList monitoring tests

### Direction

- WatchList entry를 Marketplace의 최신 `Product`로 조회
- 이후 Change Detection과 연결할 수 있는 Application boundary 확보

---

## Sprint 8 — WatchList Foundation

### Added

- WatchList domain models and aggregate behavior
- SQLite WatchList repository
- Infrastructure mapper
- Repository and domain tests

### Architecture

- WatchList state와 Marketplace 조회 책임 분리
- 저장소 구현은 Infrastructure에 유지
- Monitoring은 Application use case로 구성

---

## Sprint 7 — Marketplace and Presentation Expansion

### Added / Changed

- eBay marketplace adapter integration
- Marketplace adapter contract tests
- Marketplace validation strengthening
- Dashboard utilities and component extraction
- Hero summary
- Opportunity list ViewModel
- Opportunity list CLI presentation

### Recent Commits

- `6972c7e feat: integrate eBay marketplace adapter`
- `0980269 test: add marketplace adapter contract tests`
- `df23ee0 refactor(presentation): extract dashboard utilities and restore decision timeline`
- `95a3570 refactor(presentation): extract dashboard component builders`
- `2655753 feat(presentation): add dashboard hero summary`
- `1efe197 feat(presentation): add opportunity list view model`
- `448b443 feat(presentation): render opportunity list in cli`

---

## Sprint 7 PR-3 — Documentation Quality Audit

### Added

- Documentation audit report
- Sprint 6 summary
- Documentation inventory and cross-reference audit

### Changed

- Project status, Sprint history, document index, documentation policy, and changelog

### Validation

- Markdown UTF-8 validation passed
- Inspectable relative links: no broken links found
- Last code regression at that point: **853 passed**

---

## Sprint 6 — Explainable Decision Pipeline

### Added

- Market Adjustment explanation
- Decision Report integration
- AI Partner decision explanation
- Dashboard Decision Timeline

### Validation

- Full regression at Sprint 6 completion: **853 passed**

## PR13-B — Production Safety Gate

### Added

- Explicit `production`, `test`, `demo`, and `unspecified` product data sources.
- A post-score Safety Gate that preserves scores while preventing incomplete
  `BUY` and `STRONG_BUY` recommendations.
- `INSUFFICIENT_DATA` safety status with explicit missing-field reasons.
- `PROFITABILITY_FAILED` as a distinct hard-gate status, plus original and
  effective recommendation grades.
- Shipping-cost provenance so an omitted cost is distinct from confirmed free
  shipping.
- Per-component verification metadata for marketplace, payment, and fixed fees.
- Structured Safety Gate fields in Dashboard/API output and opportunity history.

### Changed

- The fixed Amazon catalog remains available for demo and tests but is no
  longer part of production opportunity discovery.
- A production BUY now requires a production source, purchase price, currency,
  known shipping cost, at least two price observations, fee inputs, net profit,
  and ROI.
- Known New and Used conditions are treated as a high comparable conflict.

### Compatibility

- Opportunity scores, weights, thresholds, ROI formulas, and trend formulas
  are unchanged.
- Existing non-BUY recommendations are not upgraded or recalculated by the
  Safety Gate.

Sprint 13

PR13-B
- Production Safety Gate
- Provenance
- Profitability Hard Gate
- Founder Validation Safety

PR13-C
- Verified Economics Contract
- Economics Domain Model
- Legacy Wrapper
- Typed Economics Contract
## PR26-A - Verified Economics Operational Admission

- Added an explicit post-admission Application/API boundary for the existing immutable
  Verified Economics snapshot contract.
- Added atomic, immutable command receipts for exact restart-safe replay without reusing
  Founder Review receipts.
- Extended Opportunity Detail with explicit immutable economics admission, provenance
  fields, read-only saved summary, and authoritative readiness refetch.
## PR26-C - Competition Operational Admission

- Added an Opportunity-bound raw Competition Observation Application/API boundary that
  reuses the existing analyzer and immutable assessment snapshot contract.
- Added atomic observation/assessment/receipt persistence with exact restart-safe replay.
- Added explicit Competition provenance entry and read-only generated assessment display
  to Opportunity Detail, followed by authoritative Decision Readiness refetch.
## PR26-D - Demand Operational Admission

- Added an Opportunity-bound raw Demand Observation Application/API boundary reusing the
  existing analyzer and complete/partial assessment snapshot contract.
- Added atomic Demand observation/assessment/receipt persistence with restart-safe replay.
- Added explicit Demand provenance entry, generated assessment summary, and authoritative
  Decision Readiness refetch to Opportunity Detail.
