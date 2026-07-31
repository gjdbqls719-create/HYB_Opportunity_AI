# AI OPERATING ARCHITECTURE

Version: 1.0
Status: Active
Owner: HYB AI Team
Last Updated: 2026-07-31

---

# Purpose

This document defines how Artificial Intelligence participates in the HYB Opportunity AI project.

It describes responsibilities, document relationships, development flow, and collaboration rules between human contributors and AI systems.

This document focuses on architecture.

Operational details belong to AGENTS.md.

---

# Architecture Overview

The AI Operating System consists of four layers.

```

Project Vision
↓
Project Governance
↓
AI Governance
↓
AI Execution

```

Each layer has a different responsibility.

---

# Layer 1 — Project Vision

Purpose

Define why the project exists.

Documents

- PROJECT_FOUNDATION
- PROJECT_CONSTITUTION
- HYB_DNA
- PROJECT_NORTH_STAR
- VISION_STATEMENT

These documents rarely change.

---

# Layer 2 — Project Governance

Purpose

Define how the project should be managed.

Documents

- DECISION_FRAMEWORK
- DEVELOPMENT_PRINCIPLES
- DOCUMENT_POLICY
- CHANGE_MANAGEMENT

These documents define engineering policies.

---

# Layer 3 — AI Governance

Purpose

Define how AI behaves inside the project.

Documents

- AI_PARTNER
- AI_CONSTITUTION
- AI_ENGINEERING_GUIDE
- AGENTS.md

These documents define AI responsibilities.

---

# Layer 4 — AI Execution

Purpose

Describe how work is performed.

Documents

- AI_WORKFLOW
- REVIEW_CHECKLIST
- TESTING_GUIDE
- PR_TEMPLATE

These documents may evolve frequently.

---

# AI Lifecycle

Every implementation follows the same lifecycle.

Idea

↓

Architecture Review

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

No step should be skipped.

---

# Responsibility Model

Product Owner

↓

Architecture

↓

Implementation

↓

Review

↓

Release

Each responsibility has exactly one owner.

AI may assist every stage.

Final decisions always belong to the Product Owner.

---

# Document Dependency

PROJECT_CONSTITUTION

↓

AI_CONSTITUTION

↓

AI_ENGINEERING_GUIDE

↓

AGENTS

↓

AI_WORKFLOW

↓

Implementation

This dependency should remain stable.

---

# Design Principles

The AI Operating System follows these principles.

Single Responsibility

Documentation First

Evidence-Based Decisions

Long-Term Maintainability

Architecture Before Implementation

Quality Before Speed

---

# Future Expansion

The architecture is AI-independent.

Additional AI systems may join without changing the overall structure.

Examples

- ChatGPT
- Codex
- Claude
- Gemini
- Cursor
- Copilot

All must follow the same governance.

---

# Summary

The AI Operating System provides one consistent development model for every AI participating in the HYB project.

Its goal is not automation.

Its goal is sustainable collaboration.