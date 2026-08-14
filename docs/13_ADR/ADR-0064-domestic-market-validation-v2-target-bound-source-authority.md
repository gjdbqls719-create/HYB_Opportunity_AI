# ADR-0064: Domestic Market Validation v2 Target-Bound Source Authority

## Status

Accepted and implementation-authorizing.

PR A implements the Domain and Application authority core described here. It
does not implement SQLite history or receipts, replay persistence, a production
API, OpenAPI, or production composition. Those remain the bounded PR B scope.

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

PR A owns only the ADR, v2 Domain contract, v2 Application use case/read ports,
and focused tests. PR B may add append-only SQLite assessment history and
receipts, exact reconstruction/integrity checks, replay, v2 API/OpenAPI, and
production composition. PR A does not claim those boundaries are implemented.
