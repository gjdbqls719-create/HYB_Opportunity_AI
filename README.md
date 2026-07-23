# HYB Opportunity AI

> **AI-Powered Opportunity Discovery Platform**
>
> **Discover. Analyze. Evaluate. Automate.**

---

## Vision

HYB Opportunity AI는 온라인 마켓플레이스의 상품 데이터를 수집하고,
AI를 활용하여 사업성이 높은 Opportunity를 발견하는 플랫폼입니다.

프로젝트의 목표는 단순한 가격 비교가 아니라 **지속 가능한 Opportunity Discovery System**을 구축하는 것입니다.

---

## Current Status

| Area | Status |
|------|:------:|
| Foundation | ✅ 100% |
| Documentation | 🟡 In Progress |
| Core Engine | 🟡 In Progress |
| Marketplace Integration | 🟡 In Progress |
| Automation Pipeline | 🔵 Planned |

---

# Core Features

- Opportunity Discovery
- Product Matching
- Price Analysis
- Marketplace Integration
- AI Evaluation
- Automation Pipeline

---

# High-Level Architecture

```text
Collectors
      │
      ▼
Marketplaces
      │
      ▼
Engine
      │
      ▼
Storage / Database
      │
      ▼
Presentation
```

세부 설계는 `docs/TECHNICAL/` 문서를 참고하세요.

---

# Documentation

| Category | Description |
|----------|-------------|
| FOUNDATION | 프로젝트의 철학과 운영 원칙 |
| BUSINESS | 사업 전략 및 방향 |
| TECHNICAL | 시스템 설계와 기술 문서 |
| DEVLOG | 개발 기록 |
| HANDOVER | 프로젝트 인수인계 |
| archive | 이전 문서 보관 |

읽기 권장 순서

1. FOUNDATION
2. BUSINESS
3. TECHNICAL
4. DEVLOG
5. HANDOVER

---

# Repository Structure

```text
app/
ai/
collectors/
config/
database/
docs/
engine/
marketplaces/
presentation/
services/
storage/
tests/
```

---

# Development Workflow

```text
Idea
 ↓
Design
 ↓
Implement
 ↓
Test
 ↓
Document
 ↓
Commit
 ↓
Review
```

---

# Quick Start

```bash
git clone <repository>

python -m venv .venv

pip install -r requirements.txt

python app/main.py
```

> 실제 실행 파일이 다를 경우 프로젝트 구조에 맞게 수정하세요.

---

# Roadmap

## Completed

- Foundation 구축
- 프로젝트 문서 체계 재설계
- Opportunity Engine 기반 구조

## In Progress

- Marketplace 확장
- Engine 고도화
- Documentation Refactoring

## Planned

- Dashboard
- Production 환경
- AI Ranking 개선
- Automation Pipeline

---

# Project Principles

HYB는 다음 원칙을 기반으로 개발됩니다.

- Business First
- Opportunity First
- Explainable AI
- Long-Term Maintainability
- Documentation as an Asset

자세한 내용은 `docs/FOUNDATION/`에서 확인할 수 있습니다.

---

# License

Internal Project (HYB Opportunity AI)

Copyright © HYB
