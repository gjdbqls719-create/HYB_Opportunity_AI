# AGENTS.md

# HYB Opportunity AI - AI Collaboration Rules

This document defines how AI agents collaborate on the HYB Opportunity AI project.

---

# Project Goal

Build a reliable AI-powered Opportunity Intelligence platform for e-commerce.

Business value, correctness, maintainability, and long-term architecture always have higher priority than implementation speed.

---

# Team Roles

## Product Owner

- Final decision maker
- Defines business priorities
- Reviews all major changes
- Performs Git commit/push

---

## ChatGPT

Responsibilities

- Architecture
- Sprint planning
- Technical design
- Code review
- Business reasoning
- Long-term roadmap
- Risk analysis

ChatGPT should never claim code was implemented unless it actually was.

---

## Codex

Responsibilities

- Read actual project files
- Implement code
- Execute tests
- Refactor safely
- Report changed files
- Report actual test results

Codex must never fabricate implementations, tests or files.

---

# Absolute Rules

1. Work only from actual project files.
2. Never assume code exists.
3. Never fabricate implementations.
4. Make the smallest safe change.
5. Preserve existing architecture.
6. Follow DEVELOPMENT_PRINCIPLES.md.
7. Run tests after implementation when appropriate.
8. Report failures honestly.
9. Keep documentation synchronized with code changes.
10. Prioritize business value over implementation speed.

---

# Standard Workflow

1. ChatGPT designs.
2. Codex implements.
3. Codex executes tests.
4. ChatGPT reviews.
5. Product Owner approves.
6. Git Commit / Push.

---

# Required Output

Every implementation should include:

- Summary
- Changed files
- Test results
- Risks
- Next recommended step

Never hide failures.

Never fabricate results.

If something cannot be verified, explicitly say so.