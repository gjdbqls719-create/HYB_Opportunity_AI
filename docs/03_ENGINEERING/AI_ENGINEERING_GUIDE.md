# AI ENGINEERING GUIDE

Version: 1.0
Status: Active
Owner: HYB AI Team
Last Updated: 2026-07-31

---

# Purpose

This document defines the engineering standards that every AI contributor must follow when participating in the HYB Opportunity AI project.

Unlike AI_CONSTITUTION, this document focuses on engineering execution rather than philosophy.

---

# Development Principles

Every implementation should follow the same engineering lifecycle.

Architecture

↓

Implementation

↓

Testing

↓

Documentation

↓

Review

↓

Approval

↓

Release

Skipping steps is not permitted.

---

# Implementation Rules

Every AI should:

- Prefer small implementation units.
- Keep changes easy to review.
- Minimize unrelated modifications.
- Avoid unnecessary refactoring.
- Preserve backward compatibility whenever possible.
- Explain architectural decisions clearly.

---

# Code Quality

Code should be:

- Correct
- Readable
- Testable
- Maintainable
- Extensible
- Production-ready

Short code is never preferred over understandable code.

---

# Testing Rules

Every feature should include appropriate tests.

Testing order:

1. Feature Tests
2. Integration Tests
3. Full Regression Tests

No implementation is considered complete until tests pass.

---

# Documentation Rules

Implementation and documentation progress together.

Meaningful architectural changes require documentation updates.

Every new feature should leave the project easier to understand than before.

---

# Git Principles

Development should be organized into small reviewable PRs.

Each PR should have:

- Clear objective
- Implementation summary
- Test results
- Documentation updates

Large unrelated changes should be avoided.

---

# AI Collaboration

AI contributors should:

- Report uncertainty honestly.
- Ask for clarification when necessary.
- Avoid assumptions.
- Preserve previous architectural decisions.
- Prefer evidence over intuition.

---

# Review Expectations

Before requesting review, every AI should verify:

- Architecture consistency
- Code quality
- Test completion
- Documentation updates
- Naming consistency

---

# Completion Criteria

Engineering work is complete only when:

- Code is implemented.
- Tests pass.
- Documentation is updated.
- Review is completed.
- Product Owner approves the change.

---

# Summary

Engineering quality is achieved through consistent execution rather than rapid implementation.

Every AI is responsible for protecting the long-term quality of the HYB project.