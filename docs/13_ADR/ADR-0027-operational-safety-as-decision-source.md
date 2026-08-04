# ADR-0027: Operational Production Safety as Decision Source

## Status

Accepted (PR36-B)

## Decision

Production Decision composition, finalization, Readiness, and Dashboard use the
approved operational `production_safety_evaluation_current` projection. The
projection must resolve to immutable evaluation history and exact provenance with
matching Opportunity, rule, schema, and version. Production wiring never falls
back to the legacy admission-time `production_safety_snapshots` row.

`DecisionCompositionSnapshot.production_safety_snapshot_id` remains serialized
for schema compatibility, but its production meaning is the operational
evaluation ID. That exact ID participates in the composition fingerprint. A new
operational current therefore permits a new explicitly requested composition
version; it does not automatically finalize one.

Finalization reloads operational current in the Application boundary and then
checks the same evaluation ID against current/history/provenance inside the
existing composition `BEGIN IMMEDIATE` transaction. A current change between the
two checks is a stale-source conflict and commits no composition. Duplicate
provenance and existing composition version rules remain unchanged.

Dashboard reconstruction loads the immutable evaluation named by the finalized
composition rather than whichever evaluation is current later. Missing or stale
required sources are business conflicts; malformed, unsupported, or identity
conflicting facts are bounded source errors; genuine repository/transaction
failures remain infrastructure-unavailable errors.

Legacy isolated callers may continue using their explicit admission Snapshot
adapter. There is no migration, backfill, implicit fallback, Safety execution
API/UI, automatic Finalize, or Decision/Safety policy change.

PR36-C adds the explicit operational execution UI. It refetches this same
Readiness source after commit and leaves Finalize gated by the authoritative
Readiness response.
