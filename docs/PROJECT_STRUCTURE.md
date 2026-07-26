# HYB Opportunity AI Project Structure

## Code Structure

HYB 프로젝트는 역할별 책임 분리를 기본 원칙으로 합니다.

예상 구조:

app/
- Application 진입점

collectors/
- 공통 데이터 수집 인터페이스

marketplaces/
- Marketplace Adapter

engine/
- 핵심 분석 로직

storage/
- 데이터 저장

services/
- 외부 연결 및 지원 기능

tests/
- 검증 코드

docs/
- 프로젝트 지식 관리

## Relationship Between Code and Docs

Architecture:
코드 구조와 설계 원칙 관리

Engineering:
코딩 및 테스트 기준 관리

Development:
구현 과정 기록

Quality:
검증 기준 관리

Audit:
상태 점검 기록

## Principle

코드는 기능을 구현하고,
문서는 프로젝트의 지식과 방향을 보존합니다.
