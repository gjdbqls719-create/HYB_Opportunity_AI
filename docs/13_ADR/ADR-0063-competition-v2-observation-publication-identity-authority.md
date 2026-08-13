# ADR-0063: Competition v2 Observation and Publication Identity Authority

## Status

Accepted and implemented by the Competition v2 observation identity correction.

## Context

ADR-0061 gives one immutable `cohort_id` ownership of a bounded Competition v2
manifest. The implementation consequently used that ID as the publication
lookup and receipt target. ADR-0062 requires Demand v2 to pin both the admitted
Competition publication and its exact cohort. Overloading `cohort_id` would
retroactively broaden an established authority.

## Decision

Competition v2 observation/publication identity and cohort identity are
distinct. A new publication receives a server-issued opaque UUID identity. A
caller never supplies it. Exactly one observation maps to exactly one cohort,
and exactly one cohort maps to exactly one observation. One-to-many mappings
are prohibited under this contract.

The immutable identity contract exposes `observation_id`, `identity_kind`, and
`identity_version`. Issued identities use kind `issued` and version
`competition-observation-identity-v1`.

## Legacy Compatibility Identity

Existing rows are not backfilled. A legacy repository derives an explicitly
non-UUID compatibility identity from canonical JSON containing only:

- namespace `competition-v2-legacy-observation-identity`;
- version `competition-observation-legacy-compatibility-v1`;
- existing `cohort_id`;
- existing cohort authority fingerprint.

The SHA-256 digest is prefixed with
`legacy-competition-v2-observation-v1:`. This identity has kind
`legacy_compatibility`. Derivation uses no clock, randomness, write, API, or
provider access.

## Persistence and Schema Compatibility

Current schemas add append-only `competition_v2_observation_identities` with a
primary observation ID, unique cohort ID, kind, version, issuance time, and a
foreign key to the cohort. Publication, identity, and receipt are committed in
one transaction.

Repositories recognize exact legacy and current schema variants. Opening a
legacy schema performs no migration or table creation. New Competition writes
against legacy schema fail closed pending an explicitly approved upgrade.

## Replay and Fingerprints

Receipts remain command-to-cohort records. Replay resolves the receipt, cohort,
then issued or compatibility observation identity. Existing receipts are not
rewritten. Observation identity does not participate in the existing command
fingerprint or cohort authority fingerprint. Replay and convergent aliases do
not issue another observation ID.

## API and Demand Boundary

The Competition v2 request remains unchanged. Responses add the observation
ID, identity kind, and identity version as server-owned authority. Demand v2
may later pin the Competition observation ID and cohort ID together with the
existing fingerprint, versions, and artifact provenance. This ADR does not
implement Demand admission.

## Historical Safety

The verified genuine Competition cohort and its 17-card manifest, assessment,
receipt, fingerprints, and timestamps remain unchanged. Compatibility identity
is reconstructed without opening a migration or creating a second publication.
