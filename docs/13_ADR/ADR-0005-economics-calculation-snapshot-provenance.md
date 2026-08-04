# ADR-0005: EconomicsCalculation Snapshot Provenance

## Status

Accepted

## Context

`calculate_verified_economics` converts a `VerifiedEconomicsInput` into the
legacy calculator input, calls `calculate_opportunity`, and returns an in-memory
`EconomicsCalculation`. The runtime result contains typed fee and cost outputs,
profit, ROI values, margin, and an open analysis mapping. It does not contain an
Opportunity identity, Market Observation identity, source snapshot ID,
calculation version, or generation time.

The immutable Verified Economics snapshot owns accepted input facts and their
evidence. Validation admission stores summary ROI and recommendation fields, and
the estimated baseline stores selected variance fields, but neither is the exact
EconomicsCalculation provenance record.

The current calculator has no break-even calculation. A snapshot must preserve
that absence explicitly through the existing MoneyInput evidence contract; it
must not manufacture a break-even value.

## Decision

The Economics Calculator exclusively owns creation of
`EconomicsCalculationSnapshot`. The snapshot references the exact Verified
Economics snapshot rather than copying or reconstructing accepted source inputs.
It copies current calculation outputs into immutable MoneyInput and Decimal
fields and never embeds the runtime EconomicsCalculation object.

The snapshot also preserves the actual marketplace, thresholds, monthly-sales,
competitor, risk, and deeply immutable context parameters supplied to the
calculator. Profitability provenance contains the minimum-profit and minimum-ROI
thresholds and the calculator's three existing filter results. These facts are
required because Production Safety currently consumes
`passes_profitability_filter`; preserving only net profit and ROI would lose the
thresholds under which that result was produced.

PR31.1 supplements this contract with the complete canonical runtime analysis
provenance described by ADR-0008. The Verified Economics lineage field is named
`verified_economics_opportunity_id` because the authoritative persisted contract
has no separate snapshot identifier and is queried by Opportunity ID.

Calculation version identifies the formula semantics used for the output.
Immutability prevents accepted input references, output values, thresholds, or
profitability facts from changing after generation.

The Application repository boundary supports save, direct lookup, Opportunity
lookup, and Market Observation identity lookup. No persistence technology is
selected.

Collectors, Validation Admission, Review, Production Safety, Decision, and
Dashboard do not create Economics Calculation snapshots.

## Consequences

- Accepted inputs remain owned by Verified Economics and are linked explicitly.
- Calculation results and profitability thresholds can be audited together.
- Unsupported break-even remains truthful rather than fabricated.
- Runtime and persistence contracts can version independently.
- Calculator wiring and durable persistence remain future work.
- Existing calculations are not inferred, migrated, or backfilled.

## Out of Scope

- Production Safety, Safety API/UI, or Safety receipts
- Decision or Dashboard changes
- SQLite, transaction, migration, or backfill
- Formula, calculator, Verified Economics, or existing test changes
