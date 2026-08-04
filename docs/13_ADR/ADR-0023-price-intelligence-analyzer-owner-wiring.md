# ADR-0023: PriceIntelligence Analyzer Owner Wiring

## Status

Accepted

## Decision

The Price Analyzer owns `PriceIntelligenceSnapshot`. Its application boundary
accepts an explicit ordered Product Snapshot cohort, Candidate, finalized group,
Market identity, fallback multiplier, Analyzer version, and command identity.
It loads every persisted Snapshot and source binding and requires the ordered
collector observation IDs to equal finalized group membership exactly. It does
not select latest Candidate snapshots, regroup Products, or sort by Product data.

Runtime Product reconstruction is lossless and shared with the Production Safety
adapter. The existing `analyze_product_prices` function remains the only formula
implementation. Fallback and Analyzer version are explicit provenance; neither
is hidden or derived.

Price Snapshot and `PriceIntelligenceAnalysisReceipt` commit in one
`BEGIN IMMEDIATE`. Same command/fingerprint replays the committed result without
Analyzer, ID generator, or clock calls. Changed intent conflicts. Different
commands may create new immutable analysis facts for the same cohort. Concurrent
Analyzer calls may race, but only one authoritative result commits per command.

Production Discovery orchestrator wiring, Economics Price-source handoff,
Snapshot Chain binding, and Production Safety execution remain deferred.
