# HYB Development Principles

> Version: 1.0
> Status: Active
> Last Updated: YYYY-MM-DD

---

# 1. Purpose

This document defines the engineering principles that guide the development of the HYB Opportunity AI project.

Its purpose is to ensure that every contributor—human or AI—makes decisions using the same engineering standards.

This document serves as the highest-level engineering guideline within the project.

---

# 2. Core Values

HYB follows these core engineering values.

1. Business Value First
2. Correctness
3. Stability
4. Maintainability
5. Scalability
6. Readability
7. Performance
8. Development Speed

Every engineering decision should respect this priority unless a documented exception exists.

---

# 3. Engineering Philosophy

HYB is developed as a long-term platform.

Engineering decisions should prioritize:

- Long-term maintainability
- Stable architecture
- Incremental improvements
- Clear responsibilities
- Sustainable growth

Temporary convenience should never compromise long-term quality.

Engineering should balance both long-term platform quality
and short-term business value.

Development speed may improve through better processes,
but never by sacrificing correctness, stability,
or maintainability.

---

# 4. Development Workflow

Every feature follows the same lifecycle.

Requirement

↓

Architecture Review

↓

ADR (if required)

↓

Domain Design

↓

Implementation

↓

Testing

↓

Documentation

↓

Review

↓

Git Commit / Push

---

# 5. Architecture Principles

The project follows Domain-Driven Design.

Principles:

- Business rules belong inside Domains.
- Infrastructure depends on Domains.
- Domains do not depend on Infrastructure.
- Application coordinates Domains.
- Responsibilities should remain clearly separated.
- New abstractions require engineering justification.

---

# 6. Domain Design Principles

Each domain should:

- Have a single responsibility.
- Minimize coupling.
- Maximize cohesion.
- Expose clear interfaces.
- Be independently testable.
- Prefer immutable data where appropriate.

---

# 7. Coding Principles

Detailed coding rules are defined in:

- CODING_STANDARD.md

General principles:

- Write readable code.
- Avoid duplication.
- Prefer explicit behavior.
- Keep functions focused.
- Protect business rules.

---

# 8. Testing Principles

Detailed testing rules are defined in:

- TESTING_GUIDE.md

General principles:

- Every feature should be verified.
- Regression tests should remain green.
- External systems should be mocked.
- Bugs should become tests.

---

# 9. Documentation Principles

Documentation is treated as part of the product.

Rules:

- Code and documentation evolve together.
- Existing documents should be updated before creating new ones.
- Documentation must reflect the current implementation.
- When documentation cannot be verified, request the latest source before updating.
- Documentation should explain both "what" and "why".

---

# 10. ADR Principles

Architecture Decision Records should be created when:

- Architecture changes.
- New architectural patterns are introduced.
- Significant trade-offs are made.
- Long-term decisions require historical context.

ADR documents preserve engineering reasoning.

---

# 11. Definition of Done

A feature is complete only when:

- Implementation is finished.
- Tests pass.
- Documentation is updated.
- Code review is completed.
- Git history is clean.

---

# 12. Sprint Workflow

Every sprint follows two phases.

## Sprint Build

- Design
- Implementation
- Testing

## Sprint Review

- Documentation update
- Architecture review
- ADR review
- Quality verification
- Git preparation

---

# 13. Continuous Improvement

HYB evolves continuously.

Engineering improvements should be:

- Small
- Safe
- Measurable
- Documented

Large changes should be divided into incremental steps.

---

# 14. Engineering Decision Priority

When multiple solutions are available, use the following priority.

Business Value

↓

Correctness

↓

Stability

↓

Maintainability

↓

Scalability

↓

Readability

↓

Performance

↓

Development Speed

## Process Improvement

HYB continuously improves not only the product
but also the development process.

When a more efficient workflow is proposed,
it should be evaluated using the following criteria.

- Does it preserve correctness?
- Does it preserve stability?
- Does it improve maintainability?
- Does it reduce unnecessary work?

If the answer is yes,
the workflow should evolve accordingly.

---

# 15. References

- CODING_STANDARD.md
- TESTING_GUIDE.md

Future references:

- CODE_REVIEW_GUIDE.md
- DOCUMENTATION_GUIDE.md
- GIT_WORKFLOW.md

# 16. AI Collaboration Principles

HYB Opportunity AI is designed as a long-term collaboration between human engineers and AI assistants.

AI is expected to act as an engineering partner rather than a code generator.

The following principles define how AI should participate in the project.

---

## 16.1 Repository First

Before making implementation decisions, AI should understand the current repository.

Implementation should never ignore the existing project structure.

---

## 16.2 Documentation First

Before changing architecture or behavior, AI should review the related documentation.

If documentation is unavailable or outdated, the latest version should be requested before making changes.

AI should never guess documentation.

---

## 16.3 Architecture Awareness

AI should understand:

- Existing Domains
- Existing Workflows
- Existing ADRs
- Existing Engineering Principles

before introducing new abstractions.

---

## 16.4 Incremental Development

Large refactoring should be avoided unless clearly justified.

Small, reviewable improvements are preferred.

---

## 16.5 Explain Engineering Decisions

AI should explain:

- Why a change is necessary
- Expected benefits
- Possible trade-offs
- Potential risks

Engineering reasoning is considered part of the implementation.

---

## 16.6 Preserve Project Continuity

AI should preserve previous engineering decisions whenever possible.

New ideas should extend the existing architecture rather than replace it.

---

## 16.7 Documentation Synchronization

Documentation is part of development.

When implementation changes:

- Related documents should be reviewed.
- Related documents should be updated.
- Related references should remain valid.

---

## 16.8 Sprint Awareness

AI should understand the current Sprint before proposing work.

Recommendations should align with the current Sprint goal.

Large future ideas should be recorded instead of interrupting the current Sprint.

---

## 16.9 Engineering Partner Mindset

AI should behave as:

- Software Engineer
- Architect
- Reviewer
- Documentation Maintainer
- Quality Engineer

AI should prioritize the long-term success of the project over short-term implementation convenience.

## 검증 중심 PR 완료 절차

핵심 도메인, 경제성 계산, 운영 상태, 영속성처럼
실제 사업 결과와 데이터 무결성에 영향을 주는 변경은
단순한 테스트 통과만으로 완료하지 않는다.

기본 절차는 다음과 같다.

1. 아키텍처 및 설계 검토
2. 작은 PR 범위 확정
3. 구현
4. 기능별 테스트
5. 전체 회귀 테스트
6. 계약 감사
7. 발견된 결함 보강
8. 필요한 경우 최종 계약 감사
9. 문서 최신화
10. 커밋 및 Push

계약 감사에서는 다음을 중점적으로 확인한다.

- 도메인 불변식이 외부에서 우회되지 않는가
- Legacy와 신규 계약의 결과가 일치하는가
- 계층 및 도메인 경계가 유지되는가
- 영속화와 복원 과정에서 정보가 손실되지 않는가
- 트랜잭션 실패 시 부분 저장이 발생하지 않는가
- 외부 API, CLI, Dashboard 및 History 계약이 의도치 않게 변경되지 않는가

모든 PR에 동일한 수준의 감사를 강제하지는 않는다.
실제 금전, 운영 상태, 데이터 무결성 또는 장기 핵심 아키텍처에
영향을 주는 변경일수록 더 강한 감사 절차를 적용한다.

# Authoritative Runtime Projection

Open runtime mappings are not persistence contracts. When exact runtime
reconstruction is required, authoritative facts must use a versioned, deeply
immutable, deterministic representation that preserves value semantics and
rejects unsupported values. Reconstruction copies persisted facts; it does not
recalculate, infer, default, or backfill them.

# Pre-admission Identity Ownership

Discovery candidates and admitted Opportunities are different subjects. A
pre-admission identity must not imply lifecycle creation or admission. Identity
and Market scope are passed explicitly through owner boundaries; global context,
text-derived identity, implicit promotion, and downstream reconstruction are
prohibited. Admission binds a candidate and its exact source lineage to an
authoritative Opportunity in a separate explicit contract.

# Stable Automated Correlation

Durable automated identity must not be inferred from mutable runtime objects,
list indexes, titles, representative items, or changing prices. Server-owned
opaque IDs identify facts; deterministic fingerprints validate canonical command
intent and ordered source membership. IDs and fingerprints remain separate, and
committed command replay must use persisted results rather than repeat live
external collection.
# Candidate promotion

Candidate promotion must read Candidate identity, Discovery context, and issuance
lineage from authoritative persistence. Callers must not reconstruct discovery
reference or Market identity. Candidate and Opportunity IDs are separate opaque
identities, and admission plus their immutable binding and receipt must share one
transaction. Missing Snapshot-chain facts must remain missing rather than being
inferred or represented by placeholders.

## Snapshot subject timing

A Snapshot subject must exist when its owner produces the fact. Pre-admission
Product and Price facts use Candidate identity; post-admission Verified Economics
and EconomicsCalculation use Opportunity identity. Candidate ID must never be
used as an Opportunity ID. Cross-stage consumers must validate the immutable
promotion binding plus exact Market identity instead of inferring lineage.

## Snapshot owner publication

Collector observations may precede Candidate issuance. Candidate-scoped Product
Snapshots are published only by a collector-owned post-issuance boundary from
exact persisted observation IDs. Downstream layers must not reconstruct this
fact. Source bindings and replay receipts commit atomically with the Snapshots.

Price analysis consumes an explicitly ordered Product Snapshot cohort whose
source bindings exactly match finalized group membership. It must not select all
Candidate snapshots, choose latest rows, or reconstruct order from Product data.
Fallback multiplier and Analyzer version are explicit command provenance, and
the Price Snapshot plus owner receipt share one transaction.

Economics ownership must receive an exact Price Snapshot reference through the
Candidate/Opportunity promotion binding. Price is provenance and must never
replace persisted Verified Economics values. Calculator input comes only from
the authoritative VerifiedEconomics Snapshot plus explicit immutable parameters
and context; Snapshot and owner receipt commit atomically.
