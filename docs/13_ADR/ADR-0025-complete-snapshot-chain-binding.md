# ADR-0025: Complete Snapshot Chain Binding and Safety Source Selection

## Status

Accepted (PR35-E4)

## Decision

Persist a complete-only `OpportunitySnapshotChainBinding` after the Product,
PriceIntelligence, EconomicsCalculation, Verified Economics, and Candidate to
Opportunity promotion facts have all committed. The binding records their exact
IDs, ordered Product cohort, Candidate/Opportunity bridge, full Market identity,
and a server-issued timestamp. It does not copy or recalculate source facts.

An Opportunity may have multiple append-only chain versions because the existing
Price and Economics owner boundaries permit later calculations. Version numbers
are allocated under `BEGIN IMMEDIATE`. The exact same complete source set is one
authoritative binding; another command receives an alias receipt. A changed
source set receives a new version. There is no current projection: Production
Safety must select an explicit binding ID, and no latest fallback is permitted.

History, normalized ordered Product members, and command receipts are written in
one transaction. History and receipts are immutable. Same-command replay returns
the persisted binding and receipt without regenerating IDs or timestamps; changed
payload under the same command conflicts.

`ProductionSafetyEvaluationContext` is reconstructed from an exact binding plus
an explicit Product Snapshot member. This extra selection is necessary because a
Price cohort can contain several Product Snapshots while the existing Safety
context accepts one Product. Selecting the first or latest Product would invent
provenance. Runtime inputs may be reconstructed through the existing adapter,
but Production Safety execution and Safety persistence remain deferred.

`AdmissionSnapshotChainHandoff` remains a legacy in-memory admission contract.
It is not persisted or auto-converted, and existing rows receive no migration or
backfill. Missing bindings fail explicitly.
