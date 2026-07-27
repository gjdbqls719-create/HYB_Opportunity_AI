# HYB Architecture Index

## Core Architecture

- [System Architecture](01_SYSTEM_ARCHITECTURE.md)
- [System Flow](02_SYSTEM_FLOW.md)
- [Module Reference](03_MODULE_REFERENCE.md)
- [Database Schema](04_DATABASE_SCHEMA.md)
- [API Spec](05_API_SPEC.md)
- [AI Engine Spec](06_AI_ENGINE_SPEC.md)
- [Marketplace Interface](07_MARKETPLACE_INTERFACE.md)

## Architecture Alignment

- [Architecture Alignment Report v1](ARCHITECTURE_ALIGNMENT_V1.md)

## Opportunity Discovery

- [Discovery Domain](OPPORTUNITY_DISCOVERY_DOMAIN.md)
- [Discovery Application Layer](OPPORTUNITY_DISCOVERY_APPLICATION.md)
- [Discovery Workflow](OPPORTUNITY_DISCOVERY_WORKFLOW.md)

## Related Standards

- Coding Standard과 Testing Guide는 `docs/03_ENGINEERING`에서 관리한다.
- 주요 구조 결정은 `docs/13_ADR`에서 관리한다.
- 배포 및 운영 문서는 `docs/05_OPERATIONS`에서 관리한다.
- 보안 정책은 `docs/06_SECURITY`에서 독립 관리한다.

## Sprint 5 Opportunity Intelligence

- [Opportunity Intelligence Integration Contract v1](OPPORTUNITY_INTELLIGENCE_INTEGRATION_CONTRACT.md)
  - Discovery와 신규 Score/Decision Engine 사이의 Source Map, 결측 정책,
    공존 정책 및 Application/Adapter 경계를 정의한다.
- [ADR-0001 — Opportunity Intelligence Integration Boundary](../13_ADR/ADR-0001-opportunity-intelligence-integration-boundary.md)
  - 불완전 Factor에 임의 기본값을 사용하지 않고 `unavailable` 상태로 처리하는
    결정을 기록한다.
