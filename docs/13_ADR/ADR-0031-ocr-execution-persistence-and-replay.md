# ADR-0031: OCR Execution Persistence and Replay

## Status

Accepted (PR42-B1)

## Context

ADR-0030 selects the production authority path:

```text
External OCR -> Artifact Reference -> OCR Candidate
```

The existing foundation persists one `OCRCandidate` at a time in the External
Signal Ledger. It has no durable Artifact admission fact, OCR execution record,
execution receipt, ordered Candidate membership, or zero-field completion fact.
`OCRResult` carries provider provenance and ordered field results, but
`OCRCandidate` and its ledger payload do not retain provider, provider version,
request ID, result confidence, or bounding boxes. The existing ledger
fingerprint is a Candidate duplicate guard and duplicate writes are conflicts;
it is not the execution replay key defined by ADR-0030.

Without an execution-level persistence boundary, restart cannot reconstruct an
exact result, concurrent submissions cannot converge safely, and a failure
between Candidate writes can expose a partial authoritative execution.

## Decision

Use **one atomic transaction** for a fresh OCR admission. Append-only
checkpoints with an incomplete execution state are rejected.

The durable admission boundary consists of four immutable facts:

1. **ArtifactAdmissionRecord** preserves the complete admitted
   `ArtifactReference`, its Artifact replay key, the HYB admission time, and its
   schema version.
2. **OCRExecutionRecord** preserves the complete normalized external execution
   payload and the OCR execution replay key.
3. The existing **OCR Candidate history** in the External Signal Ledger remains
   the authoritative store for each unverified `OCRCandidate`.
4. **OCRExecutionReceipt** preserves the execution key, Artifact key, ordered
   Candidate IDs, Candidate schema version, committed time, and receipt schema
   version. The receipt is the execution completion boundary.

`OCRExecutionRecord` owns input provenance. `OCRExecutionReceipt` owns the
committed output membership. They are separate facts and share the execution
key; no additional execution or receipt UUID is introduced. Ordered membership
is stored once in the receipt and is not duplicated as a second Candidate
source of truth.

Artifact admissions and OCR executions are separate append-only histories.
Neither requires a mutable current projection to determine replay or
completion; the immutable record and committed receipt are authoritative.

### Identity Ownership

- The external Artifact supplier owns `artifact_id` and SHA-256 as established
  by ADR-0030. Artifact admission introduces no new opaque identity.
- The external OCR supplier owns `provider` and `request_id`. Together with
  `artifact_id`, they form the OCR execution identity and replay key.
- The HYB Application boundary owns fresh OCR Candidate identity issuance
  through an injected supplier. The supplier is invoked once per ordered field.
- The OCR execution key is also the receipt identity. Receipt timestamps,
  fingerprints, sequence numbers, and repository row IDs are not identities.

The Candidate identity algorithm and concrete production supplier remain
outside this ADR. Candidate identity must remain opaque and must not be derived
from OCR text, values, confidence, Artifact hash, execution key, field position,
or repository state.

### Artifact Replay and Conflict

The Artifact replay key is `(artifact_id, sha256)`.

- The same key with the same complete normalized `ArtifactReference` is exact
  Artifact replay and reuses the existing `ArtifactAdmissionRecord`.
- The same key with changed Artifact metadata is a conflict.
- The same `artifact_id` with a different SHA-256 is a conflict.
- The same SHA-256 under a different `artifact_id` is a distinct externally
  identified Artifact and is not deduplicated by HYB.

The complete Artifact comparison excludes HYB-generated admission time. Exact
Artifact replay does not replace the original admission time or append another
Artifact record.

### OCR Execution Replay and Conflict

The execution replay key is `(provider, request_id, artifact_id)`.

The execution payload comparison retains and compares all of these facts:

- provider;
- provider version;
- request ID;
- Artifact ID and admitted Artifact key;
- execution time;
- result confidence;
- execution schema version;
- ordered field position;
- field name;
- raw text;
- normalized value;
- field confidence; and
- optional bounding box.

The same execution key with the same complete normalized payload is exact
replay. It returns the committed receipt, reloads its ordered Candidate IDs from
the External Signal Ledger, validates that their facts match the execution
record by position, and returns the original ordered Candidates.

The same execution key with any changed payload fact is a conflict. Existing
Artifact, execution, Candidate, and receipt facts remain unchanged. A different
execution key for the same exact Artifact is a distinct execution and is
allowed.

The physical canonical encoding or fingerprint algorithm used to compare
payloads is an Infrastructure detail. It must cover every fact listed above and
must not redefine either replay key.

### Candidate Batch and Reconstruction

For a fresh execution, the Application requests exactly one opaque Candidate ID
for each field in the external field order. It constructs one unverified
`OCRCandidate` per field using:

- the supplied `ArtifactReference` unchanged;
- the HYB-issued Candidate ID;
- field name, raw text, normalized value, and field confidence unchanged;
- `OCRResult.executed_at` as Candidate capture time; and
- the admitted Candidate schema version.

The receipt stores Candidate IDs in that same order. Position `n` in the
receipt identifies the Candidate constructed from position `n` in the execution
record. Reconstruction never sorts by Candidate ID, field name, timestamp, or
ledger projection order.

A valid execution with zero fields is an authoritative successful execution.
It atomically commits the Artifact record when new, the execution record, and a
receipt with an empty Candidate ID tuple. It appends no Candidate. Exact replay
reconstructs the same empty result.

### Transaction and Completion

Choose transaction strategy **A**:

```text
Artifact admission when new
  + OCR execution record
  + every OCR Candidate history/projection write
  + OCR execution receipt
  = one atomic transaction
```

The persistence boundary obtains its write serialization before authoritative
lookups, Candidate identity issuance, or clock calls. The receipt is written
last inside the transaction. A committed receipt proves that the execution
record and every ordered Candidate are durable. Absence of a receipt means the
execution is not authoritative and cannot be replayed as completed.

Any identity supplier, clock, Candidate validation, ledger write, execution
write, receipt write, projection, or commit failure rolls back every fresh fact
from that attempt. In-memory Candidate IDs produced by a failed attempt are not
authoritative and cannot be returned as committed facts.

HYB records Artifact admission time only when a new Artifact record is admitted
and execution committed time only for a fresh execution receipt. Exact execution
replay invokes neither Candidate identity suppliers nor clocks. Exact Artifact
replay followed by a fresh distinct execution invokes only the execution
completion clock and Candidate identity supplier.

### Conflict Ordering

After side-effect-free Domain and input-shape validation, the authoritative
order inside the serialized transaction is:

1. load Artifact admission by `artifact_id` and apply Artifact replay/conflict;
2. load execution and receipt by the OCR execution key;
3. return exact execution replay or reject changed execution payload;
4. for a fresh execution, request Candidate identities in field order;
5. construct and validate the complete Candidate batch and its lineage;
6. obtain only the clocks required for new facts;
7. persist the new Artifact record when needed, execution record, all Candidate
   history/projections, and receipt atomically; and
8. commit before returning the result.

Artifact conflict is therefore reported before execution replay or execution
conflict. Exact replay performs no identity issuance, clock access, or writes.

### Concurrency

- Concurrent same-key, same-payload submissions converge on one execution,
  one receipt, and one ordered Candidate batch. The serialized loser reloads
  exact replay before identity or clock calls.
- Concurrent same-key, changed-payload submissions commit at most one payload;
  the other conflicts without appending Candidate facts.
- Concurrent distinct executions for the same exact Artifact may both commit,
  each with its own receipt and Candidate batch.
- Concurrent reuse of one `artifact_id` with different SHA-256 values commits at
  most one Artifact; the other submission conflicts before execution admission.
- No loser-generated Candidate ID may be persisted, returned, or referenced by
  a receipt. Serialization is acquired before Candidate identity issuance.

### Existing External Signal Ledger

The External Signal Ledger remains the authoritative owner of OCR Candidate
history and the read boundary used by Review. The OCR execution persistence
owner coordinates the Artifact and execution facts, the existing Candidate
ledger writes, and the receipt under one caller-owned transaction. The execution
repository does not maintain a second Candidate payload store, and the ledger
current table remains a projection rather than execution membership authority.

The existing public `save_candidate()` behavior commits one Candidate at a time
and cannot satisfy this boundary unchanged. Future implementation must provide
transaction participation without exposing partial execution state. The
existing Candidate fingerprint remains a Candidate-level duplicate guard and
must be reconciled so it cannot reject a legitimate distinct execution or act
as the execution replay receipt.

### Migration and Compatibility

Existing caller-created OCR Candidates and legacy ledger rows remain read-only
legacy compatibility facts for the new production admission path. This ADR does
not remove isolated compatibility writers, but their output remains unverified
Candidate facts and is not authoritative production OCR execution lineage.

There is no implicit backfill, inferred execution key, synthesized provider
metadata, receipt creation, or migration into production execution history.
Only Candidates named by a committed `OCRExecutionReceipt` belong to the new
production admission path. Existing Review and Human Verification behavior is
otherwise unchanged.

## Alternatives

### Append-only checkpoints with incomplete recovery

Rejected. Checkpoints would require a new incomplete-state lifecycle, recovery
ownership, and rules for whether partially appended Candidates are visible to
Review. ADR-0030 requires exact execution replay and immutable unverified facts;
a single transaction satisfies those semantics without introducing a second
workflow state machine.

### Execution repository owns duplicate Candidate history

Rejected. Review already reloads authoritative Candidates from the External
Signal Ledger. Copying Candidate payloads into execution persistence would
create two sources of truth and ambiguous conflict behavior.

### Existing ledger fingerprint as execution receipt

Rejected. The fingerprint is per Candidate, omits execution/provider facts and
field payload, cannot represent ordered membership or zero fields, and treats a
duplicate as conflict rather than completed replay.

## Consequences

- Artifact replay, execution replay, ordered batches, zero-field success,
  restart reconstruction, and concurrent convergence have one durable contract.
- A receipt is the sole production OCR execution completion boundary.
- Candidate identity suppliers and clocks are never called for exact replay.
- Review continues reading immutable Candidates from the existing ledger; no
  Review or Decision contract changes.
- Implementation requires a minimal new Artifact/execution/receipt persistence
  foundation and transaction participation from the Candidate ledger. Physical
  schema, repository class names, serialization format, and concrete Candidate
  identity algorithm are deferred to implementation and tests.
- Legacy Candidates remain compatible but cannot be presented as production
  OCR execution lineage without forbidden provenance inference.
- This ADR adds no Python production code, tests, API, SQLite schema, identity
  supplier, OCR adapter, Artifact storage, worker, Review, or Decision change.
