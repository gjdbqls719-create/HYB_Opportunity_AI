# HYB System Architecture

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
