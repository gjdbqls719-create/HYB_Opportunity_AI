# ADR-0067: Persisted Discovery Screening Authority

## Status

Accepted

## Implementation Status

PR2 implements the explicit finalized-Group correlation prerequisite. The
Application grouping checkpoint returns its ordered, already-issued
`finalized_group_id` values to the Engine before analysis. Each
`OpportunityResult` preserves its assigned ID through the existing stable sort,
the runtime maps it into `DiscoveryResult`, and both runtime and Application
boundaries reject missing, duplicate, unknown, lost, or count-mismatched
correlations. The ordered checkpoint tuple remains the explicit grouping
ordinal source; no post-sort positional inference is used.

This PR2 status does not implement screening evaluation/publication
persistence, change ranking keys or stable-tie behavior, or change any
Candidate, O1/O2, Capital, API, schema, or replay authority. PR3 is next.

## Context

The production Discovery path persists the command, collected observations,
finalized Groups, and one successful `DiscoveryExecutionResult`. Economics,
recommendation, and ranking are calculated after Group finalization, but the
ranked `OpportunityResult`/`DiscoveryResult` values remain transient. A
completed replay therefore proves exact Discovery lineage without restoring
the screening facts that caused one Group to be reviewed before another.

Repository Deep Audit v2 and the follow-up Architecture Design identified this
as Persisted Discovery Screening F2. The existing Discovery boundary already
owns collection, grouping, transient screening, and completion. Persisting that
screening does not require a new bounded Domain, and it must not acquire the
authority of later Candidate, Opportunity, Capital, or execution workflows.

## Problem

HYB needs an immutable, explainable screening record for Founder review and
runtime-free completed replay. That record must preserve exact policy,
provenance, reasons, evaluation time, ranking time, and integrity lineage.

The current runtime also has a blocking correlation gap. It emits ordered
`GroupingCorrelation` values that safely map collection positions to finalized
Groups, and it later emits a separately sorted list of transient
`OpportunityResult` values. No explicit key safely proves which sorted result
belongs to which `FinalizedProductGroup`. Display or marketplace fields cannot
repair that missing relationship.

## Decision

Adopt the following existing-Discovery-owned chain:

```text
DiscoveryCommand
  -> CollectedProductObservation[]
  -> FinalizedProductGroup[]
  -> DiscoveryScreeningEvaluationSnapshot[]
  -> DiscoveryScreeningRankingPublication
  -> DiscoveryExecutionResult v2
       (screening_ranking_publication_id reference only)
```

`DiscoveryScreeningEvaluation` is the screening concept;
`DiscoveryScreeningEvaluationSnapshot` is its immutable persisted fact. Each
successful completed v2 execution references exactly one immutable ranking
publication. `DiscoveryExecutionResult v2` does not embed evaluation, ranking,
reason, metric, policy, or provenance payloads. It retains only the exact
`screening_ranking_publication_id` in addition to its completion lineage.

## Ownership

The existing Discovery boundary owns screening evaluation and ranking
publication. No `OpportunityEvaluation` owner, general Opportunity Engine, or
new Screening bounded Domain is introduced. Discovery may expose its immutable
facts to later consumers, but those consumers do not redefine historical
screening meaning.

## Evaluation and Ranking Separation

One evaluation snapshot concerns one exact finalized Group under one exact
screening policy and input set. It preserves at least its evaluation ID,
execution and finalized-Group lineage, `evaluated_at`, structured reasons,
screening recommendation/review-priority facts, policy manifest, input and
used-evidence manifests, provenance, and integrity fingerprints.

An evaluation snapshot never stores rank. Evaluation history remains valid
even when a later publication orders the same eligible evaluations differently
under a different ranking policy.

One ranking publication freezes a ranking policy, `ranking_created_at`, its
publication fingerprint, and ordered entries. Every ordered entry fixes:

- `rank`;
- `finalized_group_id`;
- `screening_evaluation_id`; and
- the referenced evaluation fingerprint.

Repositories must verify same-execution lineage, unique Group/evaluation/rank
membership, contiguous ranks beginning at one, and exact evaluation
fingerprints. Evaluations whose required ranking inputs are `UNKNOWN` or
`UNSUPPORTED` remain auditable but are not assigned fabricated numeric keys;
they may remain explicitly unranked under the versioned policy.

## Explicit Group Correlation Requirement

Before an evaluation can be persisted, the runtime must provide an
execution-local explicit group correlation identity, or an equivalent
deterministic contract, that survives analysis and sorting and resolves to one
exact `FinalizedProductGroup`. PR2 must establish and test this relationship as
a prerequisite to evaluation persistence.

The existing collection-position `GroupingCorrelation` safely constructs
Groups, but it does not by itself bind a later sorted result to a Group.
Grouping ordinal may be an explicit deterministic tie-break; it is not a
substitute for result-to-Group identity.

The implementation must never correlate a transient result to a finalized
Group by:

- title matching;
- URL matching;
- inferred marketplace item ID matching; or
- assuming sorted-result position equals grouping position.

## Ranking Policy v1

Repository inspection confirms that current production
`engine.orchestrator.find_best_opportunities` sorts successful results by this
descending tuple:

1. post-safety-gate recommendation object score;
2. `final_opportunity_score`;
3. per-unit `analysis["net_profit"]`.

The production safety gate can downgrade the effective grade while preserving
the numeric recommendation score. The sort therefore uses the effective
recommendation object's score, not a grade ordering. The current code has a
defensive `0` fallback when the recommendation object is absent, although the
successful production loop generates a recommendation before appending each
result. Persisted screening must not turn an actually unknown or unsupported
score into zero; such an evaluation is explicitly unranked unless a future
versioned policy defines another non-fabricating rule.

Python's current stable sort implicitly preserves pre-sort Product Group order
when all three values tie. Ranking Policy v1 makes that behavior explicit and
deterministic:

1. effective recommendation score descending;
2. final opportunity score descending;
3. per-unit net profit descending;
4. explicit grouping ordinal ascending as the final tie-break.

Making the fourth key explicit preserves current successful exact-tie behavior
while removing reliance on incidental stable-sort input order. PR2 must first
bind that ordinal and each analyzed result to the exact finalized Group, and
PR3 must version the complete descriptor and numeric/availability semantics.

`app/domain/discovery/ranking.py::RankingEngine` is a different legacy/domain
policy: it orders normalized `DiscoveryResult` values by opportunity score,
matched count, cost, title, and identity. It is not the production screening
authority and must not be used to describe or reconstruct Ranking Policy v1.

## Provenance Semantics

The screening contract distinguishes at least:

- `OBSERVED`: a source-produced fact with its source, reference, and observation
  time;
- `CALCULATED`: a deterministic derived value whose exact input references and
  input provenance are preserved;
- `ESTIMATED`: a model, heuristic, or bounded estimate rather than direct
  observation;
- `POLICY_ASSUMPTION`: an explicit policy/command value used in calculation
  without an independent observation;
- `UNKNOWN`: the fact is not known or was not obtained; and
- `UNSUPPORTED`: the current contract cannot represent or consume the fact's
  semantics.

`UNKNOWN` and `UNSUPPORTED` carry no numeric value. Missing evidence is never
converted to zero. `CALCULATED` does not erase or upgrade the provenance of its
inputs. In particular, fixed monthly sales, competitor count, and similar
screening inputs are `POLICY_ASSUMPTION` unless an independent observation is
actually supplied and consumed.

NAVER/ItemScout total search volume may include overseas searches. It cannot be
recorded or consumed as Korea-only demand evidence. A truthful mixed-geography
observation also does not become Korea-only through a calculated value.

The policy manifest records the exact policy descriptors used. The input
manifest records exact inputs made available to the evaluation. The
used-evidence manifest includes a command source or policy reference only when
the screening calculation actually consumed it. Merely carrying a reference
on `DiscoveryCommand` does not make it used evidence.

These are screening semantics, not a forced universal enum. Existing Economics
`EvidenceStatus`, Market `MarketEvidenceStatus`, and their historical meanings
remain separate. Future adapters map exact source semantics without merging or
reinterpreting those enums.

## Screening-Only Authority Scope

Persisted Screening is only:

- Discovery screening evidence; and
- Founder review-priority evidence.

Founder-facing primary terminology uses `DiscoveryScreeningEvaluation`,
`ScreeningRecommendation`, `ReviewPriorityRank`, and High/Medium/Low Review
Priority. Raw Engine `BUY` and `STRONG_BUY` values may be retained as exact
historical/audit detail, but they are not the primary Founder-facing authority
label and do not authorize buying.

Machine rank number one creates no Candidate automatically. The Founder must be
able to select another ranked candidate or an explicitly allowed unranked
candidate. Any selection proceeds through the existing separate Candidate
issuance contract and its exact lineage checks.

## Candidate, O1, and O2 Separation

A screening evaluation or ranking publication does not mean:

- Candidate issuance;
- O1 promotion/admission; or
- O2 target admission.

Those workflows retain their own explicit identities, source validation,
commands, persistence, replay, and Founder choices. Screening publication IDs
may become lineage references only through separately approved consumer
contracts.

## Capital Authority Separation

A screening recommendation, review priority, or machine rank does not mean:

- Capital Readiness;
- Capital Gate `PASS`;
- Founder Capital Approval;
- Real-Money Execution Intent; or
- `BUY` authorization or permission to spend.

The existing Capital and real-money execution authorities remain the only
owners of those meanings. Screening cannot bypass or synthesize them.

## Persistence and Replay

Future implementation must provide immutable evaluation history, immutable
ranking-publication history, integrity fingerprints, append-only storage, and
exact historical policy/provenance restoration.

A completed v2 replay reconstructs the committed execution result, referenced
ranking publication, ordered entries, and evaluation snapshots from persisted
facts. It must not call the Engine, a live marketplace, current policy, an
identity supplier, or the current clock to recalculate historical screening.
Corruption, a missing referenced fact, fingerprint mismatch, or cross-execution
lineage mismatch fails closed.

## Atomic Completion Boundary

For one successful v2 execution, these facts form one logical completion
bundle:

- all screening evaluation snapshots;
- the ranking publication; and
- `DiscoveryExecutionResult v2`.

The future SQLite implementation uses a narrow completion repository that
commits this bundle through one connection and one transaction. Evaluation or
publication rows must not remain committed without the corresponding v2
completion result, and the v2 result must not reference a partially committed
publication. Already persisted command, observation, and finalized-Group
checkpoints remain inputs to this completion transaction.

This decision does not introduce a generic workflow engine, durable phase
machine, queue, or distributed transaction.

## Legacy v1 Policy

Existing `DiscoveryExecutionResult` v1 rows are not backfilled, recomputed, or
interpreted through current screening policy. Reads expose an explicit
`SCREENING_NOT_RECORDED_LEGACY` state, or an equivalently unambiguous versioned
contract, rather than an empty ranking, inferred result, or recalculated
screening payload.

## F1 Recovery Relationship

F2 screening persistence may be implemented first for successful completed
executions. It does not explain failed or incomplete attempt history, resume
position, retry ownership, or failure recovery.

F1 durable attempt/recovery remains a separate authority/ADR/PR track. F1 and
F2 must not be combined into one large implementation PR. Adding the F2 atomic
successful-completion repository does not claim that earlier checkpoints or
failed attempts are one atomic workflow.

## Shadow Future Compatibility

Screening authority does not know about Shadow Validation. It nevertheless
provides stable lineage that a future consumer can reference exactly:

- ranking publication ID;
- screening evaluation ID;
- integrity fingerprints;
- structured reasons;
- policy manifest;
- input and used-evidence manifests; and
- `evaluated_at` and `ranking_created_at`.

Shadow-specific state, checkpoint, outcome, and calibration fields do not
belong in screening contracts. A future Shadow authority may reference exact
historical screening IDs without writing back into or reinterpreting them.

## Consequences

- Founder review can use durable, explainable priority evidence without
  granting downstream authority.
- Evaluation history is reusable independently of a particular ranking
  publication.
- Runtime-free v2 replay restores exact historical screening and provenance.
- Append-only fingerprints and one SQLite completion transaction make partial
  completion and silent reinterpretation detectable.
- The explicit result-to-Group correlation contract is a mandatory PR2
  prerequisite, not an implementation detail deferred to persistence.
- New tables/contracts and versioned completion behavior are required in later
  PRs, while legacy v1 history remains unchanged.
- F1 recovery and Shadow Validation remain independently reviewable work.

## Rejected Alternatives

### Full screening payload inside `DiscoveryExecutionResult`

Rejected because it couples completion, evaluation, ranking, and provenance
evolution and duplicates immutable facts inside one result payload.

### One giant nested publication

Rejected because evaluations cannot be independently referenced or integrity
checked and any ranking change would duplicate the whole evaluation history.

### `OpportunityEvaluation` ownership

Rejected because screening occurs before Candidate/O1/O2 authority and is
already owned by Discovery. Opportunity ownership would imply a lifecycle stage
that does not yet exist.

### Opaque `OpportunityResult` JSON or pickle

Rejected because runtime objects are not stable versioned Domain contracts,
hide evidence semantics, and cannot guarantee safe cross-version replay.

### Inferred title, URL, or marketplace-item matching

Rejected because display/source attributes are not a safe one-to-one
result-to-Group correlation key. Sorted and grouping positions are also not
assumed equal.

### Automatic Candidate issuance

Rejected because screening rank is review evidence, not Founder selection or
Candidate authority.

### F1 and F2 as one giant implementation PR

Rejected because successful completion persistence and failed-attempt recovery
have different facts, atomicity, failure semantics, and review risks.

## Implementation Sequence

1. **PR2 — Explicit finalized-Group correlation contract.** Bind each analyzed
   result to one exact Group and make grouping ordinal explicit without inferred
   matching.
2. **PR3 — Versioned screening/ranking policy descriptors and structured reason
   contract.** Freeze Ranking Policy v1, availability semantics, labels, and
   reason vocabulary.
3. **PR4 — Immutable evaluation/ranking/provenance Domain contracts.** Add
   fingerprints, manifests, lineage invariants, and legacy state contracts.
4. **PR5 — SQLite composite completion persistence.** Add one-transaction
   atomicity plus replay, corruption, and concurrency coverage.
5. **PR6 — Production completion integration and runtime-free v2 replay.** Wire
   the successful execution boundary without recalculation.
6. **PR7 — Founder screening read API and Top-N UI.** Expose review-priority
   terminology and explicit selection without automatic Candidate issuance.

After PR7, reassess readiness to start the Shadow Validation MVP. Implement F1
Recovery on its separate track.

## Non-goals

- PR2 or any production implementation in this ADR PR;
- Python production-code, SQLite schema, API, or template changes;
- Candidate issuance, O1 promotion, O2 admission, or automatic selection;
- changes to Capital Readiness, Capital Gate, Founder Approval, execution
  intent, Purchase, or spending authority;
- a universal evidence enum or reinterpretation of Economics/Market evidence;
- F1 failed-attempt persistence or resumable workflow behavior;
- Shadow state, checkpoint, outcome, or calibration design;
- legacy v1 backfill, recomputation, or migration; and
- a generic workflow, queue, or orchestration framework.
