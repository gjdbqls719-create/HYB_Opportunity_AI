# HYB Opportunity AI Project Context

## 프로젝트 개요

프로젝트명:
HYB Opportunity AI

목표:

온라인 마켓플레이스의 상품 데이터를 수집·정규화·비교하고,
동일하거나 유사한 상품을 매칭한 뒤 가격·시장 신호·수익성·위험 요소를 분석하여
AI가 높은 가능성의 상품 기회를 발견하고 설명 가능한 추천을 제공하는 플랫폼 구축.

HYB는 단순 검색 페이지나 가격 비교 사이트가 아니라,
상품 기회의 신뢰성을 판단하는 Decision Engine을 핵심 가치로 한다.

---

## Product Definition

HYB는 Multi-market Product Intelligence System이다.

핵심 기능:

- 상품 데이터 수집
- 상품 정규화
- 동일 상품 매칭
- 가격 분석
- 시장 신호 분석
- Opportunity 품질 계산
- 추천 생성

---

## 대상 시장

초기 목표:

- 미국
- 한국

예정 Marketplace:

- eBay
- Amazon
- Walmart
- Coupang
- AliExpress
- Temu
- 공통 Collector Interface 기반 추가 Marketplace

---

## 핵심 Processing Pipeline

Marketplace Collectors
↓
Normalized Product Model
↓
Product Matching
↓
Price Intelligence
↓
Trend / Confidence Analysis
↓
Opportunity Scoring
↓
Recommendation Engine
↓
Storage / API / Dashboard / Alerts

---

## 현재 아키텍처 원칙

- Marketplace별 코드는 수집과 변환 담당
- Engine은 Marketplace 구조를 몰라야 함
- 핵심 계산은 설명 가능하고 테스트 가능해야 함
- Marketplace 오류는 독립적으로 처리
- Web UI는 Domain 설계를 주도하지 않음

---

## 개발 철학

HYB의 핵심은 검색 기능이 아니라,
상품 기회가 실제로 가치 있는지 판단하는 시스템이다.

