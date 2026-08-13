# HYB System Architecture

## Competition v2 observation identity

ADR-0063 separates server-owned Competition v2 publication identity from the
caller-declared immutable bounded cohort identity. Current schemas persist a
one-to-one append-only observation/cohort mapping. Legacy schemas reconstruct a
versioned deterministic compatibility identity without migration or writes.
Receipts and existing command/cohort fingerprints remain cohort-based and
unchanged.

## Demand v2 evidence foundation (CR-1B7D4G)

Demand v2 is an additive authority boundary beside Demand v1. It persists one
provider-scoped Market Intent fact family and one immutable bounded Comparable
Market Response family, with optional rating/provider envelopes. Demand v2 has
dedicated publication, current-projection, receipt, fingerprint, observation,
assessment, and policy namespaces. It may pin an immutable Competition v2
cohort, but Demand owns its listing review/rating facts and never copies a
Competition assessment. No Decision Composition v2 or DMV v2 wiring is added.

## Demand v2 evidence authority direction

ADR-0062 preserves Demand v1 and introduces a separate, not-yet-implemented
Demand v2 authority for pre-listing new-to-market assessment. Its mandatory core
has two independent families: one exact provider-scoped KR query/search count
for Market Intent, and raw per-listing review counts from one immutable bounded
comparable-organic-listing cohort for Comparable Market Response. Different
provider counts remain separate; ranks, indices, rating, estimated sales,
sponsored context, and post-listing target traction are optional.

Demand v2 derives review coverage, sorted review counts, median review count,
engaged-listing count/share, family availability, and separate family
confidence. It emits no generic high/medium/low demand level and no blended
confidence. Unknown, unsupported semantics, extraction failure, provider
unavailability, not-applicable facts, and absence of a target listing remain
distinct from observed zero.

An exact Competition v2 cohort may be referenced only by immutable source IDs,
versions, artifact/integrity hash, and matching subject/scope. Demand attaches
its own review/rating facts to the pinned cards and never copies Competition
assessment, price, Rocket, or count values as Demand. Manual and future
automated evidence share one provider envelope and immutable reference/hash
pattern; no current provider integration is implied.

Implementation requires separate Demand v2 schemas, additive persistence,
receipt/replay namespace, and a dedicated API v2 route. Demand v1 and ADR-0044
DMV v1 remain unchanged. Decision Composition v2 and DMV v2 do not exist. The
genuine run remains Competition v2 verified, Demand not admitted, and DMV
blocked.

## Competition v2 evidence authority direction

ADR-0061 preserves historical Competition v1 and separates future Competition
v2 into a mandatory marketplace-independent core plus optional
marketplace-specific signals. The v2 core is derived from one immutable bounded
cohort of unique comparable organic listing cards and requires
`comparable_listing_count`, `price_spread`, and `median_price`. Sponsored cards
are recorded separately, and all price facts use the exact same core cohort.

Coupang Rocket evidence is an optional `coupang-rocket-signal-v1` envelope over
that cohort. Explicit `판매자로켓`, `로켓배송`, `로켓그로스`, and other Rocket
labels remain separate taxonomy states; arrival-speed text, icons, and colors
do not imply a state. Per-card unknown, unsupported, and extraction-failure
outcomes never become false or zero. No seller identity or deduplication is
inferred.

Competition v2 uses separate core and marketplace-signal availability,
confidence, and coverage. It requires a new observation/assessment/policy
version and dedicated API v2 contract. Competition v1 rows, snapshots,
receipts, fingerprints, analyzers, and ADR-0044 DMV-v1 requirements remain
unchanged. CR-1B7D4E implements this foundation through dedicated v2 Domain and
Application owners, additive immutable SQLite cohort/receipt tables, and the
API v2/OpenAPI contract. Automated Coupang collection, Decision Composition v2,
DMV v2, and UI support remain absent, and the genuine run remains stopped.

## Pre-admission discovery identity

One finalized ProductGroup is a discovery candidate, not an admitted
Opportunity. The Discovery Orchestration boundary issues an explicit
`OpportunityCandidateIdentity` and propagates an immutable
`DiscoveryOpportunityContext` through candidate-owned processing. Validation
Admission later promotes the candidate by explicitly binding it to an
`OpportunityIdentity` and its exact Snapshot chain. Candidate issuance does not
create an Opportunity lifecycle. Market identity must be supplied explicitly and
must never be inferred from Product text, item ID, query, or category.

A discovery execution is correlated by an immutable command, collector-owned
observation envelopes, opaque finalized-group references, ordered group
membership fingerprints, and one ordered command result. Opaque IDs are separate
from content fingerprints. A committed replay must eventually load these facts
instead of calling a live marketplace again; this PR defines only the contracts,
not persistence or production wiring.

The Discovery Application layer defines separate command, finalized-group, and
execution-result repository boundaries. SQLite implements only the command
boundary: one immutable command and its receipt commit atomically with
`BEGIN IMMEDIATE`, and durable replay returns that exact pair after restart.
Command persistence does not execute discovery or issue Candidate identity.
Collected observations and finalized groups are also stored as immutable,
execution-bound SQLite facts. Observation identity is independent from source
listing identity, so a listing may be observed repeatedly. Group membership is
an ordered normalized relation and one observation may participate in multiple
groups. An immutable Discovery execution result now records successful
completion, including ordered finalized Group IDs or an explicit successful
zero-result. Result persistence is command/execution-bound and does not generate
completion time, execute discovery, or issue Candidates.

Candidate issuance is a read-only Application boundary over the persisted
command, completed result, finalized Group, and representative observation. The
caller supplies an explicit discovery reference and listing or canonical-product
Market identity; neither value is derived from Group ID, Product text, query, or
fingerprint. After lineage and source identity validation, an injected opaque ID
generator creates `OpportunityCandidateIdentity` and the boundary returns an
immutable `DiscoveryOpportunityContext`. This does not create an Opportunity,
write a Candidate, or claim durable replay. Until an issuance receipt exists,
repeating the request may generate another Candidate identity.

Candidate issuance persistence closes that replay gap. One Candidate and Context
exist per `(Discovery command ID, finalized Group ID)`, while every immutable
issuance command owns one receipt; multiple alias receipts may reference the same
Candidate. Initial issuance atomically stores Candidate, Context, and receipt.
An equivalent later command stores only an alias receipt and returns the existing
Candidate without regenerating its ID or issuance time. This durable state is
still pre-admission and creates no Opportunity lifecycle.

ADR-0057 is implemented for the production Candidate handoff. The `EBAY_US`
marketplace adapter owns the exact Candidate Market
identity at collection time, while the Discovery Application issues a dedicated
opaque Candidate discovery reference before immutable observation admission.
Both facts and their handoff policy version are persisted with the observation.
The exact Finalized Group representative exposes them verbatim in the nullable
`candidate_handoff` response, and the explicit Candidate request must match both
by complete equality. Historical or
unsupported observations remain valid Discovery history but are not
Candidate-eligible; there is no backfill or read-time inference. A clean
file-backed database can now complete Discovery, Group read, Candidate,
Product Snapshot, Promotion, and O1 through production HTTP boundaries only.

HYB는 Modular Pipeline Architecture를 사용한다.

흐름:
Application
↓
Marketplace Collectors
↓
Normalized Product
↓
Engine Orchestrator
↓
Analysis Engine
↓
Storage / Presentation

원칙:
Marketplace는 수집,
Engine은 분석,
Service는 연결,
UI는 표현만 담당한다.
# Candidate Admission Promotion (PR34-E)

Persisted Candidate ID is promoted through an Application boundary that reloads
Candidate, Context, and issuance provenance. The existing Validation Admission
fact builders are reused, and a SQLite promotion repository commits lifecycle,
admission snapshot, market binding, immutable Candidate/Opportunity binding, and
receipt atomically. Candidate and Opportunity remain distinct identities.
Snapshot-chain ownership and Production Safety are not part of this flow.

That paragraph describes implemented historical Candidate Promotion v1.
ADR-0059 accepts a bounded v2 evolution because v1 requires caller-supplied
recommendation, score, ROI, currency, and safety values without an authoritative
pre-promotion source. V2 defines O1 only as a Founder-selected `discovered`
Opportunity for deeper validation. It requires exact persisted Candidate,
Context, finalized Group, complete Product Snapshot capture, representative
Snapshot, operator, reason, and requested time; it admits no economic or safety
conclusion. A separate additive v2 admission record and Product-source companion
preserve the existing common Candidate/Opportunity cardinality anchor while v1
history remains unchanged. CR-1B7C3 implements this production boundary and its
versioned Validation Queue read union; no legacy v1 admission row is fabricated.

## Candidate-scoped Snapshot chain (PR35-A)

Marketplace Collection owns Candidate-scoped Product Observation snapshots;
Price Intelligence owns Candidate-scoped Price snapshots referencing an ordered
Product cohort. Verified Economics and EconomicsCalculation remain post-admission
Opportunity facts. Production Safety context joins these stages only through the
immutable Candidate/Opportunity promotion binding and exact Market identity.
Snapshot persistence and owner wiring are not part of this foundation.

PR35-B persists the Product Observation stage only. SQLite revalidates persisted
Candidate and Context lineage atomically before appending the complete Snapshot.
The repository does not invoke Collection and does not require promotion. Price,
Economics, handoff, and Safety persistence remain unavailable.

PR35-C adds the Price Analyzer's immutable Candidate-scoped Snapshot. It retains
the ordered persisted Product cohort and validates every Candidate and Market
lineage edge without rerunning grouping or price analysis. Economics, handoff,
and Safety remain outside this persistence boundary.

PR35-D persists the post-admission EconomicsCalculation Snapshot. The immutable
promotion binding bridges Candidate provenance to its Opportunity, and Verified
Economics is the exact calculator source. Price-to-Economics Snapshot lineage is
not inferred because the calculator contract does not retain a Price Snapshot ID.

PR35-E1 adds the collector-owned post-issuance Product Snapshot capture boundary.
It reads one exact finalized group's ordered observations and atomically persists
Candidate-scoped Snapshots, source bindings, and replay receipt. It performs no
latest-source selection or Product-field identity inference.

PR35-E2 adds the Price Analyzer owner boundary. It validates one explicit ordered
Product Snapshot/source-binding cohort against finalized group membership,
reconstructs runtime Products losslessly, invokes the existing Analyzer, and
atomically persists the Price Snapshot and replay receipt. Production Discovery
orchestrator wiring remains deferred.

PR35-E3 adds the Economics calculator owner boundary. An immutable source context
bridges the exact Candidate Price Snapshot through the promotion binding to the
Opportunity and Verified Economics source. The existing calculator consumes only
persisted VerifiedEconomicsInput; Price remains provenance. Economics Snapshot v3
and its replay receipt are committed atomically.

PR35-E4 adds the post-owner complete Snapshot Chain binding. One immutable,
versioned fact binds the exact promotion, ordered Product cohort, Price,
Economics, Verified Economics, and Market identity. Exact duplicate chains share
one binding through alias receipts; changed complete sources append a new version.
There is no current/latest projection. Safety source reconstruction requires an
explicit binding ID and Product member ID and performs no source calculation.

PR36-A executes the unchanged Production Safety engine over that exact selection.
Operational evaluation history and provenance are authoritative; a controlled
current projection supplies Decision Readiness. The one-shot admission Safety
snapshot remains a separate legacy outcome and is never overwritten or backfilled.

PR36-B makes operational Safety current the production Decision source. Finalize
captures the exact evaluation ID and transactionally rejects a stale current;
Dashboard subsequently reads that immutable evaluation. Readiness, Finalize, and
Dashboard therefore share one authoritative source without a legacy fallback.

PR36-C exposes operational Safety through a thin DTO/API boundary and explicit
Opportunity Detail controls. Application services retain all source validation,
runtime reconstruction, engine execution, persistence, and replay responsibility.

## Founder-assisted Sourcing authority (CR-0B)

The Sourcing Application boundary owns manual admission of one opaque Supplier,
one exact Supplier product/option, immutable commercial quote revisions, explicit
MOQ/quantity/shipping/lead-time availability, external evidence references, and
Human-verified selling-to-sourcing Product lineage. Existing marketplace grouping
and similarity are proposal-only and cannot create match authority. Commands use
deterministic fingerprints and replay receipts through a repository Protocol;
SQLite, Economics integration, Capital Readiness, Capital Gate, API, and UI remain
outside this foundation.

CR-0C implements that Protocol with append-only SQLite Supplier, Sourcing Product,
Match Verification, Quote Revision, Admission Revision, and Receipt history. Fresh
admission and quote revision each use one `BEGIN IMMEDIATE` transaction. Reads
reconstruct the exact Domain graph and validate source rows, versions, fingerprints,
revision continuity, and the persisted Economics source reference. There is no
current projection, identity inference, Supplier deduplication, or downstream
production composition.

CR-0B1 separates Sourcing timestamp authority. `requested_at` remains the
caller command time and `verified_at` the operator's factual match-verification
time. An injected Application clock supplies authoritative `admitted_at`, while
the receipt clock supplies `committed_at`. Admission v2 persists requested and
admitted times separately. Replay lookup precedes identities and both clocks,
and the command fingerprint contains no generated identity or server time.

CR-1B1 exposes this authority through two thin production command routes. A
request-scoped composition owns one `SQLiteSourcingAuthorityRepository`, five
Sourcing-specific opaque identity suppliers, and separate UTC admission and
receipt clocks. FastAPI performs strict DTO conversion and bounded HTTP error
mapping only; the existing Application services retain replay, identity,
verification, revision, and persistence behavior. Responses originate from the
committed/reconstructed result. No supplier lookup, matching calculation,
Economics, Capital policy, Snapshot Chain mutation, OCR promotion, or UI is
part of this composition.

CR-1B5D2C adds a second explicit selling-lineage variant without changing the
legacy Candidate-Promotion payload. `DomesticSellingProductLineage` pins one
persisted O1-to-O2 admission, its exact O1/O2 identities, source Product
Snapshot, KR Market identity and equivalence evidence. The existing Sourcing
owner validates that source before identity issuance and still creates a normal
independent Supplier Product Match and Quote under O2. SQLite preserves legacy
v2 payload bytes while domestic admissions use a discriminated v3 payload;
existing Sourcing Economics Binding consumes either through the same exact
Founder Sourcing Admission reference.

CR-1B5D2D exposes the accepted O1-to-O2 authority through a request-scoped
FastAPI composition. One `SQLiteDomesticSellingOpportunityAdmissionRepository`
owns the O1 source reads and atomic O2 lifecycle, KR Market binding, admission,
and receipt transaction; independent UUIDv4 suppliers and UTC clocks remain
server-owned. The existing Sourcing route accepts an explicit admission-ID-only
domestic variant, and the Sourcing Application reconstructs the exact persisted
lineage before identity issuance while preserving the legacy Candidate request
and the independent `VERIFIED_MATCH` requirement. The two HTTP calls are
separate committed authorities; there is no cross-request transaction or
automatic Economics, Market Validation, Capital, execution, UI, or auth flow.

ADR-0060 accepts a separate additive path for an exact O1 source product that
the Founder selects as a new-to-market KR selling target before an exact KR
listing or canonical-product identity exists. The Application will own a
server-issued opaque `NewToMarketDomesticSellingTargetIdentity`, a distinct O2,
and an immutable `OpportunityDomesticSellingTargetBinding`. The existing
ADR-0049 listing/canonical admission and every historical Market binding remain
unchanged. Comparable Coupang products stay evidence rather than target
identity, and a later real listing will attach through a new append-only fact
without mutating the original binding or creating another O2 automatically.
CR-1B7D3 implements this authority and its production route. The genuine run has
created the separate O2 and opaque target without creating a KR listing or
canonical-product identity.

CR-1B5D2F keeps Validation Queue membership distinct from authoritative
Opportunity existence at operational ingress. Competition, Demand, and Verified
Economics now share a narrow read contract that requires one exact non-archived
Opportunity lifecycle and then preserves each owner's immutable Market-binding
validation. This admits both legacy queue-backed Opportunities and Domestic
Selling O2 without fabricating queue snapshots or changing queue, assessment,
evidence, or Economics semantics.

CR-1B5D2G exposes the existing ADR-0044 owner through one request-scoped FastAPI
entry. A single `SQLiteDomesticMarketValidationRepository` connection reads the
exact Opportunity lifecycle, immutable KR Market binding, and caller-selected
Competition/Demand observation-assessment pairs, while the Application remains
the sole owner of evidence policy and `VALIDATED_FOR_CAPITAL`/`BLOCKED` state.
Founder/operator review facts are explicit factual inputs at a private unauthenticated
MVP boundary; assessment identity and evaluation/commit times remain server-owned.
The entry performs no latest selection, Verified Economics interpretation, Validation
Queue admission, or Capital creation.

CR-1B5D2H makes the existing exact-source acquisition/Economics authorities
production-callable without adding an orchestration transaction. Independent
Opportunity-scoped entries derive the full identity from the named Sourcing Admission,
Binding, Landed Cost or Normalization source and reject O1/O2 mixing. Shipping
allocation remains an explicit Founder/operator authority, FX remains an explicit
observed fact, and normalization/source composition remain mechanical Application
owners using exact ordered IDs. Each request owns one SQLite connection and one
append-only transaction; earlier authorities remain historical facts if a later step
fails. The existing Conservative Economics API consumes the new composition unchanged.
Critical Cost remains separate and is required later by Capital Readiness, not by
Acquisition Normalization or Economics Source Composition.

CR-1B2B adds an Application-owned, exact Sourcing-to-Economics source-selection
fact. An immutable binding links one `OpportunityIdentity` to one explicit
Admission/Quote revision and is persisted with its replay receipt in a single
`BEGIN IMMEDIATE` transaction. Reads reconstruct the exact historical source;
there is no latest selection or current projection. The narrow binding reference
prepares a future Economics handoff without injecting costs, changing formulas,
or asserting Capital Readiness.

CR-1B3A defines the acquisition-side `LandedCostComposition` Domain/Application
contract over one exact Sourcing Economics Binding. Unit purchase and the three
shipping scopes remain separate, preserve availability and source currency, and
carry MOQ/quoted quantity as provenance only. Shipping allocation remains
explicitly unspecified because the authoritative quote does not own that fact;
there is no aggregation, FX, profitability, or Capital policy. A repository port
defines replay semantics, while SQLite remains deferred until this allocation
contract is stable.

CR-1B3A1 implements that repository port with append-only SQLite composition and
receipt history. One `BEGIN IMMEDIATE` transaction preserves the exact binding,
Opportunity lineage, canonical component order, availability, source currency,
allocation basis, quantities, evidence, timestamps, and versions without
calculation. Durable replay reconstructs the committed composition after restart;
changed command payloads conflict, malformed persistence fails explicitly, and
UPDATE/DELETE triggers protect both histories. No current projection, latest
binding selection, FX, allocation, Economics, Capital policy, API, or UI is added.

CR-1B3B adds a separate immutable Critical Cost Completeness assessment over one
exact persisted Landed Cost Composition, its exact Sourcing Binding/Admission,
and the persisted Verified Economics Snapshot for the same Opportunity. The
versioned Domestic Commerce policy evaluates availability, evidence trust,
shipping allocation authority, currency compatibility, and quote validity with
deterministic structured reasons. UNKNOWN never becomes numeric zero in the
Capital-facing assessment. Existing Discovery/operational calculator fallback
remains a compatibility path and is not Capital authority. This assessment
means source completeness only: it does not calculate Conservative Economics,
assert Capital Readiness, open a Capital Gate, or grant Founder approval.
CR-1B3B intentionally deferred assessment persistence until this source and
policy contract was stable.

CR-1B3B1 publishes that stable assessment through a replay-first Application
owner and a dedicated SQLite repository. A server-owned opaque assessment ID is
receipt/history identity, while the immutable Domain assessment remains
unchanged. Two new append-only tables atomically preserve the command receipt,
exact composition and Verified Economics references, policy identity/version,
evaluation/commit times, state, and ordered reasons. Restart reads validate the
still-exact source lineage but never re-evaluate policy, substitute latest facts,
or create Economics results.

CR-1B5D2I1 adds an additive Critical Cost v2 contract over one exact persisted
Acquisition Cost Normalization. It validates the normalization's exact Landed
Cost, resolved Shipping Allocation Authorities, FX Observations, target currency,
and component provenance without repeating allocation, conversion, or total
arithmetic. Historical v1 payloads remain reconstructable unchanged. A v2 result
preserves the normalization and ordered allocation/FX identities, allowing the
supported O2 CNY-to-KRW chain to become `COMPLETE` when all pre-existing evidence
and Quote-validity rules pass.

CR-1B3C1 reconciles production shipping allocation without mutating Landed Cost
history. One explicit Application command separates effective basis authority
from denominator authority for an exact persisted composition/component.
Operator-admitted `PER_ORDER` preserves its positive denominator and factual
evidence; explicit `PER_QUOTED_QUANTITY` may use only the exact known quoted
quantity. MOQ is never substituted. A dedicated opaque identity, immutable
authority/receipt history, `BEGIN IMMEDIATE` transaction, restart replay, and
source-integrity validation make the result an exact future normalization
source. No division, FX, Critical Cost mutation, Economics, or Capital judgment
is performed.

CR-1B3E adds a dedicated authoritative acquisition-cost normalization boundary.
It consumes one exact persisted Landed Cost Composition, an ordered exact set of
resolved Shipping Allocation Authority facts, explicit exact FX Observations,
and caller-owned target currency. Policy v1 uses Decimal-only 34-significant-
digit `ROUND_HALF_EVEN` arithmetic, preserves original and effective allocation,
denominator and FX provenance per component, and emits a total only after every
applicable component is safely expressed per unit in the target currency.
UNKNOWN blocks; NOT_APPLICABLE and known zero remain distinct. Dedicated
append-only SQLite history/receipts provide atomic replay and restart
reconstruction without latest-source selection or recalculation. This boundary
does not create sale-side Economics, profit/ROI, Capital Readiness, or approval.

Landed Cost Composition
Shipping Allocation Authority
Authoritative FX Observation
Authoritative Acquisition Cost Normalization

CR-1B4A adds an immutable Economics Source Composition over one exact persisted
Acquisition Cost Normalization and one exact immutable Verified Economics
Snapshot. The manifest excludes legacy purchase and shipping fields, preventing
their double-counting with the normalized acquisition total. It preserves
expected sale price, marketplace/payment rates, fixed fee, tax rate, duty, and
other cost with original evidence status/reference. Source readiness is
deterministic: missing or weak required evidence, currency mismatch, and current
non-zero unscoped `other_cost` block without becoming zero or invoking FX.
Dedicated append-only SQLite history and receipts provide atomic replay and
restart reconstruction without source migration, latest lookup, profit/ROI,
Conservative assumptions, or Capital judgment.

CR-1B4B0 establishes the semantic boundary for future Conservative Economics.
Current generic non-zero duty and tax facts are not automatically Capital-
authoritative: only explicit verified zero with evidence may contribute zero;
all other current cases block until exact scoped authority exists. A new
`conservative_acquisition_roi` metric will divide conservative unit profit by
the exact normalized acquisition cost per unit when that denominator is
positive. It does not redefine legacy purchase-price ROI, legacy landed-cost
ROI, or Actual ROI, and it carries no Capital Readiness or investment meaning.

CR-1B4B implements that boundary as a dedicated Conservative Economics owner.
One exact Economics Source Composition and one explicit sale-price-factor
scenario produce immutable unit economics under a 34-significant-digit
`ROUND_HALF_EVEN` Decimal policy. The only calculable v1 path has a positive
normalized acquisition cost and verified-zero tax, duty, and other cost;
unsupported semantics produce ordered BLOCKED reasons with no profit, margin,
or ROI values. Dedicated append-only SQLite result/receipt histories preserve
exact source, scenario, policy, calculation, replay, and restart reconstruction.
The legacy calculator and existing ROI/Actual contracts remain unchanged.

CR-1B4B1 exposes that owner through an Opportunity-scoped production entry and
FastAPI route. Request scope opens one dedicated Conservative Economics SQLite
repository against the production database, supplies the existing UUIDv4 result
identity and separate UTC calculation/commit clocks, and always closes owned
resources. The entry resolves only the named exact Economics Source Composition
and injects the current authoritative policy; FastAPI maps transport errors and
serializes the committed/reconstructed result without performing calculations.
Fresh execution is HTTP 201, exact replay is HTTP 200, and a committed BLOCKED
result remains a successful authoritative response. No Capital decision meaning
or legacy calculator path is introduced.

CR-1B5A0A implements the ADR-0044 Domestic Market Validation authority. A
dedicated Application owner reconstructs only named persisted Competition and
Demand observations and assessment snapshots, verifies their exact
Opportunity/KR Market lineage, required metric provenance, supported evidence
status and factual timing, then combines them with an explicit operator
current-use verification event. It issues only `VALIDATED_FOR_CAPITAL` or
`BLOCKED` with ordered reasons; it does not calculate profitability or imply
Capital readiness. Dedicated append-only SQLite assessment and receipt tables
provide replay-first identity/time issuance, atomic commit, restart
reconstruction, source-lineage integrity checks, rollback and concurrent-command
convergence without latest-source selection or policy re-evaluation. Production
API exposure is added by CR-1B5D2G without changing that policy. UI, operator
authentication and Capital Readiness consumption remain separate future boundaries.

CR-1B7D3 implements ADR-0060 as a separate additive new-to-market admission
authority. It reconstructs the exact ADR-0059 v2 O1, capture, ordered Product
Snapshot cohort, representative Snapshot, selected Snapshot/source observation,
and eBay/US Market lineage; records a bounded KR search whose only admissible
conclusion is `exact_kr_identity_not_established`; then atomically issues a
server-owned opaque KR selling target and distinct `DISCOVERED` version 1 O2
with an immutable target binding. Append-only SQLite admission, target, binding,
and receipt history provides replay/alias, restart, rollback, corruption, and
concurrency safety. Reciprocal checks with ADR-0049 enforce one O1 to one O2
across both modes. No `OpportunityMarketIdentityBinding` is synthesized for the
new target. CR-1B7D4 adds an explicit operational subject union over exactly one
historical Market binding or ADR-0060 target binding, plus versioned
Competition/Demand observations and snapshots for the target subject. Actual KR
marketplace/query/category/listing provenance remains on each evidence item and
never becomes the target identity. Historical Market-observation rows and
analyzer policy remain unchanged. Domestic Market Validation, Sourcing,
Economics, Safety, Capital, UI, and later-listing support remain blocked.

CR-1B7D4C makes canonical-reference migration detection-driven so an already
initialized current-schema SQLite database is byte-stable across repository
construction and production GET/read composition. Fresh bootstrap and actual
legacy canonicalization still create or repair the required partial unique
index, but ordinary reads do not drop/recreate it or rewrite canonical rows.
Schema bootstrap and migration remain persistence concerns; read operations do
not masquerade as migrations.

CR-1B5D2B implements the ADR-0049 Domain/Application foundation that preserves
one foreign/source Opportunity O1 and admits a distinct KR domestic-selling
Opportunity O2. The replay-first owner reconstructs O1's exact lifecycle,
Candidate Promotion, Product Observation Snapshot and immutable Market binding,
requires explicit Founder/operator product-equivalence confirmation and evidence
reference, then issues server-owned O2/admission identities and constructs O2 as
`DISCOVERED` version 1 with one exact KR listing/canonical-product Market
binding. The admission never mutates O1, infers equivalence from title or
similarity, copies Economics, or creates Capital state. SQLite atomic
persistence now reuses the existing lifecycle and Market-binding tables on one
shared connection while dedicated append-only admission/receipt tables preserve
exact replay, restart reconstruction, rollback and durable one-O1-to-one-O2
cardinality. CR-1B5D2C and CR-1B5D2D subsequently add the exact O2 Sourcing
lineage handoff and thin production API wiring without changing this authority.

CR-1B5A implements ADR-0045 as a separate Capital evidence-admission boundary.
One Application command selects exact Conservative Economics, Domestic Market
Validation, and Critical Cost results; the owner reconstructs their complete
Economics Normalization and Sourcing lineage, requires `VERIFIED_MATCH`, and
checks the exact Quote revision at the fresh server evaluation time. Only
`READY_FOR_CAPITAL_REVIEW` or `BLOCKED` is issued. Negative but `CALCULABLE`
economics remains eligible because profit, margin, ROI, required capital, and
investment thresholds belong to a later Capital Gate. A dedicated UUIDv4-style
identity and two append-only SQLite histories preserve the exact source manifest,
policy, ordered reasons, evaluation/commit times, replay, and restart
reconstruction. Historical replay never rechecks Quote expiry or selects latest
sources. Existing Decision Readiness, Production Safety, Founder approval, and
API/UI contracts remain isolated and unchanged.
CR-1B5D2I1 makes fresh Capital Readiness assessments schema v2 and requires the
Critical Cost normalization identity to equal the one reconstructed through
Conservative Economics and Economics Source Composition. The readiness policy
and Gate-facing meaning remain unchanged; historical schema-v1 replay does not
gain new provenance retroactively.

CR-1B5D2J exposes the reconciled Critical Cost v2 and Capital Readiness v2
owners through two thin Opportunity-scoped FastAPI entries. Critical Cost names
one exact O2 Landed Cost, Acquisition Normalization, and Verified Economics
tuple and reconstructs allocation/FX provenance on one request-owned SQLite
connection. Capital Readiness names exact Conservative Economics, Domestic
Market Validation, and Critical Cost terminal IDs, verifies their common O2,
then retains the existing exact normalization-equality, Quote-validity, policy,
and ordered-blocker semantics. Both boundaries are replay-first and commit
independently; no transaction spans the routes, no latest source is selected,
and no Capital Gate, quantity, capital, approval, or execution authority is
introduced.

CR-1B5B0A implements the first two ADR-0046 Founder-owned Capital facts without
opening Capital Gate. `IntendedOrderQuantity` binds one explicit positive unit
quantity to the exact Opportunity and Sourcing Admission/Quote revision; it
never derives purchase intent from MOQ, quoted quantity, or shipping allocation.
`DeployableCapitalSnapshot` preserves an explicit non-negative Decimal amount,
currency, factual `as_of`, operator, and the fixed reserve-adjusted semantics
version without bank lookup or reserve arithmetic. Separate replay-first
Application owners issue opaque IDs and server admission/receipt times. Four
dedicated append-only SQLite history/receipt tables provide atomic commit,
restart reconstruction, concurrency convergence, source-integrity checks, and
malformed-state rejection without current/latest projections. Upfront-cost scope,
Planned Acquisition Capital Requirement, sufficiency, Gate policy, approval,
API, and UI remain separate.

CR-1B5B0B implements the narrow ADR-0046 Planned Acquisition Capital
Requirement without opening Capital Gate. One exact Intended Order Quantity is
joined to one exact Acquisition Cost Normalization through the persisted Landed
Cost Composition and Sourcing Binding/Admission/Quote chain. A Founder/operator
scope verification explicitly records whether all mandatory upfront acquisition
cash outside the normalized four-component scope is resolved; unresolved scope
produces a durable `BLOCKED` result with no authoritative amount. Complete scope
uses only Decimal 34-significant-digit `ROUND_HALF_EVEN` multiplication of exact
normalized per-unit acquisition cost by exact intended quantity. Dedicated
append-only SQLite history/receipt tables preserve sources, verification,
policy, result, replay, restart, and transaction integrity. Deployable Capital,
profitability, sufficiency, Gate, approval, API, and UI remain separate.

CR-1B5B implements ADR-0046 Capital Gate as a distinct policy boundary over one
exact persisted Capital Readiness assessment, Planned Acquisition Capital
Requirement, and Founder-declared Deployable Capital snapshot. The Gate fixes
the exact Conservative Economics and Sourcing lineage through those sources,
then emits only `PASS`, `REJECTED`, or `BLOCKED`. Incomplete, inconsistent,
unsupported, or cross-currency facts block; complete facts are rejected only
for non-positive conservative profit/margin/acquisition ROI, insufficient
deployable capital, or intended quantity below a known MOQ. No reserve is
subtracted, no threshold beyond strict positivity is invented, and unknown MOQ
is never substituted. Dedicated append-only SQLite history and receipts preserve
policy, evaluated facts, exact sources, replay, restart, and transaction safety.
`PASS` authorizes only a future Founder Capital Approval review; it cannot spend
capital and creates no position, concentration, API, or UI semantics.

CR-1B5C implements ADR-0047 as a separate final human authorization fact before
future real-money execution. One explicit Founder command names one exact
persisted Capital Gate `PASS`, its factual Founder identity and decision time,
and an approved capital cap. Because the Gate's Requirement represents one exact
Intended Order Quantity and no staged-release authority exists, v1 requires the
approved amount to equal that full Requirement and its exact currency. The owner
copies the Gate's Opportunity, policy, Requirement, Deployable Capital, Intended
Quantity, and evaluation time without selecting latest sources or reevaluating
Gate policy. Dedicated append-only SQLite history and receipts preserve atomic
replay and restart reconstruction. Approval does not modify generic
`FounderDecision`, execute a purchase, transfer funds, expire automatically, or
create mutable revocation state.

CR-1B5D1 implements ADR-0048 immediately before the first external manual
purchase. One exact command reconstructs the named Founder Capital Approval and
its Gate, Requirement, Intended Quantity, Sourcing Admission/Quote revision,
then binds a separately named post-Approval reserve-adjusted Deployable Capital
snapshot and explicit current Founder confirmation. Policy v1 requires exact
amount, quantity, unit and currency, checks the exact Quote `valid_until` at the
server evaluation time, and emits only `READY_FOR_MANUAL_EXECUTION` or `BLOCKED`
with ordered reasons. Dedicated append-only SQLite history and receipts preserve
historical replay without current-time reevaluation; a partial unique index and
transactional alias/conflict handling enforce at most one distinct READY action
per Approval. The intent remains a pre-execution authorization fact: it does not
place an order, transmit payment, create a Purchase Execution Record, or mutate
Actual Economics, inventory, Approval, Gate, or upstream evidence.

CR-1B5D2L wires those existing Capital authorities into the production
composition root without changing Domain policy. Six explicit POST boundaries
admit Intended Order Quantity, Founder-declared Deployable Capital, Planned
Requirement, Gate, Founder Approval, and Execution Intent independently. Each
request owns one top-level SQLite repository/connection, injects an existing
production identity supplier plus the reusable timezone-aware UTC clock, commits
only its own authority, and closes the connection on every result or failure.
Opportunity-scoped adapters derive the complete immutable identity from the
named persisted source and reject O1/O2 mixing before invoking the owner.

The production sequence intentionally has two Deployable Capital snapshots:
snapshot A is evaluated by Gate, while a distinct Founder-owned post-Approval
snapshot B is evaluated by Execution safety. No endpoint selects latest state or
automatically advances a human-sensitive boundary. The API-only O2 path can now
end at `READY_FOR_MANUAL_EXECUTION`, whose exact manifest is the durable manual
purchase handoff. External ordering/payment remains outside HYB and no
PurchaseExecutionRecord, Actual Economics, inventory mutation, authentication,
or autonomous commerce behavior is introduced.

CR-1B5D2M implements ADR-0050 immediately after that manual boundary. The
Founder names one exact persisted READY intent and reports the actual external
quantity/unit, total committed amount/currency, exact Quote revision, opaque
supplier order reference, identity, execution time, and evidence references.
The owner reconstructs O2, Approval, Gate, Requirement, Intended Quantity,
Sourcing Admission, Supplier/Product, Quote, and execution-time Capital lineage
and admits a record only when every v1 action fact exactly matches READY.

`PurchaseExecutionRecord` is an append-only historical fact with no mutable
order status. One READY intent maps to at most one record through a DB unique
index; exact command replay and equivalent-event aliases converge without new
record identity or admission time. Reads do not recheck current Quote, Capital,
Gate, or safety. This records Founder-submitted evidence after an external
action; it does not perform checkout/payment, prove supplier fulfillment,
mutate Actual Economics, or create inventory. Actual shipping, duty/customs,
FX settlement, realized marketplace facts, and physical goods receipt remain
separate future authorities.

ADR-0058 and CR-1B7B2A separate the production monetary authorities.
Founder Approval remains the full target-currency acquisition-capital cap;
Execution Intent v2 preserves that cap plus a distinct Founder-confirmed
source-currency proposed supplier-order commitment; Purchase Execution v2
records the matching genuine supplier-order commitment. No planned FX is used
at execution, and final actual FX/acquisition scope remains owned by Actual
Acquisition Settlement. Existing v1 intent and purchase rows retain exact
historical replay. Explicit `2.0.0` production requests support a CNY supplier
commitment under a KRW authorized-capital envelope without execution-time FX
or planned-value aliasing.

CR-1B6A2 implements ADR-0051 as `ActualAcquisitionSettlement` immediately after
an exact `PurchaseExecutionRecord`. The production owner preserves actual batch
totals for unit purchase, supplier-side
shipping, international freight, domestic inbound, duty/customs, and scoped
other mandatory acquisition costs, plus exact actual FX settlement provenance.
Append-only predecessor-bound revisions may record `BLOCKED` incompleteness,
while only a category-complete, evidence-backed `COMPLETE` revision is terminal
and usable downstream. Planned values, planned FX, and the execution committed
amount are never actual-settlement fallbacks.

Each request owns one SQLite connection, uses a dedicated UUID identity and
server UTC admission/receipt clocks, and persists history plus receipt in one
`BEGIN IMMEDIATE` transaction. Unique revision/predecessor/COMPLETE indexes and
a terminal trigger prevent first-revision races, forks, multiple COMPLETE
settlements, and post-COMPLETE children. Historical reads reconstruct the exact
Purchase Execution lineage and stored Decimal calculation without external FX,
current safety reevaluation, or a mutable current projection.

CR-1B6B2 implements ADR-0052's physical-arrival authority. One exact Purchase
Execution may produce multiple immutable
`GoodsReceiptRecord` events for partial shipments. Each event records positive
received quantity in the executed unit and fully inspected sellable versus
damaged quantities. Transactional cumulative receipt must never exceed the
executed quantity. Actual Acquisition Settlement is not a prerequisite because
physical receipt and financial settlement are independent facts that may occur
in either order.

The production owner is replay-first, reconstructs the exact O2,
Supplier/Product/Quote and executed quantity/unit from the named Purchase
Execution Record, and issues dedicated opaque receipt identity and server UTC
times. Dedicated append-only SQLite history and command-receipt tables commit in
one `BEGIN IMMEDIATE` transaction. The write transaction revalidates the exact
Purchase Execution and sums immutable receipt events through an indexed lookup
before insert, so concurrent partial arrivals cannot jointly exceed executed
quantity. The request-owned connection is closed on every result or failure.

The existing `market_data.InventorySnapshot` remains an external marketplace
listing-availability observation. It is not HYB-owned, sellable, or
reserved/allocated inventory and is never mutated by Goods Receipt.

CR-1B6B4 implements ADR-0053 as an on-demand, rebuildable Application read
model rather than an independently admitted balance.
Its v1 exact key combines the O2 `OpportunityIdentity`, source platform,
Supplier ID, sourcing product ID, external product/option/SKU references, and
quantity unit copied from committed Goods Receipt manifests. Multiple Purchase
Executions aggregate only when that complete key is identical, and every
contributing Purchase Execution and Goods Receipt ID remains traceable.

Before an authoritative outbound event exists, v1 sellable on-hand is exactly
the sum of committed `GoodsReceiptRecord.sellable_quantity` for one key. Total
received and damaged received remain separate cumulative facts. No speculative
sale, reservation, settlement, marketplace availability, or manual balance is
subtracted. There is no v1 owned-inventory SQLite table; a future materialized
cache must be disposable and fully rebuildable from immutable events.

CR-1B6C3 preserves that v1 behavior as an explicit historical Domain owner and
adds current production v2 policy
`receipt-and-complete-sale-derived-owned-inventory / 2.0.0` with schema
`owned-inventory-position-v2`. The unchanged GET uses one request-owned
connection to enumerate committed receipts plus COMPLETE sale settlements,
sorts inbound by UTC receipt time/ID and outbound by UTC period-end/settlement
ID, and subtracts only exact-key COMPLETE fulfilled outbound. BLOCKED revisions
are absent. Zero-sale COMPLETE events remain traceable with zero quantity.
Missing O2 returns 404, an existing O2 without receipts returns an empty
collection, source conflict returns 409, and bounded read failure returns 503.
Repeated reads and restart reconstruction perform no writes and produce the
same positions.

The decision-level closed-loop sequence is:

```text
PurchaseExecutionRecord (implemented)
|-- ActualAcquisitionSettlement (implemented; independent money fact)
`-- GoodsReceiptRecord(s) (implemented physical facts)
    `-- OwnedInventoryPosition v1 (implemented historical receipt-only read)

ActualSaleSettlement (implemented authoritative outbound source)
    `-- OwnedInventoryPosition v2 (implemented current production read)

ActualAcquisitionSettlement
+ GoodsReceiptRecord
+ ActualSaleSettlement (implemented sale-side fact)
`-- ActualOutcome (implemented immutable exact-source result)
    `-- Variance v2 + exact ConservativeEconomics binding
        (implemented immutable exact-pair result)
        `-- Calibration / policy learning (future)
```

Purchase Execution, Actual Acquisition Settlement, and Goods Receipt imply
neither of the other facts. Goods Receipt does not calculate economics or
mutate legacy Actual Economics. Future Actual Outcome consumers must bind the
exact COMPLETE acquisition settlement and applicable receipt/sale events; they
must not select latest state.

Legacy `ActualEconomics.record_sale` cannot decrement owned inventory because it
has no sold quantity, exact sourcing-product/receipt lineage, or fulfillment
semantics. ADR-0054 therefore defines a marketplace-generic, exact-product,
batch/window `ActualSaleSettlement`; the first marketplace is Coupang through
manual evidenced ingest, with no automatic synchronization. Only a terminal
`COMPLETE` settlement's confirmed fulfilled/non-cancelled quantity is an
authoritative outbound fact, effective at the explicit window end rather than
order, payment, payout, admission, or `settled_at` time. Cancellation does not
decrement stock, while refunds and returns do not restore stock without a future
inspected return/adjustment authority.

The CR-1B6C2 writer reconstructs immutable Goods Receipt/product lineage and
transactionally enforces non-overlapping source scope, reference deduplication,
and chronological COMPLETE outbound not exceeding eligible sellable receipts
at every period-end boundary. One `BEGIN IMMEDIATE` transaction repeats replay,
revision, source, overlap/reference and oversale checks before committing
history plus command receipt. It rejects v1 backorder/oversale and never clamps
a negative balance. CR-1B6C3's
`receipt-and-complete-sale-derived-owned-inventory / 2.0.0` projection now
subtracts only COMPLETE settlement outbound; receipt-only v1 remains unchanged.
Unknown fees, refunds, advertising, fulfillment/storage, other material costs,
or finality keep a revision `BLOCKED` and contribute no outbound.

Actual Sale Settlement preserves sale-side quantities and batch monetary facts
but does not itself calculate profit, margin, ROI, Actual Outcome, or Variance.
CR-1B6D2's separate Actual Outcome owner binds exact acquisition, receipt, and
sale history. Reservation and allocation remain separate future dimensions.
`InventorySnapshot` may disagree with owned inventory without either authority
being rewritten.

ADR-0055 defines `ActualOutcome` as an immutable persisted cumulative
assessment for one exact O2/product and one Purchase Execution. The caller names
one exact acquisition settlement and an explicit ordered COMPLETE-sale prefix;
the owner reconstructs and freezes the complete receipt set through the terminal
sale boundary. v1 refuses multiple contributing purchases because no FIFO, LIFO,
weighted-average, or lot-allocation authority exists.

The implemented calculation preserves executed, received, sellable, damaged, sold,
remaining, and unreceived quantity separately. ADR-0051 per-executed-unit cost
allocates into sold COGS, remaining inventory basis, damaged loss, and unreceived
exposure with exact batch conservation. Profit uses canonical sale credits and
cost components rather than payout, excludes customer tax and unadmitted
seller-side tax, expenses sold COGS and damaged loss, and leaves remaining or
unreceived basis as capital exposure. Zero sales, partial receipt, partial sale,
and negative profit may be CALCULABLE; ratio unavailability and batch resolution
are separate facts. Domain/Application, append-only SQLite persistence, and the
production API are implemented. The manifest freezes complete canonical
acquisition/receipt/sale snapshots, while read/replay never consults current
sources or selects latest history.

One CALCULABLE ActualOutcome over genuine purchase, acquisition, receipt, and
sale evidence defines the Real-Money Validated MVP commerce-fact cut. Closed-Loop
Learning MVP additionally requires an exact Conservative Economics result and
persisted Variance v2; ActualOutcome itself has no predicted-source dependency.

CR-1B7B3 adds no new authority. It exposes the already-fixed Actual Acquisition
and Actual Sale category/state contracts as closed OpenAPI enums and supplies a
Founder operational runbook for the complete production HTTP chain. The runbook
uses an external evidence folder, an external non-authoritative ID manifest, and
immediate request/response JSON archival because most append-only command results
do not have broad recovery GET endpoints. The exact pre-purchase Conservative
result and READY execution chain are frozen before external checkout; unknown,
not-applicable, known zero, payout reconciliation, and return finality retain
their Domain meanings. No workflow state, evidence binary store, recovery table,
or implicit database access is added.

ADR-0056 defines Variance v2 as an immutable exact-pair comparison
under `conservative-actual-variance / 2.0.0`. It binds explicit persisted
Conservative and ActualOutcome IDs, reconstructs only named immutable lineage
and component sources, and never selects latest or recalculates either result.
Metric comparability, overall comparison state, and calibration eligibility are
separate. Partial and zero-sale outcomes remain useful without fabricated sale
values; predictions not calculated strictly before Purchase Execution remain
numerically comparable where safe but calibration-ineligible. CR-1B6E2
implements the Domain/Application authority, exact-source reconstruction,
append-only SQLite history and receipts, and the thin production API. It does
not implement a calibration engine or any automatic model or policy update.

`POST /api/v1/opportunities/{opportunity_id}/actual-sale-settlements` exposes
manual marketplace-generic admission with the first controlled path using
`COUPANG`. Exact replay is historical and does not re-evaluate current inventory;
fresh BLOCKED/COMPLETE revisions return 201, replay returns 200, and missing,
conflict, structural and bounded persistence failures map to 404/409/422/503.
Zero-sale COMPLETE windows are valid. No route calls Coupang, calculates
profit/margin/ROI, creates Actual Outcome, mutates legacy Actual Economics, or
reinterprets receipt-only Owned Inventory v1.

`POST /api/v1/opportunities/{opportunity_id}/actual-outcomes` exposes the
production-callable cumulative result. The caller names one exact acquisition
settlement and a non-empty ordered sale-settlement prefix. The server derives
the exact Purchase Execution, receipt set, quantities, category-level conserved
cost allocation, sale credits/costs, COGS, damaged loss, remaining/unreceived
basis, profit, margin/ROI availability, and inventory resolution. It refuses
prefix omissions, source-lineage contradictions, impossible quantities, and
unsupported multi-purchase allocation. It performs no FX, predicted-value
fallback, inventory mutation, or legacy Actual Economics/Variance write.
