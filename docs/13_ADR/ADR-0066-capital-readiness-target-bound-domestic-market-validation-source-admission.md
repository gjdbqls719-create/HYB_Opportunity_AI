# ADR-0066: Capital Readiness Target-Bound Domestic Market Validation Source Admission

## Status

Accepted

## Implementation Status

PR C2 implements this decision additively in the existing Capital Readiness
Domain, Application, SQLite, production API, and composition boundary. Capital
Gate, Founder Capital Approval, Real-Money Execution Intent, and Purchase
Execution Record remain unchanged.

## Context

ADR-0045 defines Capital Readiness as the authority that decides whether one
exact Opportunity's trusted market, Sourcing, Economics, and Critical Cost
facts are sufficiently complete and internally consistent for Capital Gate.
Its original contract consumes only ADR-0044 DMV v1 and proves subject equality
through `MarketObservationIdentity`.

ADR-0060 instead owns a pre-listing
`NewToMarketDomesticSellingTargetIdentity`. ADR-0064 validates Competition and
Demand v2 for that exact target, and ADR-0065 preserves the same target in an
exact Founder Sourcing lineage while retaining independent Product Match and
Quote authority. Converting those facts to DMV v1 or fabricating a Market
identity would destroy their meaning.

The Capital Readiness business decision does not otherwise change. Trusted
market evidence must concern the same intended domestic-selling subject as the
exact supplier product and Economics chain, but Capital Readiness still does
not decide profit thresholds, BUY, INVEST, capital sufficiency, or permission
to spend.

## Decision

### One Capital Readiness authority

Keep one `CapitalReadinessAssessment` authority, policy
`domestic-commerce-capital-readiness` version `1.0.0`, state set, and ordered
reason set. Add source discrimination rather than creating a parallel Capital
Readiness v2 authority.

The historical `capital-readiness-command-v1` contract and fingerprint remain
byte-for-byte unchanged. Add `capital-readiness-command-v2`, which contains
only:

- command ID;
- route Opportunity ID;
- exact Conservative Economics result ID;
- exact discriminated DMV source reference;
- exact Critical Cost assessment ID;
- request time; and
- the existing Readiness policy and command schema.

The source reference contains exactly `kind` and `assessment_id`. Supported
kinds are `domestic_market_validation_v1` and
`domestic_market_validation_v2`. The caller cannot supply a target, Market
identity, discovery reference, source-manifest fingerprint, or latest/current
selector. The command fingerprint naturally includes the exact kind and
assessment ID.

### Exact source reconstruction

The Application resolves the named assessment through an explicit exact read
port for its kind. For DMV v2, the server derives the immutable
`source_manifest_fingerprint`; callers never attest it.

All existing Economics and Critical Cost lineage checks remain. Subject
equality is discriminated as follows:

- DMV v1 requires the existing exact `MarketObservationIdentity` equality;
- DMV v2 requires `NewToMarketDomesticSellingProductLineage` and exact
  equality between its `target_identity` and the DMV v2 target binding.

Both paths require exact Opportunity ID and discovery-reference equality.
Opportunity equality alone never proves supplier-product or target equality.
The existing Product Match, Quote revision/status/validity, source policy,
normalization, and Critical Cost rules remain unchanged. Existing reason codes
represent blocked business results; no target-specific reason vocabulary is
introduced.

### Manifest and assessment versions

Fresh command-v2 evaluations persist
`capital-readiness-source-manifest-v2` and `capital-readiness-v3`. The manifest
retains every existing exact source pin and adds only:

- `domestic_market_validation_source_kind`;
- conditional
  `domestic_market_validation_source_manifest_fingerprint` (required for DMV
  v2 and absent for DMV v1); and
- `critical_cost_normalization_id`.

The target identity is deliberately not copied into Capital Readiness. It is
reconstructed from the exact DMV and Sourcing authorities whenever a normal
source-validating read is required. Historical assessment and manifest
versions remain readable without backfill or reinterpretation.

### Persistence and replay

Reuse the existing append-only `capital_readiness_history` and
`capital_readiness_receipts` tables and columns. Manifest and assessment
evolution occurs inside the existing integrity-covered payload. There is no
new table, column, migration, compatibility row, or historical rewrite.

Fresh writes validate the exact resolved DMV kind, assessment ID, DMV v2
manifest fingerprint when applicable, and Critical Cost normalization pin.
Normal `get_assessment` reconstruction continues to validate exact live source
integrity for Capital Gate and audit reads.

Command-v2/assessment-v3 replay is receipt-first and reconstructs only the
persisted Readiness assessment and receipt. It does not reread DMV, Sourcing,
Economics, Critical Cost, issue identities, call clocks, or re-evaluate policy.
A changed source kind or assessment ID under the same command ID conflicts.

### Production API

The existing Opportunity-scoped Capital Readiness route keeps its historical
flat DMV v1 request. The additive command-v2 request supplies:

```json
{
  "command_id": "...",
  "conservative_economics_result_id": "...",
  "domestic_market_validation_source": {
    "kind": "domestic_market_validation_v2",
    "assessment_id": "..."
  },
  "critical_cost_assessment_id": "...",
  "requested_at": "..."
}
```

The v2 response exposes the source kind, exact assessment ID, conditional DMV
v2 manifest fingerprint, and Critical Cost normalization ID. It exposes no
target identity or compatibility Market identity. Unknown kinds, mixed flat
and discriminated requests, and caller-owned lineage/fingerprint fields are
rejected.

## Downstream reuse

Capital Gate consumes the exact Capital Readiness assessment ID, common state,
policy, Economics, requirement, and deployable-capital facts. It does not
consume DMV kind, Market identity, or target identity. Therefore Capital Gate,
Founder Capital Approval, Real-Money Execution Intent, and Purchase Execution
Record require no contract or implementation change.

## Explicit prohibitions

- no DMV v2 to DMV v1 conversion or compatibility row;
- no synthetic `MarketObservationIdentity`;
- no target-to-Market or ADR-0060-to-ADR-0049 bridge;
- no Opportunity-only target/Sourcing equality;
- no latest/current/fallback source selection;
- no caller-supplied target, discovery reference, or source fingerprint;
- no Capital Readiness policy, state, or reason change;
- no parallel Capital Readiness v2 authority;
- no Capital Gate, Founder approval, or execution-chain semantic change.

## Consequences

One exact `VALIDATED_FOR_CAPITAL` DMV v2 assessment can now join the same
ADR-0060 target preserved by Founder Sourcing and the existing exact Economics
and Critical Cost chain. HYB can issue a target-backed
`READY_FOR_CAPITAL_REVIEW` assessment that the unchanged Capital Gate can
consume. This opens the existing economic-attractiveness and capital-sufficiency
decision without granting purchase approval by itself.

Historical DMV v1 and Capital Readiness behavior, payloads, fingerprints, and
replay remain unchanged.

## Rejected alternatives

### Separate Capital Readiness v2 authority

Rejected because the owned decision, policy, states, reasons, Economics checks,
and downstream Gate contract do not change.

### Target-to-Market compatibility bridge

Rejected because ADR-0060 intentionally represents a selling target for which
an exact KR listing/canonical Market identity does not yet exist.

### Latest-source resolution

Rejected because capital-facing authority must preserve exact immutable source
selection and deterministic replay.
