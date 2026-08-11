# ADR-0059: Candidate Promotion v2 and O1 Admission Authority

## Status

Accepted

## Implementation Status

Decision only. Candidate Promotion v1 remains the only implemented production
write contract. A genuine run must not submit invented v1 admission
recommendation, score, ROI, currency, or safety facts while v2 is unimplemented.

## Context

The first genuine Founder run persisted one exact Discovery Candidate, its
Candidate Context and finalized Group, and one Candidate-owned Product
Observation Snapshot capture. It then stopped before Candidate Promotion because
the current v1 request requires caller-supplied:

- `admission_recommendation`;
- `admission_score`;
- `admission_roi`;
- `currency`; and
- `admission_safety_status`.

The recommendation, score, ROI, and safety values in that list are written into
the legacy `ValidationAdmissionSnapshot`; `currency` is stored beside them. Candidate
Promotion does not reconstruct an authoritative persisted source for those
values. Discovery may transiently calculate score, recommendation, economics,
or safety-like results, but production Discovery persistence retains observations,
finalized Groups, execution results, Candidate handoff, and Candidate issuance—not
a replayable promotion decision source for those transient calculations.

ADR-0018 establishes the relevant ownership timing. Product Observation and
PriceIntelligence snapshots are Candidate-scoped and may exist before an
Opportunity. Verified Economics and EconomicsCalculation are Opportunity-scoped
and can exist only after promotion. ADR-0025 through ADR-0028 then make complete
Snapshot Chain and operational Production Safety explicit downstream authorities.
Requiring their results to create the Opportunity would be circular.

## Decision

### 1. O1 business meaning

An O1 created by Candidate Promotion v2 is a distinct, server-identified
Opportunity that the Founder/operator selected for deeper validation from one
exact persisted Candidate and Product Snapshot lineage.

O1 means only:

```text
the Founder selected this exact Candidate/product provenance
for Opportunity-scoped validation
```

O1 does not mean BUY, approved capital, verified economics, positive ROI,
Production Safety readiness, supplier readiness, or permission to spend money.
Its initial lifecycle is the existing `discovered` state at version 1. Lifecycle
creation is an admission fact, not an investment approval or Founder Capital
Approval.

Candidate identity, Opportunity identity, Market identity, Product Snapshot
identity, and later O2 identity remain separate.

### 2. Promotion v2 prerequisites

A v2 promotion requires all of the following exact persisted facts:

- Candidate and Candidate Context;
- Candidate issuance receipt and its Discovery command/execution lineage;
- the exact finalized Group named by Candidate issuance;
- one committed Candidate-owned Product Snapshot capture whose complete ordered
  source cohort equals that finalized Group's ordered observation membership;
- the exact representative Product Snapshot whose source binding points to that
  Group's persisted representative observation;
- an explicit Founder/operator promotion command, non-empty factual reason, and
  timezone-aware requested time.

The Application reloads every source by exact identity. It verifies Candidate,
discovery reference, Discovery command/execution, finalized Group, complete
Market identity, observation membership/order, capture receipt, Product Snapshot
source bindings, and representative relationship. It performs no latest lookup,
title/URL matching, or caller-assembled lineage acceptance.

The Opportunity ID, Candidate-Opportunity binding ID, admission ID, lifecycle
transition ID, promotion time, and commit time are server-owned.

### 3. v2 request authority

The production route remains the Candidate Promotion boundary. The future request
is explicitly versioned with `contract_version = "2.0.0"` and contains only:

- `promotion_command_id`;
- `candidate_id`;
- `finalized_group_id`;
- exact `representative_product_snapshot_id` as the anchor for reconstructing the
  committed capture and complete ordered cohort;
- `operator_id`;
- `reason`;
- timezone-aware `requested_at`; and
- optional non-authoritative `note`.

Issuing this command is the explicit Founder/operator decision to promote for
deeper validation. No score, recommendation, economic return, safety state,
currency, title, caller-chosen Opportunity ID, or placeholder confirmation is
part of the v2 request.

The exact Product Snapshot source binding uniquely identifies its capture command.
The Application loads that binding, the immutable capture receipt, every ordered
Snapshot, and the finalized Group. Naming one Snapshot is not permission to
accept a partial cohort; any missing, additional, reordered, cross-Candidate, or
cross-Group source fails closed.

### 4. display facts

Title, marketplace, and currency may be returned as display context copied from
the exact representative Product Snapshot and Candidate Market identity. They
are not v2 admission decision inputs and do not become recommendation, economics,
or safety authority. Display fields never participate as identity substitutes.

### 5. removed legacy prerequisite semantics

Candidate Promotion v2 does not accept or persist:

- `admission_recommendation`;
- `admission_score`;
- `admission_roi`;
- `admission_safety_status`; or
- caller-supplied promotion currency.

Their absence is not represented as zero, `WATCH`, `READY`, `UNKNOWN`, null
economics, or another sentinel. No v1 field is copied from transient Discovery
results, Product display facts, or later downstream authorities.

### 6. Candidate Promotion admission v2

The current `ValidationAdmissionSnapshot` and
`validation_queue_admission_snapshots` table are v1 facts with non-null legacy
signal columns. They remain unchanged.

V2 uses a separate append-only, versioned Candidate-promotion admission fact,
stored in an additive v2 history table. It freezes:

- O1 and Candidate identities;
- Candidate Context and Discovery lineage;
- finalized Group identity;
- capture command identity and ordered Product Snapshot IDs;
- representative Product Snapshot identity;
- Founder/operator identity, reason, requested time, and optional note;
- admission kind `founder_selected_for_deeper_validation`;
- policy/schema versions and server admission/commit times.

No v2 row is inserted into the legacy v1 admission table. The existing lifecycle,
Market binding, and common Candidate/Opportunity cardinality anchor remain in the
same atomic promotion transaction.

### 7. Validation Queue evolution

Validation Queue read models become an explicit versioned union:

- v1 items expose their historical recommendation, score, ROI, currency, and
  admission safety status exactly as persisted; and
- v2 items expose the Founder-selection admission basis and exact Product
  Snapshot provenance without legacy signal fields.

V2 does not return nullable or placeholder legacy signals. Consumers that need
recommendation, economics, or safety must load their proper downstream authority.
The direct legacy Validation Admission contract remains v1 history/compatibility;
it is not reused to manufacture Candidate Promotion v2 facts.

### 8. Candidate-Opportunity binding v2

The existing promotion history table remains the common one-Candidate/one-
Opportunity cardinality anchor. A v2 binding keeps the existing common Candidate,
Opportunity, Discovery, finalized Group, Market, command, and timestamp fields
and adds an immutable companion v2 source record containing capture command,
ordered Product Snapshot IDs, and representative Product Snapshot ID.

This additive companion avoids changing historical v1 payload meaning and allows
all readers to use the common lineage fields while v2-aware readers validate the
stronger Product source manifest.

### 9. Product Snapshot relationship

Product Snapshot capture is mandatory for v2 because it is already a persisted,
Candidate-owned pre-admission fact under ADR-0018, ADR-0019, and ADR-0022. It is
not a Product recommendation or an economic approval. Its purpose here is exact
commercial-product and Discovery provenance.

The representative Snapshot must be a member of the exact capture cohort and
must bind to the finalized Group's authoritative representative observation.
Cross-Candidate Snapshot use, a Snapshot outside the exact Group, partial cohort,
latest capture, or caller-created Snapshot lineage is rejected.

### 10. PriceIntelligence relationship

PriceIntelligence is not a Candidate Promotion v2 prerequisite. It remains an
optional Candidate-scoped enrichment that may be persisted before or after O1
creation because its owner does not require Opportunity identity. It becomes
required only where an existing downstream contract explicitly consumes it,
including the complete Snapshot Chain and subsequent operational Production
Safety flow.

Promotion neither selects a latest Price Snapshot nor copies recommended selling
price, score, or analyzer output into O1 admission.

### 11. Discovery decision context

Transient Discovery score, recommendation, economics, confidence, and safety-like
results remain Discovery execution context only. This decision does not persist
them as promotion authorities and does not map:

```text
Discovery score          -> O1 admission score
Discovery recommendation -> O1 investment recommendation
Discovery economics      -> O1 Verified Economics
Discovery safety-like data -> Production Safety
```

Any future decision to persist a Discovery decision result requires its own
explicit authority, provenance, version, and replay contract.

### 12. Economics and safety handoff

After O1 exists, Verified Economics and EconomicsCalculation may be admitted
under their existing Opportunity-scoped contracts. Complete Snapshot Chain
binding then joins the exact Candidate Product/Price sources, Candidate-
Opportunity binding, Opportunity Economics, and Market identity. Operational
Production Safety evaluates only an explicitly selected complete chain/Product.

O1 creation supplies lineage, not those downstream conclusions. Later authorities
must not backfill or rewrite the v2 admission fact.

### 13. O2 compatibility

ADR-0049 remains unchanged. Domestic Selling Admission reconstructs O1 lifecycle,
the common Candidate-Opportunity binding, O1 Market binding, and one exact source
Product Snapshot. It does not consume legacy admission recommendation, score,
ROI, currency, or admission safety status.

A v2 O1 is therefore a valid ADR-0049 source provided the named source Product
Snapshot belongs to its exact persisted v2 promotion cohort and every existing
cross-market equivalence check passes. O2 remains a distinct KR Opportunity and
does not inherit O1 economics or safety.

### 14. replay, aliases, and cardinality

Existing global rules remain:

- one Candidate maps to at most one Opportunity;
- one Opportunity maps to at most one Candidate;
- same v2 command and exact payload replays the committed v2 result;
- changed payload under the same command conflicts;
- a different v2 command for the identical v2 subject may add only an alias
  receipt and returns the same binding/Opportunity;
- all promotion, admission, binding, lifecycle, and receipt facts are append-only
  and commit atomically under `BEGIN IMMEDIATE`.

Policy/schema version and the complete Product source manifest are part of the
v2 subject fingerprint.

V1 and v2 never alias each other. A Candidate already promoted by v1 cannot be
promoted again by v2, and a Candidate promoted by v2 cannot later create a v1
Opportunity. Exact historical v1 command replay remains v1; a new cross-version
attempt conflicts without mutation.

### 15. historical v1 preservation

All existing v1 commands, admission snapshots, promotion bindings, fingerprints,
receipts, O1 identities, lifecycle facts, Market bindings, reads, and replay retain
their original meaning.

There is no migration, inferred Product Snapshot reference, backfill, silent v2
conversion, v1-to-v2 alias, or reinterpretation of v1 recommendation, score, ROI,
currency, or safety values.

### 16. genuine-run continuation

Repository integrity confirms the current genuine facts form one exact lineage:

- Candidate `9b047bd45052488a867cd1bcec48633d`;
- finalized Group `44c772c1f42d4e8b9dd93bc929ae2b1b`;
- Product Snapshot `63edc6a8-6d77-45e8-ad06-9f04b8bea282`;
- the Snapshot source binding points to the Group's sole representative
  observation and to a committed capture receipt; and
- no Candidate Promotion or promotion receipt currently exists for the Candidate.

After v2 implementation, those immutable facts are eligible for the v2 command
without deletion, recreation, mutation, or invented admission signals. The owner
must revalidate them transactionally at write time; this ADR does not itself
create O1 or reserve an Opportunity identity.

## API direction

The existing production Candidate Promotion route evolves to accept an explicit
versioned request. V1 compatibility remains distinguishable from an explicit
`2.0.0` payload; a v2 response is a distinct schema and returns at least:

- contract version, command ID, O1 ID, Candidate ID, and common binding ID;
- exact Discovery/finalized Group/Market lineage;
- capture command ID, ordered Product Snapshot IDs, and representative Snapshot
  ID reconstructed by the server;
- admission kind and Founder/operator decision provenance;
- initial lifecycle state/version;
- server promotion/commit times and replay state.

The v2 response contains no legacy recommendation, score, ROI, currency-as-
decision, or admission safety status fields. OpenAPI must make the v1/v2
distinction explicit rather than inferring a contract from nullable field
combinations.

## Consequences

- The genuine Founder run can continue without fabricated decision values after
  the bounded v2 implementation.
- O1 regains its narrow role as the bridge from Candidate provenance to
  Opportunity-scoped validation.
- Product lineage becomes stronger at promotion without making Price,
  Economics, or Safety circular prerequisites.
- Historical v1 meaning and global Candidate/Opportunity cardinality remain
  stable.
- Validation Queue consumers must become version-aware instead of assuming
  every admitted Opportunity has legacy recommendation/score/ROI/safety fields.

## P0 closure condition

The implementation closes the current genuine-run blocker only when production
HTTP can execute:

```text
persisted genuine Candidate
+ exact committed Product Snapshot capture
-> Candidate Promotion v2
-> O1(discovered)
-> ADR-0049 Domestic Selling Admission
-> O2
```

without invented legacy signals, raw SQLite writes, private repository calls,
latest selection, or deletion/recreation of the genuine Candidate/Snapshot facts.

## Out of scope

- new scoring, ROI, recommendation, or safety algorithms;
- persistence of transient Discovery decision results;
- ItemScout or Coupang automation;
- UI, authentication, or workflow orchestration;
- O2 redesign;
- Capital, Purchase, Actual Outcome, or Variance changes;
- automatic calibration or policy learning.
