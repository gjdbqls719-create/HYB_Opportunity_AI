# ADR-0029: Persisted Discovery Execution Entry

## Status

Accepted (PR36-D.1)

## Context

The existing production discovery runtime can calculate transient
`DiscoveryResult` values, and the durable Discovery boundary can persist or
replay an immutable `DiscoveryCommand`. Before this change no Application owner
ensured that command identity was committed before the external runtime began,
and the existing minimal Discovery port forwarded only query and limit.

`DiscoveryCommandParameters` contains nineteen execution-affecting values. A
production entry must therefore execute from the committed command rather than
reconstructing a smaller request that silently falls back to Engine defaults.

## Decision

Add an Application-level persisted discovery execution entry with one ordered
responsibility:

```text
DiscoveryCommand
    -> PersistDiscoveryCommand
    -> Production Discovery Runtime
    -> tuple[DiscoveryResult, ...]
```

The runtime receives the authoritative command returned by the persistence
boundary, including exact replay. Its Infrastructure adapter forwards every
execution-affecting command parameter to the existing Engine orchestrator and
reuses the existing `OpportunityResult` to `DiscoveryResult` mapper.

Command persistence failure stops execution. Runtime failure does not roll back
the already committed command. Repository transactions, receipt replay, Engine
calculations, Domain contracts, and the existing `DiscoverOpportunitiesUseCase`
and `DiscoverOpportunitiesWorkflow` semantics remain unchanged.

## Consequences

- Production execution has an explicit Application owner.
- Persisted command intent and actual Engine arguments remain aligned.
- Exact command replay uses the committed command as runtime input.
- A failed external runtime leaves a durable command that can be retried.
- Observation, group, execution-result, candidate, promotion, and Snapshot
  orchestration remain outside PR36-D.1.
- CLI and FastAPI composition remain unchanged until a later wiring boundary.
