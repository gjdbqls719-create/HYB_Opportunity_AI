# ADR-0030: OCR Artifact Authority

## Status

Accepted (PR42-A)

## Context

The existing market-intelligence foundation defines an immutable
`ArtifactReference`, a provider-neutral `OCRResult`, an unverified
`OCRCandidate`, an `ExtractText` port, and an append-only External Signal
Ledger. Production Review reloads persisted Candidates and treats them as
immutable references. Only a separate Human Verification can promote a
Candidate into a HUMAN_VERIFIED External Signal consumed by Decision
Readiness and Decision Composition.

The foundation does not select a production Artifact or OCR authority.
`ArtifactReference` intentionally excludes bytes and any storage locator, the
dummy adapter performs no Artifact access, and the current Candidate conversion
does not preserve the OCR provider metadata carried by `OCRResult`. A production
contract must therefore choose who owns bytes, Artifact admission, OCR
execution, identity, provenance, replay, and retention without making an
unverified Candidate authoritative for Decision.

## Decision

Select **B: External OCR -> Artifact Reference -> OCR Candidate**.

HYB does not own Artifact bytes or execute OCR inside the authoritative
Application boundary. An external Artifact/OCR supplier owns the bytes and OCR
execution. HYB admits immutable references and extraction facts, persists the
resulting unverified Candidates, and preserves the existing Human Review trust
boundary.

### Artifact Authority

- **Storage owner:** the external Artifact supplier owns and stores the bytes.
  HYB stores no Artifact bytes and does not infer a storage location.
- **Admission owner:** the HYB Application boundary owns admission of an
  `ArtifactReference` and rejects malformed, incomplete, or conflicting
  metadata before an OCR Candidate is persisted.
- **Identity owner:** the external Artifact supplier supplies the opaque
  `artifact_id`. HYB preserves it unchanged and does not derive it from OCR
  text, business values, filenames, or repository row IDs.
- **Hash authority:** the external Artifact supplier computes SHA-256 from the
  exact admitted bytes before supplying the reference. HYB validates the hash
  syntax and preserves it unchanged; without bytes it does not verify content
  or reconstruct a hash from metadata.
- **Replay:** `(artifact_id, sha256)` identifies an exact Artifact admission.
  The same pair and same metadata is an exact replay. Reuse of an
  `artifact_id` with a different hash or conflicting metadata is rejected.
- **Retention:** the external storage owner controls byte retention. HYB
  retains the immutable `ArtifactReference` with append-only OCR Candidate
  history. The reference does not imply that HYB can retrieve bytes after the
  external owner's retention period.

### OCR Authority

- **Execution owner:** the external OCR supplier executes OCR against the bytes
  it can access. `OCRService` remains a provider-neutral Application
  coordinator and does not become an OCR engine.
- **Provider authority:** the executing supplier authoritatively supplies
  `provider`, `provider_version`, `request_id`, `executed_at`, result
  confidence, and ordered field results through `OCRResult`.
- **Confidence authority:** OCR field confidence is the external provider's
  unverified extraction assessment. HYB preserves it but does not treat it as
  human confidence or Decision evidence.
- **Replay:** `(provider, request_id, artifact_id)` is the OCR execution replay
  key. Exact replay returns the previously admitted Candidate identities and
  facts without executing OCR or appending duplicates. A changed execution
  payload for the same key is a conflict.
- **Provider metadata:** the authoritative OCR admission lineage must retain
  provider, provider version, request ID, execution time, result confidence,
  and ordered field provenance including any supplied bounding box. These facts
  must not be inferred later from a Candidate ID or schema version.
- **Candidate identity owner:** the HYB Application admission boundary owns
  opaque OCR Candidate identity issuance for a fresh admitted execution.
  Replay reuses the committed identities. Identity is not derived from raw
  text, normalized values, confidence, Artifact hash, or a repository row ID.

The current `request_id:index:field` Candidate ID construction and the current
ledger duplicate fingerprint are foundation behavior, not the production
identity or execution-replay authority established by this ADR. Production
wiring must reconcile those contracts before it claims authoritative OCR
admission.

`DummyOCRAdapter` remains a deterministic no-I/O test adapter and is not a
production OCR authority. The caller-created `OCRCandidate` Application path
remains a compatibility path; caller-supplied text, confidence, or Candidate
identity does not constitute authoritative production admission under this ADR.

### Review Authority

- Review references a persisted `OCRCandidate` by identity and reloads it from
  the External Signal Ledger.
- Review never mutates or backfills an OCR Candidate or its Artifact reference.
- OCR text, normalized value, and provider confidence remain unverified until
  an explicit Human Verification is persisted.
- Approve or Correct creates separate immutable Human Verification and External
  Signal facts; Skip creates neither.

### Decision Authority

- `OCRCandidate` and `OCRResult` are never direct Decision inputs.
- Decision Readiness and Decision Composition may consume only persisted
  HUMAN_VERIFIED External Signals selected through the authoritative
  Opportunity-Review lineage.
- Artifact metadata, OCR provider confidence, or caller-supplied OCR text cannot
  bypass Human Verification or substitute for a verified signal.

## Alternatives

### A: Artifact Upload -> Server OCR -> Candidate

Rejected. It conflicts with the current boundary in which Artifact bytes are
intentionally external and no storage locator, upload admission, binary
repository, or byte-reading OCR adapter exists. Selecting A would make HYB the
byte-storage and OCR-execution owner rather than complete the existing external
reference contract.

### C: Worker -> Artifact -> Candidate

Rejected. No worker, queue, job, lease, retry, or execution-receipt lifecycle
exists in the current architecture. A worker boundary is not required to
preserve the established Review and Decision trust chain.

### D: Current Contract Cannot Decide

Rejected for this ADR. The prior audit correctly identified that the foundation
had not yet selected an authority. This ADR supplies that missing decision. The
existing external-byte boundary, provider-neutral OCR result, and explicit
Human Review boundary support B without assigning Artifact storage or OCR
execution to HYB.

## Consequences

- Production Artifact and OCR admission can be implemented without an HYB byte
  store, upload API, worker, or server-side OCR engine.
- External suppliers remain responsible for byte access, SHA-256 calculation,
  OCR execution, and truthful provider metadata.
- HYB Application remains responsible for admission validation, Candidate
  identity issuance, exact replay, conflict detection, and persistence
  orchestration.
- OCR provider provenance must survive admission even though the current
  `OCRCandidate` contract does not contain it. Production wiring is blocked
  until an existing-layer provenance/receipt contract preserves it without
  weakening Candidate immutability.
- Existing External Signal Ledger duplicate detection is not reclassified as
  OCR execution replay. Repository and SQLite changes remain outside this ADR.
- Review and Decision behavior remains unchanged: only explicit Human
  Verification can create an authoritative external signal.
- This ADR defines ownership and semantics only. It adds no API, repository,
  storage, worker, adapter, UI, SQLite schema, or runtime implementation.
