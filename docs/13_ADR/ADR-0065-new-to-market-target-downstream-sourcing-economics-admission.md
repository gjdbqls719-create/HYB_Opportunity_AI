# ADR-0065: New-to-Market Target Downstream Sourcing and Economics Admission

## Status

Accepted

## Implementation Status

PR C1 implements the additive target-aware Founder Sourcing lineage, exact
ADR-0060 admission-reference ingress, existing Product Match support, append-only
Sourcing persistence/API reconstruction, and target-bound O2 admission into the
existing Verified Economics snapshot authority. PR C2/ADR-0066 subsequently
implements exact target-bound DMV v2 consumption in the existing Capital
Readiness authority.

## Context

ADR-0060 creates a distinct domestic-selling Opportunity O2 and an immutable
`NewToMarketDomesticSellingTargetIdentity` when an exact KR listing or canonical
Market identity has not been established. ADR-0064 permits Domestic Market
Validation v2 to admit Competition/Demand authority for that target.

Founder Sourcing previously supported only legacy Candidate-Promotion lineage and
ADR-0049 `DomesticSellingProductLineage`. Both require a
`MarketObservationIdentity`, so neither can truthfully identify an ADR-0060
target. Verified Economics likewise rejected a target O2 because operational
admission required a non-null Market binding even though its snapshot is owned
only by an exact Opportunity.

Capital-facing Sourcing and Economics must concern the same intended domestic
selling subject admitted by DMV v2. Opportunity equality alone must not be
treated as supplier-product equivalence.

## Decision

### Target-aware Founder Sourcing lineage

Add `NewToMarketDomesticSellingProductLineage` as the third supported selling
lineage variant. It contains exactly:

- the ADR-0060 O2 `OpportunityIdentity`;
- the exact `new_to_market_domestic_selling_admission_id`;
- the exact `NewToMarketDomesticSellingTargetIdentity` reconstructed from that
  admission; and
- its own schema version.

It does not duplicate the target ID, discovery reference, target schema,
source O1 manifest, Product Snapshot, or target-binding time as independent
fields. Those remain available through the exact ADR-0060 admission and target
identity.

Production ingress accepts only the discriminated reference:

```json
{
  "kind": "new_to_market_domestic_selling_admission",
  "new_to_market_domestic_selling_admission_id": "..."
}
```

The Sourcing Application resolves that exact admission through the existing
ADR-0060 repository. Its normal reconstruction validates admission integrity,
O2 lifecycle, exact target binding, admission/binding target equality,
conflicting Market binding, receipt, and source manifest. There is no latest
admission or latest target selection.

### Product Match ownership

`ProductMatchVerification` retains its existing meaning. It owns the statement:

> This exact Sourcing Product is Founder/operator-verified as a match for this
> exact selling-product lineage.

The new lineage identifies the intended target; it does not assert
target-to-supplier-product equivalence. `FounderSourcingAdmission` continues to
enforce exact Supplier, Sourcing Product, Quote, Product Match, lineage, match
status, and revision invariants.

The Product Match top-level schema remains unchanged because its authority and
fields do not change. The new target lineage and target-aware Founder Sourcing
admission use additive schemas. Historical legacy v2 and ADR-0049 v3 admissions
remain unchanged and readable; target-aware admissions use v4.

### Persistence and replay

The existing Sourcing tables and authority namespace are reused. The new
lineage is serialized with
`lineage_kind = new_to_market_domestic_selling_admission` in both Founder
Sourcing Admission and Product Match payloads. Existing payload fingerprints
cover it. No table, migration, backfill, or historical rewrite is introduced.

The command schema and fingerprint algorithm remain unchanged. The exact
ADR-0060 admission ID is naturally part of the canonical command payload.
Receipt-first replay returns the persisted Sourcing admission without rereading
ADR-0060 sources, running Product Match, issuing identities, or calling clocks.
A changed admission reference under the same command ID conflicts.

### Verified Economics target ingress

The existing Verified Economics admission accepts one exact non-archived O2
with exactly one supported operational subject:

- an existing Market binding; or
- an ADR-0060 target binding.

No subject, dual Market/target bindings, unsupported subject modes, and corrupt
target bindings fail closed. Existing Market-bound behavior remains unchanged.

`VerifiedEconomicsSnapshot`, its command fingerprint, receipt, and SQLite schema
remain unchanged. They own explicit economic facts for one exact Opportunity;
they do not own Market or target equivalence. Exact replay remains receipt-first
and does not depend on current subject bindings.

Existing `EconomicEvidence` supports explicit pre-listing `VERIFIED` or
`ESTIMATED` expected sale price facts with their current source/reference
semantics. This decision introduces no revenue authority and no price formula.

## Ownership

- ADR-0060 owns the O2 target, immutable target binding, and source provenance.
- `ProductMatchVerification` owns the verified target-aware selling-lineage to
  Sourcing Product relationship.
- `FounderSourcingAdmission` owns Supplier, Sourcing Product, Quote, Product
  Match, and evidence admission.
- Verified Economics owns accepted explicit economic facts for O2.
- DMV v2 remains the market-evidence trust authority.
- Capital Readiness remains the later capital-facing composition authority.

## Explicit prohibitions

- no ADR-0060 target to `MarketObservationIdentity` compatibility;
- no ADR-0060 to ADR-0049 conversion;
- no Opportunity-only supplier-product equivalence;
- no inferred or automatic Product Match;
- no O1 Economics copy or fallback;
- no automatic Competition median, Demand, or traction-derived selling price;
- no parallel Founder Sourcing v2 or Verified Economics v2 authority;
- no latest source selection, backfill, or historical reinterpretation.

## Consequences

An ADR-0060 O2 can now create an exact target-bound Founder Sourcing admission,
retain an independent verified supplier-product match and quote, and admit its
own explicit Verified Economics facts. Existing Sourcing Economics Binding,
Landed Cost, normalization, Economics Source Composition, Conservative
Economics, and Critical Cost can continue using their exact O2/source-ID
contracts.

ADR-0066 now permits Capital Readiness to consume one exact DMV v2 assessment
and compare its ADR-0060 target with the target preserved by this Sourcing
lineage. ADR-0065 itself does not own Capital Readiness and does not grant
capital approval or real-money execution permission.

## Rejected alternatives

### Fabricate a Market identity or ADR-0049 bridge

Rejected because the pre-listing target intentionally has no exact KR listing
or canonical-product identity.

### Add parallel Sourcing or Economics v2 authorities

Rejected because Supplier, Quote, Product Match, economic evidence, persistence,
and replay meanings are unchanged. Additive subject support is sufficient.

### Join by Opportunity only

Rejected because Opportunity equality does not prove which intended target a
supplier product was matched against. The exact ADR-0060 admission and target
must be persisted in Sourcing lineage.
