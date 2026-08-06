# ADR-0032: OCR Candidate Identity Authority

## Status

Accepted (PR43-A1)

## Context

ADR-0030 assigns fresh OCR Candidate identity issuance to the HYB Application
admission boundary. ADR-0031 requires an injected supplier to be called once
per ordered OCR field after execution replay checks and before the atomic
admission transaction commits. It also requires exact replay to reuse the
Candidate identities stored in the committed `OCRExecutionReceipt`.

The current execution persistence foundation implements that injected
`Callable[[], str]` boundary, ordered receipt membership, atomic rollback, and
concurrent replay convergence. It intentionally does not provide a production
supplier or select an identity algorithm. Production External OCR admission
therefore cannot be composed without deciding who supplies the identity, when
it becomes authoritative, and which algorithm policy is allowed.

`OCRCandidate` identity is distinct from Opportunity Candidate, Artifact, OCR
execution, Human Verification, External Signal, Review, and repository row
identities. Reusing one of those identities or deriving an OCR Candidate ID
from their facts would collapse existing ownership boundaries.

## Decision

OCR Candidate identity is a **HYB server-owned opaque identity**.

The HYB Application admission boundary owns the decision to issue an identity
for each field in a fresh admitted OCR execution. A production Infrastructure
supplier owns the concrete random generation mechanism and satisfies the
existing no-argument `Callable[[], str]` contract. External suppliers, API
callers, OCR providers, Review, and repositories do not issue or select OCR
Candidate identities.

### Identity Authority

- A caller supplies no OCR Candidate ID in authoritative External OCR
  admission.
- The Application calls the injected supplier exactly once for each ordered
  field of a fresh execution and preserves each supplied value unchanged.
- A supplier return value is provisional until the Artifact admission when
  new, execution record, complete Candidate batch, and execution receipt commit
  in the single ADR-0031 transaction.
- After commit, the External Signal Ledger Candidate history is authoritative
  for each Candidate payload and the `OCRExecutionReceipt` is authoritative for
  the execution's ordered Candidate membership.
- Repository sequence values, row IDs, fingerprints, timestamps, and current
  projections are not Candidate identity authorities.
- Review only reloads the immutable Candidate by the committed ID. Human
  Verification and External Signal creation issue their own identities and do
  not replace or reinterpret the OCR Candidate ID.

### Identity Lifetime

- One fresh OCR execution field receives one new OCR Candidate identity.
- Identities are not reused across field positions, distinct executions, or
  legacy caller-created Candidates.
- A valid zero-field execution issues no Candidate identity and commits an
  empty ordered membership.
- A committed Candidate identity is immutable for the lifetime of the
  append-only ledger fact and remains the reference used by Review and Human
  Verification lineage.
- Candidate correction or approval creates separate facts; it does not mutate,
  recycle, or supersede the Candidate identity.
- An identity generated during a rolled-back attempt is never authoritative
  and must not appear in a receipt, ledger history, Review, or API success
  result.

### Replay

- The OCR execution replay key remains `(provider, request_id, artifact_id)`;
  the Candidate ID is not a replay key.
- Exact execution replay loads the committed receipt and returns its original
  ordered Candidate IDs and Candidate facts.
- Exact replay does not invoke the identity supplier and does not issue aliases
  or replacement IDs.
- A changed payload under the same execution key remains an execution conflict;
  it cannot obtain new Candidate IDs to bypass that conflict.
- Restart reconstruction follows the same receipt membership and never derives
  Candidate identity from execution or field facts.

### Concurrency

- ADR-0031 write serialization remains acquired before identity issuance.
- Concurrent same-key, same-payload requests converge on one committed batch;
  the serialized replaying request does not call the supplier.
- Concurrent same-key, changed-payload requests commit at most one batch; the
  conflicting request does not issue authoritative IDs.
- Concurrent distinct executions may independently issue Candidate identities.
- Duplicate values returned within a fresh batch or collision with an existing
  authoritative Candidate identity fail the entire atomic admission. The
  Application does not transform the value or derive a fallback identity.
- A losing or failed attempt's generated values remain non-authoritative even
  if they were observed in memory before rollback.

### Algorithm Policy

The production supplier uses a randomly generated UUID version 4 and returns
its lowercase 32-character hexadecimal representation, equivalent to
`uuid4().hex`.

The supplier is:

- stateless and without mutable instance state;
- called without Artifact, OCR, field, Candidate, Review, or repository input;
- independent for every invocation;
- external to the Application owner and repository; and
- responsible only for supplying an opaque value, not for persistence or
  replay decisions.

The following derivations are prohibited:

- Artifact ID or SHA-256;
- OCR provider, request ID, execution key, execution time, or field position;
- field name, raw text, normalized value, confidence, or bounding box;
- Candidate or execution schema version;
- ledger fingerprint, database row ID, timestamp, counter, or sequence;
- Opportunity Candidate, Review, Verification, or External Signal identity;
  and
- hashes or deterministic combinations of any workflow facts.

No automatic collision retry, aliasing, or deterministic fallback is part of
the identity contract. Persistence validation and ADR-0031 atomic rollback
remain authoritative when a supplied value is invalid or conflicts.

### Compatibility

The existing caller-created `OCRCandidate` path and its test identities remain
legacy compatibility behavior. They are not production External OCR identity
authority and are not backfilled into execution receipts.

Tests may inject deterministic suppliers to verify order, replay, failure, and
concurrency. Such suppliers do not define the production algorithm.

## Alternatives

### Caller- or external-provider-supplied Candidate identity

Rejected. ADR-0030 assigns Artifact and OCR execution facts to external
suppliers but assigns OCR Candidate identity issuance to HYB. Allowing caller
IDs would let external input control an internal durable lineage identity.

### Deterministic identity derived from execution or field facts

Rejected. It would turn provenance or business facts into identity, duplicate
the execution replay contract, and make changed-payload conflict dependent on a
new hash or fingerprint rule.

### Repository-issued identity

Rejected. ADR-0031 requires issuance after authoritative replay checks but
before persistence, while the repository owns durability and conflict rather
than identity policy. Row IDs and fingerprints already have different roles.

### Reuse the Opportunity Candidate production supplier by domain meaning

Rejected. Both suppliers may follow the same UUID v4 encoding policy, but OCR
Candidate and Opportunity Candidate identities have different owners,
lifetimes, persistence boundaries, and lineage. Their concrete types and
Infrastructure exports remain separate.

## Consequences

- Production External OCR admission can add a dedicated Infrastructure
  supplier without changing `OCRCandidate`, the Application callable contract,
  execution persistence, ledger, or Review.
- Exact replay, restart reconstruction, zero-field execution, and concurrent
  convergence retain the ADR-0031 semantics.
- The API cannot accept caller-provided Candidate IDs and must return only IDs
  from the committed execution result.
- A supplier or collision failure leaves no authoritative Artifact, execution,
  Candidate, or receipt from that attempt.
- This ADR defines policy only. It adds no Python implementation, repository,
  schema, FastAPI endpoint, OCR adapter, worker, storage, test, or Review change.
