# HYB Opportunity AI
## MODULE REFERENCE

Version: 1.0

---

# 목적

이 문서는 프로젝트의 모든 모듈과 파일의 책임(Responsibility)을 정의한다.

새로운 기능을 개발하기 전에
반드시 해당 기능이 어느 모듈에 속하는지 확인한다.

한 파일은 하나의 책임만 가진다.

---

# 프로젝트 구조

project/

app/
│
├── engine/
├── marketplaces/
├── collectors/
├── services/
├── storage/
├── database/
├── models/
├── schemas/
├── config/
├── utils/
├── tests/

---

# engine/

프로젝트의 핵심 AI 엔진

Engine은

"어떻게 분석할 것인가"

만 담당한다.

외부 API를 호출하지 않는다.

Database를 직접 제어하지 않는다.

UI를 알지 못한다.

---

## product_matching.py

역할

동일 상품 판별

입력

Product List

출력

Matched Product Groups

사용 데이터

- 상품명
- 브랜드
- 모델명
- UPC
- EAN
- SKU
- 옵션
- 색상
- 용량

---

## price_intelligence.py

역할

가격 분석

계산

- 최저가
- 최고가
- 평균가
- 배송 포함 가격
- 국가별 가격
- 환율 적용 가격

출력

Price Report

---

## trend_scoring.py

역할

시장 흐름 분석

분석 요소

- 가격 변화
- 판매량 변화
- 리뷰 증가
- 계절성
- 검색량
- 품절 여부

출력

Trend Score

---

## confidence.py

역할

AI 신뢰도 계산

판단 요소

- 데이터 수
- Marketplace 수
- 일치율
- 가격 분산

출력

Confidence Score

---

## opportunity.py

역할

Opportunity Score 계산

입력

Price Report

Trend Score

Confidence

수수료

관세

배송비

출력

Opportunity Result

---

## recommendation.py

역할

최종 추천 생성

예시

Strong Buy

Good

Watch

Avoid

추천 이유 생성

출력

Recommendation

---

## orchestrator.py

역할

전체 AI Engine 실행

실행 순서

Product Matching

↓

Price Intelligence

↓

Trend

↓

Confidence

↓

Opportunity

↓

Recommendation

Engine의 진입점이다.

---

# marketplaces/

Marketplace별 구현

각 Marketplace는

동일한 Interface를 구현한다.

예

ebay.py

amazon.py

temu.py

coupang.py

naver.py

walmart.py

새 Marketplace를 추가해도

Engine은 수정하지 않는다.

---

# collectors/

역할

Marketplace에서

데이터를 수집한다.

담당

API 호출

HTML 수집

Retry

Rate Limit

Parsing

담당하지 않는 것

분석

추천

DB 저장

---

# services/

여러 모듈을 조합하여

비즈니스 기능을 만든다.

예

Search Service

↓

Marketplace 검색

↓

AI Engine 실행

↓

결과 반환

---

# storage/

역할

데이터 저장

예

Price History

Recommendation History

Search History

Cache

Scan Result

Storage는 계산하지 않는다.

---

# database/

DB 접근

담당

Insert

Update

Delete

Query

Connection

ORM

비즈니스 로직은 작성하지 않는다.

---

# models/

공통 객체

예

Product

MarketplaceProduct

Recommendation

PriceReport

Opportunity

SearchRequest

SearchResult

---

# schemas/

API 입출력

예

Request

Response

Validation

Serialization

---

# config/

환경 설정

예

.env

API KEY

DB 설정

Marketplace 설정

Feature Toggle

Runtime 설정

---

# utils/

공통 함수

예

환율

날짜

문자열

Logger

Timer

Retry

Formatter

공통으로 사용하는 기능만 작성한다.

---

# tests/

모든 테스트

Engine Test

Marketplace Test

Service Test

API Test

Regression Test

새 기능은 테스트와 함께 추가한다.

---

# 모듈 간 관계

Dashboard

↓

FastAPI

↓

Service

↓

Engine

↓

Marketplace

↓

Collector

↓

Storage

↓

Database

방향은 절대 반대로 흐르지 않는다.

---

# 새 기능 추가 규칙

기능을 만들기 전에

1.

어느 모듈인가?

2.

책임이 맞는가?

3.

기존 모듈을 수정해야 하는가?

4.

새 파일이 더 적합한가?

5.

테스트 가능한가?

를 반드시 확인한다.

---

# 최종 원칙

Engine는 AI만 생각한다.

Marketplace는 상품만 가져온다.

Collector는 수집만 한다.

Storage는 저장만 한다.

Database는 데이터만 관리한다.

Service는 연결만 한다.

UI는 보여주기만 한다.

각 모듈은 자신의 책임 외에는 절대 수행하지 않는다.

이 원칙은 프로젝트가 커질수록 더욱 중요해진다.