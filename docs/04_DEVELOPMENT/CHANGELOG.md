# HYB Changelog

## CR-1B6C3 - Owned Inventory Projection v2

- Preserve receipt-only `receipt-derived-owned-inventory / 1.0.0` as the historical v1 Domain/read owner and add immutable `receipt-and-complete-sale-derived-owned-inventory / 2.0.0`, schema `owned-inventory-position-v2`, without a mutable or materialized inventory table.
- Extend the read contract over existing history to aggregate exact-key committed Goods Receipts and only terminal COMPLETE Actual Sale Settlements, preserve ordered Purchase/Receipt/Sale source IDs and separate event counts, ignore BLOCKED quantity, retain zero-sale provenance, and fail closed on unmatched or negative reconstruction.
- Evolve the existing production `GET /api/v1/opportunities/{opportunity_id}/owned-inventory` response to v2 and prove receipt-to-sale subtraction, BLOCKED exclusion, multiple/zero-sale windows, read purity, restart rebuildability, variant isolation, and bounded errors without changing Actual Sale admission, InventorySnapshot, Actual Acquisition, or Actual Outcome.

## CR-1B6C2 - Actual Sale Settlement Authority and Production API

- Implement ADR-0054 as immutable marketplace-generic `BLOCKED`/`COMPLETE` actual-sale settlement revisions over one exact Goods Receipt-derived O2/product, explicit evaluation window/report reference, fulfilled outbound quantity, canonical gross proceeds, distinct sale-side monetary scopes, ordered other costs, payout reconciliation, finality, evidence, and Decimal/currency policy.
- Add dedicated UUID identity, exact-predecessor append-only SQLite history/receipts, integrity reconstruction, replay/restart/rollback, terminal DB enforcement, and `BEGIN IMMEDIATE` reference/overlap/chronological oversell protection across exact product variants and concurrent COMPLETE windows.
- Expose manual Coupang admission through `POST /api/v1/opportunities/{opportunity_id}/actual-sale-settlements`, including BLOCKED-to-COMPLETE and zero-sales journeys, Decimal-string responses, bounded errors, and strict isolation from Coupang networking, Goods Receipt mutation, receipt-only Owned Inventory v1, legacy Actual Economics, Actual Outcome, and Variance v2.

## CR-1B6B4 - Owned Inventory Projection and Read-Only Production API

- Implement ADR-0053 as immutable `OwnedInventoryProductKey` and `OwnedInventoryPosition` read models plus a SQLite-independent Application projection that groups only complete exact O2/Supplier/Product/option/SKU/unit keys and preserves deterministic Purchase Execution and Goods Receipt lineage.
- Extend Goods Receipt persistence with Opportunity-indexed committed-event enumeration and pure Opportunity identity/history reads; calculate received, sellable, damaged, explicit zero outbound, and sellable on-hand totals on demand without a mutable or materialized inventory table.
- Expose `GET /api/v1/opportunities/{opportunity_id}/owned-inventory` as a deterministic positions collection with empty-existing/404-missing semantics, bounded 409/503 failures, restart rebuildability, request-owned cleanup, and strict isolation from Actual Acquisition Settlement, marketplace `InventorySnapshot`, hypothetical sales, reservations, adjustments, and financial economics.

## CR-1B6B2 - Goods Receipt Authority and Production API

- Implement ADR-0052 as immutable `GoodsReceiptRecord` events over one exact Purchase Execution Record with explicit positive received quantity, exact executed unit, fully classified sellable/damaged quantities, dedicated evidence, optional opaque delivery reference, factual receipt/inspection times, and exact O2 Supplier/Product/Quote lineage.
- Add dedicated UUID identity, append-only SQLite history/command receipts, integrity reconstruction, restart replay, rollback/retry, indexed immutable cumulative sums, and `BEGIN IMMEDIATE` enforcement that prevents concurrent partial receipts from jointly exceeding executed quantity.
- Expose `POST /api/v1/opportunities/{opportunity_id}/goods-receipts` with strict factual DTOs, 100-unit 60/40 partial-receipt and concurrent over-receipt safety coverage, bounded errors, request-owned cleanup, and strict independence from Actual Acquisition Settlement, marketplace Inventory Snapshot, mutable owned inventory, legacy Actual Economics, returns, sales, and Actual Outcome.

## CR-1B6A2 - Actual Acquisition Settlement Authority and Production API

- Implement ADR-0051 as immutable `BLOCKED`/`COMPLETE` actual-acquisition settlement revisions over one exact Purchase Execution Record, preserving the five fixed cost categories, explicit other-mandatory-cost scope/items, dedicated actual evidence and actual FX settlement provenance, original batch money, deterministic normalized batch totals, and executed-quantity per-unit totals.
- Add exact-predecessor append-only SQLite history/receipts, replay-first command handling, integrity reconstruction, rollback/retry, request-owned connection lifecycle, unique revision/predecessor/COMPLETE cardinality, terminal DB enforcement, and multi-connection no-fork concurrency safety.
- Expose `POST /api/v1/opportunities/{opportunity_id}/actual-acquisition-settlements` with explicit factual DTOs, Decimal-string responses, BLOCKED-to-COMPLETE API revision journey, same/cross-currency operation, bounded errors, and strict isolation from planned FX, Goods Receipt, inventory, legacy Actual Economics, sale economics, Actual Outcome, and Variance.

## CR-1B5D2M - Purchase Execution Record Authority and Production API

- Add ADR-0050 and an immutable exact-match `PurchaseExecutionRecord` that binds one Founder-reported external purchase to one exact persisted READY Real-Money Execution Intent and reconstructs its full O2 Capital/Supplier/Product/Quote lineage.
- Add dedicated UUID identity, evidence references, append-only SQLite history/receipts, intent-level durable cardinality, exact replay/equivalent-event aliasing, integrity reconstruction, rollback/retry, and multi-connection concurrency safety.
- Expose `POST /api/v1/opportunities/{opportunity_id}/purchase-execution-records` through one request-owned connection and prove the software API-only READY-to-record journey while leaving actual supplier ordering, payment, goods receipt, inventory, and Actual Economics unchanged.

## CR-1B5D2L - Capital Gate, Approval, and Execution Intent Production Wiring

- Expose Intended Order Quantity, Deployable Capital Snapshot, Planned Acquisition Capital Requirement, Capital Gate, Founder Capital Approval, and Real-Money Execution Intent through six independent request-scoped FastAPI boundaries with production UUID identities and one reusable UTC clock.
- Preserve exact O2/Sourcing/Quote/Normalization/Readiness lineage, Decimal-string money, explicit upfront-scope verification and Founder approval, the mandatory post-Approval capital snapshot, business-state 2xx responses, historical replay, and one-READY-per-Approval cardinality without latest lookup or automatic chaining.
- Prove an API-created O2 can move from `READY_FOR_CAPITAL_REVIEW` to `READY_FOR_MANUAL_EXECUTION` with no direct DB mutation or private Application invocation between calls; this remains a manual-purchase handoff and does not create a Purchase Execution Record, execute payment, or mutate Actual Economics/inventory.

## CR-1B5D2J - Critical Cost v2 and Capital Readiness Production Wiring

- Expose the existing Critical Cost v2 and Capital Readiness v2 owners through thin Opportunity-scoped FastAPI routes with one owned SQLite connection per request and exact persisted source IDs only.
- Preserve exact O2 Landed Cost/Normalization/Allocation/FX/Verified Economics and terminal Conservative/Market/Critical manifests, replay-first behavior, deterministic BLOCKED/INCOMPLETE outcomes, Quote validity, and normalization-equality safety.
- Verify the API-only O2 path to `READY_FOR_CAPITAL_REVIEW`, normalization mismatch and all required BLOCKED paths, replay/restart/concurrency, bounded errors, atomic failure, cleanup, and historical v1 compatibility without adding Capital Gate or execution scope.

## CR-1B5D2I1 - Critical Cost Exact Normalization Authority Reconciliation

- Add Critical Cost policy/schema/command v2 over one exact persisted Acquisition Cost Normalization while preserving historical v1 reconstruction and replay unchanged.
- Validate exact Landed Cost, resolved Shipping Allocation Authority and FX Observation provenance without repeating normalization arithmetic; preserve exact normalization/allocation/FX IDs and allow the supported O2 CNY-to-KRW path to become COMPLETE.
- Add fresh Capital Readiness assessment schema v2 with exact Critical Cost/Economics normalization-ID equality while retaining policy 1.0.0, historical schema-v1 replay, Gate compatibility, and no API/UI or Capital decision expansion.

## CR-1B5D2H - O2 Acquisition and Economics Production Chain Wiring

- Expose the existing exact Sourcing Economics Binding, Landed Cost, Shipping Allocation, FX Observation, Acquisition Cost Normalization, and Economics Source Composition owners through request-scoped production APIs.
- Preserve exact O2 lineage, explicit allocation/FX authority, Decimal-string values, independent append-only transactions, replay/restart, bounded errors, and legacy generic sourcing compatibility without latest selection or hidden defaults.
- Verify an API-only O2 Sourcing-to-Conservative Economics CALCULABLE journey plus unresolved allocation, missing FX, same-currency no-FX, BLOCKED composition, mixed O1/O2, rollback, and connection-cleanup safety paths.

## CR-1B5D2G - O2 Domestic Market Validation Production API Wiring

- Add the request-scoped `POST /api/v1/opportunities/{opportunity_id}/domestic-market-validations` production entry over the existing ADR-0044 Application owner and one shared SQLite connection.
- Require exact persisted Opportunity/KR Market and Competition/Demand source lineage while keeping Founder/operator review facts factual and all validation state, reason, identity, and server times authoritative.
- Verify API-only O1-to-O2-to-Competition-to-Demand-to-Domestic-Validation operation, VALIDATED and BLOCKED outcomes, replay/restart/concurrency, bounded errors, rollback, cleanup, legacy KR compatibility, and Economics/Capital/Validation Queue isolation.

## CR-1B5D2F - O2 Operational Market and Verified Economics Ingress Eligibility

- Replace Validation Queue membership as the Competition, Demand, and Verified Economics Opportunity-existence test with one shared exact non-archived Opportunity lifecycle and immutable Market-binding read contract.
- Allow a persisted Domestic Selling O2 to use the existing production ingress routes without creating a `validation_queue_admission_snapshot`, while preserving exact Market identity checks, legacy queue behavior, replay, restart, conflict, and bounded-error semantics.
- Add an API-only O1-to-O2 continuation regression that admits O2 Competition, Demand, and O2-owned Verified Economics facts and proves that O1 Economics is neither copied nor relabelled.

## CR-1B5D2D - Domestic Selling Opportunity and O2 Sourcing Production Wiring

- Add the request-scoped `POST /api/v1/opportunities/{source_opportunity_id}/domestic-selling-admissions` production boundary with exact persisted O1 reconstruction, server-owned O2/admission identities and times, bounded HTTP errors, replay, rollback and cleanup.
- Extend the existing Sourcing admission API additively with an explicit domestic admission-ID lineage variant; reconstruct exact O1/O2/KR provenance in the Application while preserving the legacy Candidate request and required verified Supplier Product Match.
- Verify the API-only O1-to-O2-to-Sourcing journey, restart and concurrent replay, failure isolation and legacy compatibility without adding Economics, Market Validation, Capital, execution, UI, authentication, crawling or autonomous behavior.

## CR-1B5D2C - Domestic Selling Opportunity to Sourcing Lineage Handoff

- Add an immutable `DomesticSellingProductLineage` variant that binds a new O2-owned Founder Sourcing Admission to one exact persisted Domestic Selling Opportunity Admission while preserving O1 only as provenance.
- Keep the legacy Candidate-Promotion lineage payload and v2 persistence unchanged; persist domestic lineage as an additive discriminated v3 payload with restart/replay integrity.
- Reuse the existing Founder Sourcing owner, Supplier Quote, verified Product Match and Sourcing Economics Binding without copying O1 quotes/Economics or adding API, UI, automatic matching or Capital behavior.

## CR-1B5D2B1 - Domestic Selling Opportunity Admission SQLite Persistence

- Add one shared-connection SQLite repository that atomically commits the existing O2 `DISCOVERED` version 1 lifecycle/current transition, immutable KR Market binding, domestic-selling admission and command receipt.
- Preserve exact O1 Candidate Promotion, Product Snapshot and Market provenance, enforce one-O1-to-one-O2 and one-O2-to-one-admission cardinality with database uniqueness, and leave O1 unchanged.
- Add append-only admission/receipt tables, exact and restart replay, rollback at every write phase, multi-connection convergence, malformed persistence rejection, and explicit connection ownership without API or downstream orchestration.

## CR-1B5D2B - Domestic Selling Opportunity Admission Foundation

- Implement ADR-0049 as an immutable Domain/Application authority that preserves one exact foreign/source Opportunity O1 and creates a distinct KR domestic-selling Opportunity O2.
- Reconstruct exact O1 lifecycle, Candidate Promotion, Product Observation Snapshot and immutable Market binding; require explicit Founder/operator product-equivalence confirmation and an evidence reference without title, similarity or canonical-string inference.
- Add the versioned KR-only listing/canonical-product policy, replay-first command/receipt port, `DISCOVERED` version 1 O2 lifecycle and exact KR Market-binding construction, plus dedicated opaque UUIDv4-style O2/admission identity suppliers.
- Defer SQLite atomic persistence, Sourcing domestic-lineage handoff, production API/UI, trusted operator injection, Economics copying, Capital decisions and generalized cross-market mapping.

## CR-1B5D1 - Real-Money Execution Intent Authority

- Implement ADR-0048 as an immutable pre-purchase authority over one exact Founder Capital Approval, exact Gate/Requirement/Intended Quantity/Sourcing Quote lineage, one explicitly selected post-Approval Deployable Capital snapshot, and current Founder confirmation.
- Produce only `READY_FOR_MANUAL_EXECUTION` or durable `BLOCKED` with deterministic reasons; enforce exact amount, quantity, unit, currency, Quote revision and execution-time validity without partial execution, tolerance, latest-source selection, bank lookup, reserve subtraction, or upstream reevaluation.
- Add a dedicated opaque identity, replay-first Application owner, and append-only SQLite history/receipts with atomic rollback, restart reconstruction, malformed-state rejection, alias receipts for equivalent actions, and a database-level one-READY-intent-per-Approval invariant.
- Add no purchase/order execution, Supplier checkout, payment, fund transfer, Purchase Execution Record, inventory/Actual Economics mutation, API/UI, revocation, or staged release.

## CR-1B5C - Founder Capital Approval Authority

- Add an immutable ADR-0047 human authorization fact over one exact persisted Capital Gate `PASS`, preserving its Opportunity, policy, Requirement, Deployable Capital, Intended Quantity, and evaluation time.
- Require the Founder-supplied positive approved amount to equal the full exact Planned Acquisition Capital Requirement and its currency; reject partial, excess, cross-currency, blocked, and rejected Gate approvals without staged-release or FX inference.
- Add a dedicated opaque approval identity, replay-first Application owner, and separate server admission/receipt clocks while keeping factual Founder identity and approval time caller-owned.
- Persist approval and receipt atomically in two dedicated append-only SQLite tables with restart reconstruction, rollback, concurrency convergence, malformed-state rejection, exact Gate integrity, and read-only safety.
- Add no automatic approval, generic `FounderDecision` mapping, revocation/expiry policy, purchase execution, fund transfer, bank integration, API/UI, or autonomous purchasing.

## CR-1B5B - Capital Gate Authority

- Add the immutable ADR-0046 Capital Gate over one exact persisted Capital Readiness assessment, Planned Acquisition Capital Requirement, and Founder-declared Deployable Capital snapshot.
- Preserve exact Conservative Economics and Sourcing lineage while separating `BLOCKED` source safety from `REJECTED` complete-fact policy outcomes and `PASS` eligibility for future Founder approval.
- Apply only the explicit v1 strict-positive economics, same-currency capital sufficiency, and known-MOQ constraints; add no hidden ROI/margin/profit threshold, reserve subtraction, FX, position, or concentration policy.
- Persist exact sources, evaluated facts, policy, ordered reasons, result, and receipt atomically in dedicated append-only SQLite tables with replay-first issuance, restart reconstruction, rollback, concurrency convergence, corruption detection, and read-only integrity checks.
- Add no Founder Capital Approval, spending authorization, order execution, API/UI, bank integration, or change to existing Capital Readiness, Sourcing, Economics, and Requirement contracts.

## CR-1B5B0B - Planned Acquisition Capital Requirement

- Add the immutable ADR-0046 Planned Acquisition Capital Requirement over one exact Intended Order Quantity, one exact Acquisition Cost Normalization, and an embedded exact upfront-cost scope verification.
- Prove Opportunity plus Sourcing Binding/Admission/Quote lineage before using Decimal-only 34-significant-digit `ROUND_HALF_EVEN` multiplication; never substitute MOQ, quoted quantity, or a shipping denominator for Founder intent.
- Produce an authoritative amount only for a verified-complete upfront-cost scope; unresolved or additional unmodelled mandatory upfront cash remains `BLOCKED` with no numeric amount or miscellaneous-cost fallback.
- Persist exact sources, verification, policy, arithmetic result, state/reasons, and receipt atomically in two dedicated append-only SQLite tables with replay-before-identity/time, restart reconstruction, rollback, concurrency convergence, malformed-state rejection, and read-only integrity checks.
- Add no Deployable Capital comparison, Capital Gate, profit/ROI rule, additional-cost calculator, API/UI, or change to existing Sourcing/Normalization schemas.

## CR-1B5B0A - Capital Investment Facts Foundation

- Add immutable Founder-owned Intended Order Quantity and reserve-adjusted Deployable Capital Snapshot facts without creating Capital Requirement, Gate, or approval semantics.
- Bind purchase intent to one exact Opportunity and Sourcing Admission/Quote revision while prohibiting MOQ, quoted-quantity, and shipping-denominator inference.
- Preserve explicit non-negative Decimal deployable capital, including factual zero, exact currency and `as_of`, operator identity, and a versioned reserve-adjusted semantic marker without bank lookup or reserve arithmetic.
- Add dedicated opaque identity suppliers, replay-first Application owners, and four append-only SQLite history/receipt tables with atomic commit, restart reconstruction, rollback, concurrency convergence, malformed-state rejection, and read-only reconstruction.
- Keep upfront-cost scope verification, Planned Acquisition Capital Requirement, Capital Readiness, Capital Gate, Founder Capital Approval, API/UI, and existing Sourcing schemas unchanged.

## CR-1B5A - Capital Readiness Authority

- Add a dedicated immutable Capital Readiness Domain/Application authority that answers only whether one exact Opportunity's Capital-facing evidence is complete and internally consistent enough for Capital Gate evaluation.
- Require exact CALCULABLE Conservative Economics, VALIDATED_FOR_CAPITAL Domestic Market Validation, COMPLETE Critical Cost, VERIFIED_MATCH Sourcing Admission, exact Binding/Quote lineage, and a Quote valid at the fresh evaluation time.
- Preserve negative-but-calculable economics as eligible without profit, margin, ROI, required-capital, reserve, exposure, investment, or Founder-approval thresholds.
- Persist exact source manifests and receipts atomically in dedicated append-only SQLite tables with replay-before-identity/time, historical quote-time semantics, restart reconstruction, rollback, concurrency convergence, malformed-state rejection, and read-only source integrity checks.
- Add ADR-0045 while leaving Decision Readiness, Production Safety, Capital Gate, Founder lifecycle, API/UI, and all source policies unchanged.

## CR-1B5A0A - Domestic Market Validation Assessment Foundation

- Add the immutable ADR-0044 Domain/Application authority that validates one exact persisted KR Opportunity, Competition source, Demand source, and explicit operator current-use verification event.
- Require complete v1 Competition/Demand metrics with observation-bearing status, exact provenance, non-future factual times, deterministic blockers, and no numeric freshness window.
- Persist assessment and receipt history atomically in dedicated append-only SQLite tables with replay-before-identity/time, restart reconstruction, rollback, concurrency convergence, corruption detection, and exact source-lineage checks.
- Preserve optional human-verified External Signals as assisted exact references only; they cannot replace required Competition or Demand sources.
- Add no API/UI, source collection, profitability calculation, Capital Readiness/Gate, Founder capital approval, Decision Readiness change, or automatic trust policy.

## CR-1B4B1 - Conservative Economics Production Entry and API

- Add an Opportunity-scoped production entry and `POST /api/v1/opportunities/{opportunity_id}/conservative-economics` over the existing exact-source Conservative Economics authority.
- Accept only caller-owned command, exact source, explicit scenario, and request-time facts; inject the authoritative policy, UUIDv4 result identity, and separate UTC calculation/commit clocks server-side.
- Return committed/reconstructed Decimal economics and lineage with HTTP 201 fresh or 200 replay; preserve BLOCKED and negative CALCULABLE results as successful business outcomes.
- Bound missing source, conflict, validation, and persistence failures to 404/409/422/503 while hiding SQLite details and closing request-scoped resources.
- Add no formula/policy/schema change, latest-source selection, legacy calculator call, UI, Capital Readiness/Gate, Founder approval, or investment decision.

## CR-1B4B - Conservative Economics Implementation

- Add a dedicated immutable Conservative Economics Domain/Application authority that consumes only one exact Economics Source Composition and an explicit sale-price-factor scenario.
- Calculate unit sale price, marketplace/payment fees, fixed fee, total cost, profit, margin, and new `conservative_acquisition_roi` with a 34-significant-digit `ROUND_HALF_EVEN` Decimal policy.
- Enforce ADR-0043: only verified-zero tax and duty are calculable, non-zero/untrusted tax or duty blocks, unresolved other cost blocks, and non-positive acquisition cost never produces ROI.
- Preserve estimated sale-price evidence, explicit assumptions, negative-but-calculable economics, exact source lineage, policy/version, and no legacy purchase/shipping or ROI aliases.
- Persist immutable result and receipt history atomically in dedicated append-only SQLite tables with exact replay, restart reconstruction, rollback, concurrency convergence, malformed arithmetic rejection, and read-only reconstruction.
- Add no legacy calculator change, Actual Economics change, monthly forecast, API/UI, Capital Readiness/Gate, position sizing, Founder approval, or investment decision.

## CR-1B4B0 - Conservative Economics Semantic Authority

- Define the safe MVP duty policy: only explicit verified zero contributes zero; unresolved, weak, missing, or non-zero duty blocks until exact per-unit target-currency authority exists.
- Define the safe MVP tax policy: the legacy gross-sale-price formula is not promoted to Capital authority; only explicit verified zero contributes zero until scoped tax applicability and seller-cost treatment exist.
- Define new `conservative_acquisition_roi` as conservative unit profit divided by exact normalized acquisition cost per unit, with a strictly positive denominator.
- Preserve legacy `roi`, `landed_cost_roi`, and Actual ROI meanings without aliases or migration; defer Actual acquisition-ROI symmetry.
- Add no financial calculation, persistence, API, UI, Capital Readiness/Gate, or investment decision.

## CR-1B4A - Authoritative Economics Source Composition

- Bind one exact persisted Acquisition Cost Normalization and one exact immutable Verified Economics Snapshot into a dedicated source-only manifest for future Conservative Economics.
- Prevent acquisition double-counting by excluding legacy purchase/shipping fields while preserving expected sale price, fee rates, fixed fee, tax, duty, and other-cost evidence exactly.
- Add deterministic READY/BLOCKED source semantics that preserve missing/unsupported facts, explicit verified zero, estimated sale-price status, currency mismatch, and a blocker for non-zero unscoped `other_cost`.
- Persist immutable composition and receipt history atomically in dedicated append-only SQLite tables with exact replay, restart reconstruction, rollback, concurrency convergence, malformed-state rejection, and read-only source reconstruction.
- Add no profit, ROI, margin, Conservative assumptions, Capital Readiness/Gate, Founder approval, Actual Economics change, API, UI, or external integration.

## CR-1B3E - Authoritative Acquisition Cost Normalization

- Add a dedicated immutable normalization owner over one exact Landed Cost Composition, ordered exact Shipping Allocation Authority facts, exact FX Observations, and an explicit target currency.
- Normalize only the four acquisition components with explicit `PER_UNIT`, resolved `PER_ORDER`, or resolved `PER_QUOTED_QUANTITY` semantics; block `PER_WEIGHT`, `UNSPECIFIED`, missing sources, and UNKNOWN without MOQ or latest-source inference.
- Preserve direct or explicit inverse use of the same FX observation and deterministic Decimal-only policy v1 arithmetic at 34 significant digits with `ROUND_HALF_EVEN` and no intermediate money quantization.
- Persist ordered component provenance, exact source manifest, target currency, policy, result, and receipt atomically in dedicated append-only SQLite histories with replay, restart, rollback, concurrency, and malformed-state protection.
- Add no external FX lookup, sale-side Economics composition, Conservative Economics, Capital Readiness/Gate, Founder approval, Actual Economics change, API, or UI.

## CR-1B3C1 - Shipping Allocation Authority Reconciliation and Persistence

- Separate explicit allocation-basis authority from denominator authority for one exact persisted Landed Cost shipping component without mutating composition history.
- Reconcile production `UNSPECIFIED` shipping through operator/evidence-backed `PER_UNIT`, `PER_ORDER`, or `PER_QUOTED_QUANTITY` admission while keeping `PER_WEIGHT` and unapproved `UNSPECIFIED` unresolved.
- Preserve the non-negotiable MOQ separation, exact quoted-quantity provenance, operator factual time, server admission/commit times, and a dedicated opaque authority identity.
- Persist authority and receipt histories atomically in append-only SQLite with exact replay, restart reconstruction, rollback, concurrency convergence, malformed-state rejection, and no latest-source selection.
- Add no division, FX conversion, rounding, Critical Cost policy change, Economics calculation, Capital Readiness/Gate, API, or UI.

## CR-1B3B1 - Critical Cost Completeness SQLite Persistence

- Add replay-first Application publication with a dedicated server-owned opaque assessment identity held by immutable receipt/history persistence rather than the Domain assessment value.
- Persist exact composition, Sourcing lineage, Verified Economics Opportunity/time/version, policy name/version, evaluation and commit times, state, and ordered structured reasons in two dedicated append-only SQLite tables.
- Provide atomic fresh publication, exact restart replay, changed-command conflict, rollback cleanup, separate-connection convergence, malformed persistence rejection, and read-only reconstruction without policy re-evaluation.
- Preserve UNKNOWN blockers and the absence of profit/ROI results without changing Critical Cost policy, existing schemas, Economics, Production Safety, Decision Readiness, Actual Economics, Snapshot Chain, API, or UI.

## CR-1B3B - Critical Cost Completeness and UNKNOWN Safety

- Add an immutable, policy-versioned Critical Cost Completeness assessment over one exact Landed Cost Composition, Sourcing Binding/Admission revision, and Verified Economics Snapshot.
- Block unknown purchase/shipping, unresolved positive shipping allocation, mixed currency without authoritative FX, missing or weak required Economics evidence, and missing/expired quote validity with deterministic structured reasons.
- Preserve explicit known zero and authoritative not-applicable shipping without inferring allocation, dividing by MOQ, selecting a later quote, or creating an FX rate.
- Keep existing Discovery/operational calculator fallback as a non-Capital compatibility path while ensuring an incomplete assessment exposes no profit/ROI and cannot authorize a future Capital calculation.
- Keep Production Safety, Decision Readiness, Actual Economics, Snapshot Chain, Conservative Economics, Capital Readiness/Gate, Founder approval, API/UI, and assessment persistence unchanged.

## CR-1B3A - Landed Cost Composition Domain Contract

- Define an immutable acquisition-side composition over one exact Sourcing Economics Binding with four independent canonical cost components.
- Preserve KNOWN/UNKNOWN/NOT_APPLICABLE, known zero, mixed source currencies, MOQ, quoted quantity, quote evidence, and opaque identity without aggregation.
- Mark unit price as per-unit while retaining shipping allocation as explicitly unspecified; no MOQ multiplication, FX conversion, or inferred basis is introduced.
- Add an Application owner and replay repository port while deferring SQLite until allocation semantics are stable.
- Add no Verified Economics generation, calculator/formula, Critical Cost, Capital policy, Actual Economics, API/UI, collector, or Snapshot Chain changes.

## CR-1B2B - Immutable Exact Sourcing Economics Binding

- Bind an Opportunity explicitly to one exact authoritative Sourcing Admission and Quote revision using an opaque immutable binding identity.
- Persist append-only binding history and replay receipt atomically with exact restart replay, changed-payload conflict, lineage validation, and no current/latest projection.
- Preserve caller request time separately from server binding/commit times and expose a narrow future Economics source reference without calculating or mapping costs.
- Add no Verified Economics creation, formula, UNKNOWN handling, Capital policy, Snapshot Chain, API/UI, or supplier integration changes.

## CR-1B1 - Founder-Assisted Sourcing Production Entry

- Expose strict Founder Sourcing Admission and Quote Revision command routes using the existing CR-0B/0C/0B1 Domain, Application, replay, and SQLite contracts.
- Add Sourcing-specific production UUID identity suppliers, request-scoped repository ownership, and separate UTC admission/receipt clock composition.
- Return committed or reconstructed authoritative Supplier, Product, quote, verified match, lineage, evidence, requested/verified/admitted/committed timestamps, and schema versions.
- Preserve exact restart replay, changed-payload conflict, explicit UNKNOWN/NOT_APPLICABLE facts, transaction rollback, and concurrent convergence without adding supplier deduplication, OCR automation, Economics, Capital policy, Snapshot Chain changes, or UI.

## CR-0B1 - Sourcing Admission Timestamp Authority Hardening

- Separate caller-owned command `requested_at`, operator factual `verified_at`, server-owned Admission `admitted_at`, and Receipt `committed_at`.
- Preserve requested and admitted times independently in immutable Admission v2 persistence while refusing to infer authority for legacy v1 rows.
- Keep exact replay lookup ahead of identity issuance and both server clocks; persisted timestamps are reused without new rows or clock calls.
- Apply the same authority and replay ordering to quote revisions without adding FastAPI, supplier deduplication, Economics, or Capital policy.

## CR-0C - Sourcing Authority SQLite Persistence and Replay

- Persist exact Founder Sourcing Admission, opaque Supplier and Sourcing Product identities, verified Product match, immutable quote revisions, evidence, Economics source reference, and command receipt in append-only SQLite history.
- Use `BEGIN IMMEDIATE` for fresh admission and quote-revision transactions with phase-specific failures, complete rollback, restart-safe exact replay, changed-payload conflict, and separate-connection convergence.
- Reconstruct and validate every referenced immutable fact, schema version, payload fingerprint, revision relationship, selling/source lineage, and explicit unknown value without correction or numeric fallback.
- Add no Supplier deduplication, API/UI, collector/OCR wiring, Economics formula, Snapshot Chain, Capital Readiness, Capital Gate, or approval behavior.

## CR-0B - Founder-Assisted Sourcing Authority Domain Contract

- Add immutable Supplier, Sourcing Product, quote revision, explicit shipping scope, evidence reference, selling-product lineage, and Human-verified match contracts without reusing marketplace seller or grouping semantics.
- Preserve unknown money, MOQ, quoted quantity, shipping, and lead time as explicit absence rather than numeric zero.
- Add an Application-owned manual admission and quote-revision boundary with opaque injected identities, deterministic command fingerprints, receipts, exact replay, changed-payload conflict, and a narrow repository Protocol.
- Define a future exact sourcing-to-Economics source reference while adding no SQLite, API/UI, OCR, supplier adapter, formula, Snapshot Chain, Capital Readiness, Capital Gate, or approval changes.

## PR36-D.1 - Persisted Discovery Execution Entry

- Add an Application workflow owner that commits or exactly replays one immutable `DiscoveryCommand` before invoking the production Discovery runtime.
- Execute the existing Engine from the authoritative committed command and forward all nineteen execution-affecting parameters without changing Engine calculations or Domain contracts.
- Preserve the committed command when runtime execution fails; persistence failure prevents any runtime call.
- Keep Observation, Group, DiscoveryExecutionResult, Candidate, Promotion, Snapshot, Composition Root wiring, and workflow progress storage outside this PR.

## PR35-E3 - Economics Explicit Price Source Handoff and Owner Wiring

- Upgrade EconomicsCalculation Snapshot to v3 with exact Candidate and PriceIntelligence Snapshot provenance while retaining its Opportunity subject, promotion binding, and Verified Economics source.
- Add an immutable source context and owner command that validates the exact Price analysis receipt, Candidate/Opportunity binding, Market identity, and persisted VerifiedEconomicsInput before invoking the existing calculator.
- Atomically persist complete calculation Snapshot and immutable receipt with replay, conflict, rollback, deterministic read queries, append-only triggers, and separate-connection convergence.
- Treat Price as provenance only: no recommended-price injection, evidence parsing, latest selection, formula change, migration, backfill, Snapshot Chain binding, or Production Safety execution.

## PR35-E2 - Price Intelligence Analyzer Owner Wiring

- Add an authoritative command boundary that loads explicit ordered Product Snapshot IDs, validates their exact finalized-group source bindings, reconstructs runtime Products losslessly, and calls the existing Price Analyzer without formula changes.
- Persist the resulting Candidate-scoped PriceIntelligence Snapshot and immutable analysis receipt atomically, preserving explicit fallback multiplier, Analyzer version, request/generation/commit timestamps, and command fingerprint.
- Add deterministic restart/response-loss replay, changed-command conflict, repeated analysis facts for distinct commands, append-only receipts, rollback, and separate-connection concurrency.
- Add no latest Product selection, regrouping, Collector call, Economics handoff, Snapshot Chain binding, Safety execution, orchestrator wiring, migration, or backfill.

## PR35-E1 - Product Snapshot Source Reference and Owner Wiring

- Add a collector-owned post-issuance capture boundary over one exact finalized group and its ordered persisted collector observations.
- Persist immutable source bindings and replay receipts atomically with Product Snapshot history under `BEGIN IMMEDIATE`.
- Preserve Product Snapshot v2; exact replay and alias receipts are supported, while changed commands and duplicate source publication under new Snapshot IDs conflict.
- Defer Price/Economics owner wiring, complete Snapshot Chain binding, and Production Safety execution to PR35-E2-E4.

## PR35-D - Opportunity-Scoped EconomicsCalculation Snapshot SQLite Persistence

- Upgrade EconomicsCalculation Snapshot to v2 with an exact Candidate/Opportunity promotion binding reference while retaining its authoritative Opportunity and Verified Economics source.
- Persist complete typed results, Money/Evidence, profitability provenance, calculation parameters, canonical analysis/version/fingerprint, calculation version, generation time, and full payload fingerprint as immutable history.
- Validate lifecycle, promotion binding, Market identity, and Verified Economics source inside one `BEGIN IMMEDIATE` transaction; add exact replay, repeated calculation support, rollback, deterministic queries, malformed persistence detection, append-only triggers, and separate-connection concurrency.
- Do not infer a Price Snapshot: the existing calculator consumes VerifiedEconomicsInput and preserves no authoritative Price Snapshot ID. Add no latest-source lookup, calculator execution, Safety execution, current projection, migration, or backfill.

## PR35-C - Candidate-Scoped PriceIntelligence Snapshot SQLite Persistence

- Persist PriceIntelligence Snapshot v2 as an immutable Candidate-scoped Analyzer fact with exact ordered Product Snapshot IDs, Market identity, Analyzer version, Decimal outputs, sample size, generation time, schema version, and integrity fingerprint.
- Validate persisted Candidate/Context and every Product Snapshot's version, fingerprint, Candidate subject, and Market identity inside one `BEGIN IMMEDIATE` transaction without rerunning grouping, Analyzer, or fallback logic.
- Add exact snapshot-ID replay, changed-payload conflict, same-cohort new Snapshot support, restart round-trip, deterministic Candidate/Market queries, rollback, append-only triggers, malformed persistence detection, and separate-connection concurrency.
- Add no current projection, Product writes, Economics persistence, promotion changes, Safety execution, handoff creation, migration, or backfill.

## PR35-B - Candidate-Scoped Product Observation Snapshot SQLite Persistence

- Persist Product Observation Snapshot v2 as a file-backed, append-only Candidate fact with complete Product, Collector provenance, Market identity, observation time, schema version, and deterministic integrity fingerprint.
- Validate authoritative persisted Candidate/Context and exact discovery reference, Market identity, marketplace, and listing item inside one `BEGIN IMMEDIATE` transaction.
- Add exact snapshot-ID replay, changed-payload conflict, multiple observations per Candidate, deterministic Candidate/Market queries, restart reconstruction, append-only triggers, rollback, and separate-connection concurrency.
- Deliberately add no current projection, provenance uniqueness, Discovery Observation ID reuse, Collector wiring, Price/Economics persistence, Safety execution, migration, or backfill.

## PR35-A - Candidate-Scoped Snapshot Subject Alignment

- Align Product Observation and PriceIntelligence snapshot schema v2 contracts with their pre-admission `OpportunityCandidateIdentity` owner and change repository lookup boundaries from Opportunity to Candidate.
- Keep Verified Economics and EconomicsCalculation Opportunity-scoped because their authoritative source exists only after admission; never substitute Candidate ID for an Opportunity key.
- Require Production Safety evaluation context to bridge the Candidate source chain to post-admission Economics through an immutable Candidate/Opportunity promotion binding while preserving exact Market identity and runtime scalar reconstruction.
- Upgrade complete-only Admission Snapshot Chain handoff to schema v2 with an explicit promotion binding reference and no optional, fake, or inferred Snapshot IDs.
- Add explicit Candidate subject, Opportunity binding, Market identity, incomplete-chain, reference-conflict, malformed, and unsupported-version taxonomy without persistence, owner wiring, calculation, or Safety execution.

## PR34-E - Candidate-to-Opportunity Admission Promotion Foundation

- Add an immutable promotion command, one-to-one Candidate/Opportunity binding, and one-to-many command receipts while keeping Candidate and Opportunity identity separate.
- Reload authoritative persisted Candidate, Context, and issuance lineage; derive neither discovery reference nor Market identity from caller data.
- Extend the existing SQLite Validation Admission boundary so lifecycle current/history, admission snapshot, market binding, Candidate binding, and receipt commit under one `BEGIN IMMEDIATE` transaction.
- Add exact restart replay, changed-command conflict, alias receipt, append-only triggers, deterministic read queries, and rollback coverage without Snapshot IDs, Safety execution, migration, or backfill.
- Keep Snapshot-chain handoff explicitly unavailable until authoritative Snapshot owner wiring exists.

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
# PR35-E4 - Complete Snapshot Chain Binding Persistence

- Add a complete-only immutable Opportunity Snapshot Chain binding over exact promotion, ordered Product, PriceIntelligence, EconomicsCalculation, and Verified Economics source facts.
- Persist versioned binding history, normalized ordered Product membership, and replay receipts atomically under `BEGIN IMMEDIATE`; exact duplicate source sets alias the original binding.
- Reconstruct Production Safety evaluation context and runtime inputs by exact binding and Product member IDs without latest inference, analyzer/calculator execution, or Safety execution.
- Keep legacy Opportunities unbound: no migration, backfill, current projection, production orchestrator, Decision, Review, Dashboard, or Safety persistence change.
# PR36-A - Production Safety Evaluation and Persistence

- Evaluate an explicit complete Snapshot Chain binding and Product member through the existing runtime adapter and unchanged `assess_production_safety` engine.
- Persist immutable operational evaluation history, exact source provenance, replay receipts, and a controlled current projection atomically.
- Make operational current available to Decision Readiness while keeping admission-time Safety snapshots isolated as legacy outcomes without migration or backfill.
- Add no Safety API/UI, source inference, formula/status change, Decision policy change, or production orchestration.
# PR36-B - Operational Production Safety Decision Integration

- Use validated operational Production Safety current as the authoritative production source for Readiness and Decision finalization, with no legacy fallback.
- Preserve the exact operational evaluation ID in Decision Composition provenance and revalidate current/history/provenance inside the composition transaction.
- Load the immutable Safety evaluation named by a finalized composition for Dashboard Decision reconstruction, even after operational current advances.
- Map missing or malformed required composition sources to bounded 409 business conflicts while retaining 503 for persistence/transaction failures.
# PR36-C - Production Safety Operational API and UI

- Add read and POST APIs for explicit complete-chain/Product operational Safety evaluation with 201 initial commit and 200 exact replay.
- Add persisted binding/Product/current Safety DTOs and an accessible Opportunity Detail source-selection form with deterministic retry metadata.
- Refetch authoritative Safety detail and Decision Readiness after success; do not optimistically mutate state or automatically Finalize.

# CR-1B3A1 - Landed Cost Composition SQLite Persistence

- Persist immutable Landed Cost Composition and replay receipt history atomically with exact Sourcing Economics Binding and Opportunity lineage.
- Preserve ordered components, distinct known-zero/unknown/not-applicable states, source currencies, allocation bases, MOQ/quoted quantity, evidence, and timestamps without calculation or normalization.
- Add restart-safe exact replay, changed-payload conflict, append-only triggers, rollback/concurrency convergence, corruption detection, and read-only reconstruction.

# CR-1B3D - Authoritative FX Observation Foundation

- Add domain contracts for `FXObservation` and `FXObservationProvenance` with canonical pair semantics (`base/quote`, Decimal rate, timezone-aware timestamps, schema version) and repository-independent admission command/value validation.
- Add authoritative application boundary `AdmitFXObservation` with replay-first execution, server-owned observation identity, and authoritative admission timestamp.
- Enforce non-conversion trust boundary: this layer stores raw authoritative FX facts only, does not create inverse rates, freshness policy, or normalization decisions.
- Defer persistence, inverse derivation, and exchange-rate-based normalization to follow-up PRs; require explicit historical binding in future normalization.
- Preserve strict authority boundary: no cross-policy coupling, no Capital policy logic, no Currency conversion side effects at this layer.
