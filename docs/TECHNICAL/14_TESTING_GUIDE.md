# HYB Opportunity AI
## TESTING GUIDE

Version: 1.0

---

# 목적

이 문서는 HYB Opportunity AI의 테스트 기준과 실행 방법을 정의한다.

테스트는 새로운 변경으로 기존 기능이 망가지는 것을 방지한다.

핵심 Engine은 테스트 없이 수정하지 않는다.

---

# 테스트 원칙

- 새 기능은 테스트와 함께 작성한다.
- 버그 수정 시 재현 테스트를 먼저 추가한다.
- 외부 Marketplace API에 직접 의존하지 않는다.
- 테스트는 반복 실행해도 같은 결과가 나와야 한다.
- 테스트끼리 실행 순서에 의존하지 않는다.
- 하나의 테스트는 하나의 동작을 검증한다.
- 정상 경로와 오류 경로를 모두 검증한다.

---

# 테스트 구조

```text
tests/
├── unit/
│   ├── engine/
│   ├── marketplaces/
│   ├── services/
│   └── utils/
├── integration/
│   ├── database/
│   ├── marketplace_flow/
│   └── service_flow/
├── api/
├── fixtures/
└── conftest.py
```

---

# Unit Test

하나의 함수 또는 클래스만 독립적으로 검증한다.

대상:

- Product Matching
- 가격 정규화
- ROI 계산
- Opportunity Score
- Recommendation 분류
- Confidence 계산
- 입력 Validation
- 통화 및 날짜 유틸리티

```python
from decimal import Decimal

from app.engine.finance import calculate_roi


def test_calculate_roi_returns_expected_percentage() -> None:
    result = calculate_roi(
        purchase_price=Decimal("100"),
        sale_price=Decimal("180"),
        total_cost=Decimal("20"),
    )

    assert result == Decimal("60")
```

---

# Product Matching 테스트

최소 테스트 항목:

- 완전히 같은 상품명
- 대소문자 차이
- 특수문자와 공백 차이
- 모델명 일치
- 용량이 다른 상품
- 색상이 다른 상품
- UPC 일치와 불일치
- 브랜드가 다른 상품
- 정보가 일부 누락된 상품
- 제목은 비슷하지만 다른 세대의 상품

False Positive와 False Negative를 모두 검사한다.

---

# Price Intelligence 테스트

필수 항목:

- 최저가, 평균가, 최고가
- 무료 배송
- 배송비 누락
- 통화 변환
- 음수 가격 거부
- 가격이 하나뿐인 경우
- 이상치 가격 처리
- Decimal 정밀도
- 환율 정보 누락
- 서로 다른 통화 혼합 방지

---

# Opportunity Engine 테스트

필수 항목:

- 높은 ROI와 낮은 위험
- 낮은 ROI
- 손실 상품
- 데이터 부족
- Confidence가 낮은 경우
- 경쟁 강도가 높은 경우
- 배송비가 가격보다 큰 경우
- 수수료가 누락된 경우
- 점수 범위가 0~100인지 확인
- 동일 입력에서 동일 결과가 나오는지 확인

핵심 점수 계산은 Snapshot보다 명시적인 기대값 검증을 우선한다.

---

# Marketplace 테스트

실제 API 대신 Mock 또는 저장된 Fixture를 사용한다.

```python
async def test_ebay_search_normalizes_products(
    ebay_client_mock,
    marketplace,
) -> None:
    ebay_client_mock.search.return_value = {
        "itemSummaries": [
            {
                "itemId": "123",
                "title": "Example Product",
                "price": {
                    "value": "19.99",
                    "currency": "USD",
                },
                "itemWebUrl": "https://example.invalid/item/123",
            }
        ]
    }

    products = await marketplace.search("example")

    assert len(products) == 1
    assert products[0].external_id == "123"
```

필수 오류 테스트:

- 빈 검색 결과
- 필수 필드 누락
- 잘못된 JSON
- 인증 실패
- Timeout
- Rate Limit
- 일시적인 서버 오류
- 중복 상품 제거
- 일부 상품 파싱 실패
- Health Check 실패

---

# Integration Test

여러 모듈이 함께 정상 작동하는지 검증한다.

대상:

- Marketplace → Normalize
- Normalize → Product Matching
- Engine 전체 실행
- Service → Database
- Scan Job → Recommendation 저장
- API → Service → Response

외부 인터넷 대신 테스트용 Mock Server를 권장한다.

---

# API Test

FastAPI TestClient 또는 HTTPX를 사용한다.

검증 항목:

- HTTP Status Code
- Response Schema
- Validation 오류
- 인증 오류
- 존재하지 않는 리소스
- Pagination
- Error Response 형식
- Rate Limit
- 부분 성공 Response
- 잘못된 Marketplace 이름

```python
def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

---

# Database Test

운영 Database를 사용하지 않는다.

권장 방식:

- 테스트 전용 Database
- Transaction Rollback
- 독립된 Fixture
- 테스트 종료 후 데이터 정리
- Migration 적용 검증

검증 항목:

- Insert
- Update
- Query
- Unique Constraint
- Foreign Key
- Migration
- Decimal 저장 정밀도
- UTC 시간 저장
- 중복 Marketplace 상품 방지

---

# Fixture 관리

반복되는 데이터는 Fixture로 만든다.

```python
from decimal import Decimal

import pytest

from app.models.marketplace_product import MarketplaceProduct


@pytest.fixture
def sample_marketplace_product() -> MarketplaceProduct:
    return MarketplaceProduct(
        marketplace="ebay",
        external_id="product-1",
        title="Sample Product",
        price=Decimal("100.00"),
        currency="USD",
        product_url="https://example.invalid/product-1",
        shipping_cost=Decimal("0"),
        raw_data={},
    )
```

Fixture에 실제 Secret이나 개인정보를 넣지 않는다.

---

# 테스트 이름

테스트 이름만 보고 조건과 기대 결과를 이해할 수 있어야 한다.

```text
test_opportunity_score_decreases_when_confidence_is_low
test_product_matching_rejects_different_storage_capacity
test_marketplace_retries_after_rate_limit
```

다음처럼 의미 없는 이름은 사용하지 않는다.

```text
test_1
test_score
test_product
```

---

# Parametrize

유사한 입력을 여러 개 검사할 때 `pytest.mark.parametrize`를 사용한다.

```python
import pytest


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("$19.99", "19.99"),
        ("1,299.00", "1299.00"),
        ("₩15,000", "15000"),
    ],
)
def test_parse_price(raw_value: str, expected: str) -> None:
    assert str(parse_decimal(raw_value)) == expected
```

---

# 테스트 커버리지

전체 목표:

```text
최소 80%
```

핵심 Engine 목표:

```text
90% 이상
```

단순히 숫자를 높이기 위한 테스트는 작성하지 않는다.

중요한 의사결정 로직과 오류 경로를 우선한다.

---

# 테스트 실행

```bash
pytest
pytest -v
pytest tests/unit/engine/test_opportunity.py
pytest --cov=app --cov-report=term-missing
pytest -x
pytest --lf
```

---

# CI 기준

GitHub Push 또는 Pull Request 시 다음을 실행한다.

```text
Ruff
Black Check
Mypy
Unit Tests
Integration Tests
Coverage Check
Secret Scan
```

다음 조건에서는 Merge하지 않는다.

- 테스트 실패
- 핵심 Engine Coverage 하락
- 타입 검사 실패
- Lint 오류
- Migration 검증 실패
- Secret Scan 실패

---

# 버그 수정 절차

1. 버그를 재현하는 테스트 작성
2. 테스트 실패 확인
3. 코드 수정
4. 재현 테스트 통과 확인
5. 전체 회귀 테스트 실행
6. CHANGELOG 기록
7. Commit 및 Push

---

# 외부 API 테스트 원칙

실제 Marketplace API를 매 테스트마다 호출하지 않는다.

자동 테스트에서는 다음을 사용한다.

- Mock Client
- 저장된 JSON Fixture
- Mock HTTP Server
- Dependency Injection
- Fake Repository

실제 API 테스트는 별도의 제한된 E2E 테스트로 구분한다.

---

# 테스트 데이터 보안

테스트 데이터에 포함하지 않는다.

- 실제 API Key
- Access Token
- 실제 사용자 이메일
- 실제 주문 정보
- 실제 결제 정보
- 실제 Session Cookie

---

# 완료 조건

새 기능은 다음 조건을 모두 만족해야 완료로 판단한다.

- 정상 동작 테스트 존재
- 오류 상황 테스트 존재
- 기존 테스트 통과
- 외부 API Mock 처리
- 테스트가 독립적으로 실행됨
- 핵심 로직의 기대 결과가 명확함
- Coverage가 기준 이하로 떨어지지 않음
- 운영 Secret을 사용하지 않음
