# ADR-0024: Economics Price Source Handoff and Calculator Ownership

## Status

Accepted

## Decision

PriceIntelligence Snapshot is explicit Economics provenance, not a calculator
formula input. The owner command names the exact Candidate-scoped Price Snapshot,
its analysis command receipt, Candidate/Opportunity promotion binding, Verified
Economics Opportunity, Market identity, parameters, context, and versions. It
never chooses latest Price data, parses evidence references, or substitutes the
recommended price for persisted Verified Economics expected sale price.

`EconomicsCalculationSnapshot` becomes v3 and preserves Candidate ID plus exact
Price Snapshot ID while remaining Opportunity-scoped. The immutable promotion
binding bridges those subjects. Existing v2 rows receive no inferred reference,
migration, or backfill.

The owner loads all sources by exact ID, invokes only
`calculate_verified_economics` with persisted `VerifiedEconomicsInput`, captures
complete typed results and canonical analysis, and commits Snapshot plus receipt
in one `BEGIN IMMEDIATE`. Same command/fingerprint replays without calculator,
generator, or clocks; changed intent conflicts. Different commands may persist
new calculation facts for the same sources. Concurrent pure calculations may
race, but only one result commits per command.

Complete Snapshot Chain binding and Production Safety remain deferred.
