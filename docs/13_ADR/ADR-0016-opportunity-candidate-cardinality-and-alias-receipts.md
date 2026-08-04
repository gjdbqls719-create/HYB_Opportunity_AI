# ADR-0016: Opportunity Candidate Cardinality and Alias Receipts

## Status

Accepted

## Decision

Candidate cardinality is exactly one per `(Discovery command ID, finalized Group
ID)`. Candidate and `DiscoveryOpportunityContext` are one-to-one. Issuance
command receipt cardinality is one per issuance command, and Candidate-to-receipt
cardinality is one-to-many.

The first issuance stores Candidate, Context, and Receipt atomically. A different
issuance command with the same Candidate subject stores an immutable alias
Receipt referencing the existing Candidate. It cannot generate a new Candidate
ID, change Candidate issuance time, or modify prior receipts. This alias fact is
required so later reuse of that issuance command for another payload remains an
explicit command conflict after restart.

## Fingerprints

Subject fingerprint covers Discovery command/execution, finalized Group,
explicit discovery reference, complete explicit Market identity, and issuance
contract version. Command fingerprint covers the subject fingerprint, command
request time, and version. Issuance command ID selects its receipt but is not a
Candidate identity input. Candidate ID, Candidate issuance time, and Receipt
commit time are result facts and are excluded from both fingerprints.

## Atomicity and Concurrency

`BEGIN IMMEDIATE` serializes initial and alias issuance. Initial insertion writes
Candidate history, Context, and Receipt; alias insertion writes only Receipt.
Every path revalidates persisted command, completed non-zero Result, Group
membership/execution, representative Observation, and explicit Market identity
inside the transaction. Any Candidate, Context, Receipt, or commit failure rolls
back the complete attempted fact.

Concurrent valid commands for the same subject converge to one Candidate and
Context with one Receipt per issuance command. Same-command changed payload and
same-subject changed provenance remain distinct conflicts. No process-local lock
or silent retry is used.

## Lifecycle and Legacy Isolation

Persisted Candidate issuance is pre-admission identity, not Opportunity creation
or lifecycle admission. Existing Groups and PR34-C in-memory results are not
backfilled or inferred. Collector, grouping, Snapshot ownership, Safety,
Validation Admission, Review, Decision, Dashboard, API, and UI remain unchanged.
