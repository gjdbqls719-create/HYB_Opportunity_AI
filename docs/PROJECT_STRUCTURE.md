# PROJECT STRUCTURE

> HYB Opportunity AI 프로젝트 구조 및 디렉터리 설계 문서

Version: v1.0
Status: Active
Owner: Product Owner + AI Partner
Category: Documentation
Priority: High
Last Updated: 2026-07-26

---

# 📖 문서 목적

이 문서는 HYB Opportunity AI 프로젝트의 전체 구조를 설명합니다.

프로젝트에 존재하는 모든 디렉터리와 파일은 명확한 역할과 책임을 가져야 하며,
새로운 구조를 추가하거나 변경할 때에도 이 문서를 기준으로 관리합니다.

---

# 🎯 설계 목표

HYB의 프로젝트 구조는 다음 목표를 기반으로 설계되었습니다.

- 높은 가독성
- 명확한 책임 분리
- 쉬운 유지보수
- 확장 가능한 구조
- 장기 프로젝트에 적합한 설계

---

# 📂 프로젝트 최상위 구조

```
HYB_Opportunity_AI/

├── ai/
├── app/
├── collectors/
├── config/
├── database/
├── docs/
├── engine/
├── scripts/
├── tests/
├── .github/
├── .venv/
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

# 📁 디렉터리 설명

## ai/

AI 관련 기능을 관리합니다.

예시

- AI 분석
- AI 추천
- AI 전략
- AI 모델 관리

---

## app/

프로젝트에서 사용하는 핵심 데이터 모델과 공통 객체를 관리합니다.

예시

- Product
- Marketplace
- Opportunity
- Result

---

## collectors/

각 마켓플레이스의 데이터 수집 기능을 담당합니다.

예시

- eBay
- Amazon
- Walmart
- 기타 Marketplace

---

## config/

프로젝트 설정을 관리합니다.

예시

- 환경 변수
- API 설정
- 실행 옵션
- 로그 설정

---

## database/

데이터 저장소 관련 기능을 관리합니다.

예시

- SQLite
- Repository
- History
- Cache

---

## docs/

프로젝트의 모든 공식 문서를 관리합니다.

문서는 코드와 동일한 수준으로 중요하게 관리합니다.

---

## engine/

프로젝트의 핵심 비즈니스 로직입니다.

예시

- Opportunity Engine
- Product Matching
- Price Intelligence
- Recommendation
- Confidence Score

---

## scripts/

반복적으로 사용하는 실행 스크립트를 관리합니다.

예시

- 초기화
- 데이터 마이그레이션
- 테스트 실행
- 개발 보조 도구

---

## tests/

모든 테스트 코드를 관리합니다.

테스트 구조는 실제 프로젝트 구조와 최대한 동일하게 유지합니다.

---

# 📌 구조 설계 원칙

프로젝트는 다음 원칙을 따릅니다.

## 하나의 책임

하나의 디렉터리는 하나의 역할만 담당합니다.

---

## 낮은 결합도

각 모듈은 서로 최소한으로 의존해야 합니다.

---

## 높은 응집도

관련 기능은 하나의 위치에서 관리합니다.

---

## 예측 가능한 구조

새로운 개발자가 폴더 이름만 보고도 역할을 이해할 수 있어야 합니다.

---

# 🔄 의존 관계

프로젝트는 다음과 같은 흐름을 기본으로 합니다.

```
Collectors
      │
      ▼
Engine
      │
      ▼
Database
      │
      ▼
AI
```

공통 데이터 모델은 `app/`에서 관리하며, 여러 모듈이 함께 사용합니다.

---

# 📁 docs 구조

```
docs/

foundation/
engineering/
architecture/
development/
operations/
product/
quality/
business/
audit/
templates/
archive/
```

각 폴더는 독립적인 책임을 가지며, 문서는 해당 주제에 맞는 위치에만 작성합니다.

---

# ➕ 새로운 디렉터리 추가 규칙

새로운 디렉터리를 만들기 전에는 다음을 확인합니다.

- 기존 디렉터리로 해결 가능한가?
- 책임이 명확하게 분리되는가?
- 다른 개발자가 이해하기 쉬운 이름인가?
- 장기적으로 유지할 가치가 있는가?

모든 질문에 **예**라고 답할 수 있을 때만 새로운 디렉터리를 생성합니다.

---

# 📋 유지보수 원칙

프로젝트 구조는 가능한 한 자주 변경하지 않습니다.

구조 변경은 다음 경우에만 진행합니다.

- 유지보수성이 향상되는 경우
- 확장성이 개선되는 경우
- 중복 구조를 제거하는 경우
- 프로젝트 복잡도를 낮출 수 있는 경우

---

# 🔗 관련 문서

- README.md
- START_HERE.md
- DOCUMENT_INDEX.md
- SYSTEM_ARCHITECTURE.md
- MODULE_REFERENCE.md

---

# ✅ 요약

HYB Opportunity AI는 **명확한 책임 분리와 장기 유지보수**를 목표로 설계된 프로젝트입니다.

프로젝트 구조는 단순히 폴더를 나누기 위한 것이 아니라, 개발 과정에서 혼란을 줄이고 프로젝트가 성장해도 일관성을 유지하기 위한 기반입니다.