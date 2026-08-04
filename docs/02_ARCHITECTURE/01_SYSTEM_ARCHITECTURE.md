# HYB System Architecture

## Pre-admission discovery identity

One finalized ProductGroup is a discovery candidate, not an admitted
Opportunity. The Discovery Orchestration boundary issues an explicit
`OpportunityCandidateIdentity` and propagates an immutable
`DiscoveryOpportunityContext` through candidate-owned processing. Validation
Admission later promotes the candidate by explicitly binding it to an
`OpportunityIdentity` and its exact Snapshot chain. Candidate issuance does not
create an Opportunity lifecycle. Market identity must be supplied explicitly and
must never be inferred from Product text, item ID, query, or category.

A discovery execution is correlated by an immutable command, collector-owned
observation envelopes, opaque finalized-group references, ordered group
membership fingerprints, and one ordered command result. Opaque IDs are separate
from content fingerprints. A committed replay must eventually load these facts
instead of calling a live marketplace again; this PR defines only the contracts,
not persistence or production wiring.

The Discovery Application layer defines separate command, finalized-group, and
execution-result repository boundaries. Command persistence owns immutable
receipt and replay/conflict semantics only; it does not execute discovery or
issue Candidate identity. Infrastructure selection remains deferred.

HYB는 Modular Pipeline Architecture를 사용한다.

흐름:
Application
↓
Marketplace Collectors
↓
Normalized Product
↓
Engine Orchestrator
↓
Analysis Engine
↓
Storage / Presentation

원칙:
Marketplace는 수집,
Engine은 분석,
Service는 연결,
UI는 표현만 담당한다.
