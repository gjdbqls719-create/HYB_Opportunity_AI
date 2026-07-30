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
- Context Packs are refreshed when project state changes.
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

---

# 15. References

- CODING_STANDARD.md
- TESTING_GUIDE.md

Future references:

- CODE_REVIEW_GUIDE.md
- DOCUMENTATION_GUIDE.md
- GIT_WORKFLOW.md
