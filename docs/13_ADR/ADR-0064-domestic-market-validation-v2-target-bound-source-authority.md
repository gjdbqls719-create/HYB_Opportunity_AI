# ADR-0064: Domestic Market Validation v2 Target-Bound Source Authority

## Status

Accepted and implementation-authorizing.

PR A implements the Domain and Application authority core described here.

PR B1 implements a separate append-only DMV v2 SQLite history and receipt
namespace, atomic assessment/receipt finalization, deterministic payload
reconstruction and integrity verification, and exact command replay. Persisted
historical replay is resolved before live upstream source resolution and does
not re-evaluate the trust policy.

PR B1.5 exposes the existing exact source-manifest resolver through a read-only
production GET boundary. It creates no assessment, receipt, verification,
state, identity, timestamp, or persistence fact. PR B2 implements the final
validation POST, strict explicit verification request, production source/core/
persistence composition, typed response, HTTP error mapping, and OpenAPI.

## Context

Domestic Market Validation (DMV) admits market evidence for Capital use. The
v1 authority is bound to `MarketObservationIdentity` and v1 Competition and
Demand contracts. ADR-0060 instead defines a new-to-market domestic-selling
target, while ADR-0061/ADR-0063 and ADR-0062 define independent Competition v2
and Demand v2 publications for that target. Reinterpreting either v2 authority
as v1 would destroy its meaning and lineage.

DMV v2 therefore needs an additive authority that pins the exact target and
exact immutable v2 publications without copying their raw evidence.

## Decision

DMV v2 is an independent Capital-facing trust-admission authority. It does not
decide profitability, ROI, BUY, INVEST, Capital Gate, or permission to spend.
Its subject is resolved through the existing chain:

`Opportunity -> OpportunityDomesticSellingTargetBinding -> NewToMarketDomesticSellingTargetIdentity`

The caller cannot submit a replacement target or a synthetic
`MarketObservationIdentity`. The target source preserves the existing binding
fields, including the opportunity, discovery reference, target identity,
binding time, and existing target/binding schema versions. DMV v2 does not add
or pin an opportunity lifecycle version.

## Exact Upstream Authority Pins

The source manifest pins one exact Competition v2 publication using its
`CompetitionV2ObservationIdentity`, cohort ID, authority fingerprint,
observation/cohort/assessment versions, assessment policy version, publication
times, and immutable artifact provenance already owned by Competition v2.

The initial trust policy uses `CompetitionV2Availability` directly.
`COMPLETE_WITH_MARKETPLACE_SIGNAL`,
`COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL`, and `COMPLETE_CORE_ONLY` are
core-admissible. `UNAVAILABLE` produces a durable DMV `BLOCKED` assessment.
Rocket or other marketplace-signal completeness is not a new core requirement.

The manifest pins one exact Demand v2 publication using its observation and
assessment IDs, comparable cohort ID, authority fingerprint, existing
observation/assessment/cohort versions, policy version, publication times, and
exact `CompetitionCohortReference` when present. The initial trust policy uses
`DemandFamilyStatus` and `DemandV2Availability` directly: Market Intent and
Comparable Market Response must both be `COMPLETE`, and aggregate availability
must be `COMPLETE_CORE`. Otherwise DMV issues a durable `BLOCKED` assessment.
`TARGET_LISTING_ABSENT` for the ADR-0060 target is not itself a blocker.

## Competition and Demand Cross-Authority Invariant

When Demand carries a `CompetitionCohortReference`, every existing reference
dimension must exactly match the selected Competition publication: observation
ID, identity kind and version, cohort ID, authority fingerprint, observation
and cohort-policy versions, and artifact reference and SHA-256. A mismatch is a
source conflict/precondition error and no DMV assessment is issued.

When Demand owns its comparable cohort and has no Competition reference, DMV
does not invent a cohort-equality rule.

## Source Manifest and Verification

One immutable `DomesticMarketValidationV2SourceManifest` contains the target
binding reference and the exact Competition v2 and Demand v2 publication
references. It contains no second copy of upstream raw evidence. Canonical
serialization of that manifest produces one deterministic SHA-256
`source_manifest_fingerprint`; no separate target digest exists.

`DomesticMarketVerificationV2` records the operator, verification time,
explicit current-use confirmation, the one reviewed source-manifest
fingerprint, and its schema version. A missing/non-current confirmation or a
reviewed fingerprint mismatch produces a durable DMV `BLOCKED` assessment.

Exact immutable source absence, target mismatch, publication mismatch, or the
cross-authority mismatch above is instead a source/precondition error. DMV does
not publish an assessment for those conditions.

### Operational verification workflow

The Founder/operator names one exact Competition v2 observation and one exact
Demand v2 observation and reads the DMV v2 source-manifest preview. The preview
delegates to the same Application resolver used by final validation and returns
the existing manifest plus exactly
`DomesticMarketValidationV2SourceManifest.fingerprint`; there is no preview
fingerprint or latest-source selection.

Reading the preview is not verification. After reviewing the returned target
binding and source pins, the operator explicitly supplies that fingerprint in
`DomesticMarketVerificationV2` with current-use confirmation. The future final
POST resolves the same named authorities again. A changed fingerprint is
handled by the existing verification mismatch policy; the server never updates
or substitutes the reviewed fingerprint. Preview retrieval performs no DMV
history or receipt write and emits no assessment state.

## Time Contract

DMV v2 adds no TTL or arbitrary freshness window. Existing authoritative target
binding and Competition/Demand publication times must not be later than the
current-use verification, and verification must not be later than evaluation.
The authority consumes publication-level time semantics and does not reinterpret
all upstream raw-evidence timestamps.

## Command and Fingerprints

The v2 command is separate from v1. It names the command, opportunity, exact
Competition observation/publication, exact Demand observation/publication,
current-use verification, request time, and supported DMV v2 policy/schema. It
cannot declare state, Capital readiness, BUY/INVEST, profit/ROI, assessment ID,
target subject, or raw upstream evidence.

The deterministic `command_fingerprint` identifies replay intent. The resolved
`source_manifest_fingerprint` identifies exact source authority integrity.
These responsibilities remain separate.

## Replay and Versioning

DMV v2 is additive. DMV v1, Competition v2, Demand v2, and ADR-0060 retain their
existing meanings and fingerprints. There is no v1 conversion, compatibility
publication, historical backfill, latest-source resolution, or automatic alias
by source fingerprint.

PR B persistence must make the same command ID and fingerprint replay the exact
persisted publication before new identity, clock, or policy evaluation. The
same command ID with a different fingerprint conflicts. A new command ID using
the same sources is a new validation event because current-use verification is
a distinct trust event.

## Implementation Boundary

PR A owns the ADR, v2 Domain contract, v2 Application use case/read ports, and
focused authority tests. PR B1 owns only append-only SQLite assessment history
and receipts, exact reconstruction/integrity checks, and replay persistence.
PR B1.5 owns only the read-only source-manifest preview API and delegating
production source adapter. PR B2 owns the final v2 validation POST and
request-scoped production persistence composition. The final route reuses the
same source resolver, persists through the B1 replay-first owner, and does not
add v1 compatibility, source selection, or a new authority.
