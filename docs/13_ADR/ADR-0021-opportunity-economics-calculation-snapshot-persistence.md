# ADR-0021: Opportunity EconomicsCalculation Snapshot Persistence

## Status

Accepted

## Decision

`EconomicsCalculationSnapshot` v2 is an immutable post-admission Opportunity
fact. It records the exact Candidate/Opportunity promotion binding ID and exact
Verified Economics Opportunity source. SQLite validates lifecycle, binding,
Opportunity/discovery reference, Market identity, and Verified Economics inside
one `BEGIN IMMEDIATE` transaction.

The existing calculator consumes `VerifiedEconomicsInput`; it does not consume or
retain a PriceIntelligence Snapshot ID. Although expected selling price evidence
may name Price Intelligence, that string is not an authoritative Snapshot
reference. Therefore this contract does not infer a latest Price Snapshot, parse
an evidence reference as a Snapshot ID, or add an unprovable Price foreign key.
Exact Price-to-Economics lineage remains blocked until the calculator owner emits
that reference explicitly.

Complete typed calculation results, Money/Evidence, profitability provenance,
parameters and deeply canonical analysis are persisted. Decimal values are text,
canonical analysis has its own fingerprint/version, and the full Snapshot has a
second integrity fingerprint. Reconstitution never runs the calculator.

Snapshot ID is the replay key. Same ID/payload replays; changed payload conflicts;
different IDs may represent repeated calculations for one Opportunity. History
is append-only with no current projection. Calculator owner wiring, Price source
contract expansion, handoff persistence, Safety execution, migration, and
backfill remain deferred.
