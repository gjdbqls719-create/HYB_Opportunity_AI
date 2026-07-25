# HYB Opportunity AI 프로젝트 코드 리뷰

> 실제 업로드된 저장소를 기준으로 작성한 1차 기술 분석 문서

## 1. 검토 결과 요약

현재 프로젝트는 빈 프로젝트가 아니다. 상품 정규화, 상품 매칭, 가격 분석, 가격 이력, 신뢰도 계산, 기회 점수, 추천 결과를 각각 독립된 모듈로 분리했고 자동 테스트도 갖추고 있다.

검토 시점 테스트 결과:

```text
67 passed in 0.30s
```

따라서 처음부터 다시 만들기보다 현재 구조를 유지하면서 모델 통합, 실제 데이터 수집 안정화, 영속 저장소 정리, UI 연결 순서로 발전시키는 것이 가장 빠르다.

## 2. 현재 실행 흐름

현재 기본 실행은 데모 흐름이다.

```text
main.py
└─ app.cli.run_demo()
   └─ engine.opportunity.calculate_opportunity()
```

실제 통합 분석 흐름은 `engine/orchestrator.py`에 구현되어 있다.

```text
find_best_opportunities(query)
├─ marketplaces.ebay.search_products()
├─ marketplaces.amazon.search_products()
├─ group_similar_products()
│  └─ engine.product_matching.compare_products()
├─ engine.price_intelligence.analyze_product_prices()
├─ engine.confidence.calculate_price_confidence()
├─ engine.opportunity.calculate_product_opportunity()
├─ storage.price_history.PriceHistoryRepository
├─ engine.price_trend.analyze_price_trend()
├─ engine.trend_scoring.calculate_trend_score()
└─ engine.recommendation.generate_recommendation()
```

## 3. 강점

### 3.1 엔진 책임이 잘 분리됨

- `product_matching.py`: 상품 제목 기반 매칭
- `price_intelligence.py`: 가격 통계와 권장 판매가
- `confidence.py`: 표본 신뢰도
- `price_trend.py`: 저장된 가격 이력 분석
- `trend_scoring.py`: 추세 기반 점수 보정
- `opportunity.py`: 기본 수익성과 기회 점수
- `recommendation.py`: 최종 추천 등급과 설명
- `orchestrator.py`: 전체 흐름 조합

### 3.2 테스트 범위가 넓음

핵심 엔진과 저장소에 대응하는 테스트가 존재하며 현재 모두 통과한다. 이는 이후 리팩터링 시 회귀 오류를 빠르게 발견할 수 있다는 의미다.

### 3.3 외부 마켓과 분석 엔진이 분리됨

`marketplaces/`가 외부 데이터 접근과 정규화를 담당하고 `engine/`은 공통 모델을 입력받아 계산한다. 새 마켓 추가에 유리한 방향이다.

### 3.4 규칙 기반 결과가 설명 가능함

추천 결과에 점수뿐 아니라 `reasons`, `warnings`, `summary`가 포함되어 있어 사용자가 판단 근거를 확인할 수 있다.

## 4. 가장 먼저 해결해야 할 구조 문제

### 4.1 Product 모델이 두 개 존재함

현재 다음 두 모델이 동시에 존재한다.

```text
app/models/product.py
└─ marketplace, item_id, title, price, currency, condition, url

database/models.py
└─ name, marketplace, price, currency, brand, model_number, category, ...
```

`collectors/base.py`는 `database.models.Product`를 타입으로 사용하지만 `marketplaces/amazon.py`, `marketplaces/ebay.py`, `engine/orchestrator.py`는 `app.models.Product`를 사용한다.

이 상태는 현재 테스트에서는 드러나지 않더라도 향후 실제 저장과 분석을 연결할 때 타입 충돌과 필드명 불일치를 만들 가능성이 높다.

**권장 조치:** 공통 도메인 모델을 하나로 통합한다. 초기에는 `app.models.Product`를 확장하거나 별도의 `domain/models/product.py`를 만드는 방식이 적합하다. DB 전용 모델이 필요하다면 도메인 모델과 ORM/저장 모델을 명확히 분리하고 변환 함수를 둔다.

### 4.2 기본 실행이 실제 통합 흐름을 사용하지 않음

`python main.py`는 하드코딩된 데모 상품 하나만 계산한다. 실제로 구현된 `find_best_opportunities()` 흐름을 실행하지 않는다.

**권장 조치:**

- `main.py`는 CLI 진입점만 유지
- `app/cli.py`에 `demo`, `search`, `history` 같은 명령 구분
- 기본 검색 명령은 `engine.orchestrator.find_best_opportunities()` 호출

### 4.3 Amazon은 테스트용 가짜 데이터임

Amazon 검색은 실제 API가 아니라 고정된 테스트 데이터다. 이는 개발 단계에서는 유용하지만 UI에서 실제 검색처럼 표시되면 사용자 혼란을 만든다.

**권장 조치:** 결과에 `data_source="mock"` 또는 실행 모드를 명시하고 실제 연동 전까지 화면에도 테스트 데이터임을 표시한다.

### 4.4 분석 입력 중 일부가 전 상품에 동일하게 적용됨

`find_best_opportunities()`의 다음 값은 상품별 실제 데이터가 아니라 함수 인수로 동일하게 적용된다.

- `estimated_monthly_sales`
- `competitor_count`
- `risk_level`
- `shipping_cost`
- `marketplace_fee_rate`

따라서 현재 추천 점수는 상품별 실제 시장 상황보다 기본값의 영향을 크게 받는다.

**권장 조치:** 각 값에 출처와 신뢰도를 추가하고, 미수집 값은 `unknown`으로 유지하거나 보수적인 기본값과 경고를 사용한다.

### 4.5 점수 계산이 여러 단계에서 중복될 가능성

`opportunity.py`에서 이미 ROI, 판매량, 경쟁도, 위험도를 반영한 점수를 만들고, `recommendation.py`에서 ROI, 경쟁도, 위험도를 다시 반영한다.

이는 동일 요소가 이중 가중되는 구조가 될 수 있다.

**권장 조치:**

- Opportunity Score: 원시 분석 점수
- Confidence Adjustment: 데이터 품질 보정
- Trend Adjustment: 가격 추세 보정
- Recommendation: 최종 점수를 등급과 설명으로 변환

위 역할을 명확히 분리하고 Recommendation 단계에서는 점수를 다시 크게 변경하지 않는 방향을 검토한다.

## 5. 현재 모듈 상태

| 영역 | 상태 | 평가 |
|---|---|---|
| 공통 상품 모델 | 구현됨 | 중복 모델 통합 필요 |
| eBay 인증 | 구현됨 | 실제 환경 변수와 API 오류 처리 검증 필요 |
| eBay 검색 | 구현됨 | 실 API 응답과 제한 처리 점검 필요 |
| Amazon 검색 | 목업 | 실제 연동 전 명시 필요 |
| 상품 매칭 | 구현 및 테스트 | 제목 기반 초기 버전 |
| 가격 분석 | 구현 및 테스트 | 초기 규칙 기반 |
| 가격 이력 | SQLite 구현 및 테스트 | 구조가 비교적 탄탄함 |
| 가격 추세 | 구현 및 테스트 | 코드 규모가 커 분리 후보 |
| 기회 점수 | 구현 및 테스트 | 이중 가중 검토 필요 |
| 추천 엔진 | 구현 및 테스트 | 설명 가능성이 강점 |
| CLI | 데모 수준 | 통합 흐름 연결 필요 |
| 웹 UI/API | 없음 | 이후 단계 |
| 문서 | 최소 수준 | 실제 코드 기준으로 확대 필요 |

## 6. 권장 개발 순서

### Step 1 — 모델 통합

1. 공통 Product 스키마 확정
2. 중복 Product 모델 제거 또는 역할 분리
3. MarketplaceAdapter 타입 수정
4. 전체 테스트 갱신

### Step 2 — 실제 CLI 통합

1. 검색어 입력
2. eBay/Amazon 실행 모드 선택
3. Orchestrator 호출
4. 추천 결과 출력
5. 네트워크 오류를 사용자 메시지로 변환

### Step 3 — 데이터 출처와 신뢰도

1. 각 값에 source 표시
2. mock/live 구분
3. 누락 데이터 경고
4. 수집 시각 기록

### Step 4 — 점수 체계 정리

1. 점수 항목 표 작성
2. 중복 가중 제거
3. 0~100 범위 보장
4. 테스트 케이스 확대

### Step 5 — 저장과 조회

1. 검색 결과 저장
2. 동일 상품 중복 방지
3. 가격 이력 자동 기록
4. 최근 검색 결과 조회

### Step 6 — UI/API

핵심 흐름이 안정된 뒤 FastAPI와 웹 UI를 연결한다.

## 7. 바로 다음 작업

가장 먼저 해야 할 실제 코드 작업은 **Product 모델 통합 설계**다. 이 작업이 끝나야 Collector, Database, Engine, UI가 같은 데이터 구조를 사용할 수 있다.

그다음 `main.py`와 `app/cli.py`를 Orchestrator에 연결하면 사용자가 검색어를 입력해 실제 분석 결과를 확인하는 최소 동작 흐름을 만들 수 있다.

## 8. 판정

현재 프로젝트는 폐기하거나 처음부터 다시 만들 수준이 아니다. 핵심 엔진 구조와 테스트 기반은 유지할 가치가 충분하다.

현재 단계의 정확한 표현은 다음과 같다.

> 규칙 기반 상품 기회 분석 엔진의 프로토타입은 구축되었고, 실제 제품으로 전환하기 위해 데이터 모델 통합과 실사용 흐름 연결이 필요한 상태다.

---

문서 버전: 0.1.0  
검토일: 2026-07-21
