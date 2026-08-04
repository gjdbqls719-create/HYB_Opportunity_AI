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
execution-result repository boundaries. SQLite implements only the command
boundary: one immutable command and its receipt commit atomically with
`BEGIN IMMEDIATE`, and durable replay returns that exact pair after restart.
Command persistence does not execute discovery or issue Candidate identity.
Collected observations and finalized groups are also stored as immutable,
execution-bound SQLite facts. Observation identity is independent from source
listing identity, so a listing may be observed repeatedly. Group membership is
an ordered normalized relation and one observation may participate in multiple
groups. An immutable Discovery execution result now records successful
completion, including ordered finalized Group IDs or an explicit successful
zero-result. Result persistence is command/execution-bound and does not generate
completion time, execute discovery, or issue Candidates.

Candidate issuance is a read-only Application boundary over the persisted
command, completed result, finalized Group, and representative observation. The
caller supplies an explicit discovery reference and listing or canonical-product
Market identity; neither value is derived from Group ID, Product text, query, or
fingerprint. After lineage and source identity validation, an injected opaque ID
generator creates `OpportunityCandidateIdentity` and the boundary returns an
immutable `DiscoveryOpportunityContext`. This does not create an Opportunity,
write a Candidate, or claim durable replay. Until an issuance receipt exists,
repeating the request may generate another Candidate identity.

Candidate issuance persistence closes that replay gap. One Candidate and Context
exist per `(Discovery command ID, finalized Group ID)`, while every immutable
issuance command owns one receipt; multiple alias receipts may reference the same
Candidate. Initial issuance atomically stores Candidate, Context, and receipt.
An equivalent later command stores only an alias receipt and returns the existing
Candidate without regenerating its ID or issuance time. This durable state is
still pre-admission and creates no Opportunity lifecycle.

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
