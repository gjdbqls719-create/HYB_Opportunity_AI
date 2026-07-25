# HYB Opportunity AI
## MARKETPLACE INTERFACE SPECIFICATION

Version: 1.0

---

# 목적

이 문서는 HYB Opportunity AI에서 모든 Marketplace 연동 모듈이
동일한 규칙과 데이터 형식을 사용하도록 정의한다.

새 Marketplace를 추가하더라도 기존 AI Engine과 Service 코드를
가능한 한 수정하지 않는 구조를 유지하는 것이 목표다.

---

# 기본 원칙

- Marketplace 모듈은 상품 수집과 데이터 변환만 담당한다.
- Opportunity 계산이나 추천 생성을 수행하지 않는다.
- 외부 Marketplace 데이터를 공통 상품 모델로 변환한다.
- 하나의 Marketplace 오류가 전체 시스템을 중단시키면 안 된다.
- API Key와 인증 정보는 소스 코드에 직접 작성하지 않는다.
- Marketplace별 차이는 해당 Marketplace 모듈 내부에서 처리한다.
- Engine은 Marketplace별 원본 데이터 구조를 알지 못해야 한다.

---

# Marketplace 처리 흐름

```text
Marketplace API 또는 Web Source
            ↓
Marketplace Connector
            ↓
Raw Data Parsing
            ↓
Normalization
            ↓
MarketplaceProduct
            ↓
Product Matching Engine
            ↓
Price Intelligence
            ↓
Opportunity Engine
```

---

# 기본 인터페이스

모든 Marketplace 구현체는 공통 인터페이스를 상속한다.

```python
from abc import ABC, abstractmethod
from typing import Any

from app.models.marketplace_product import MarketplaceProduct


class BaseMarketplace(ABC):
    """모든 Marketplace 구현체가 따라야 하는 기본 인터페이스."""

    marketplace_name: str

    @abstractmethod
    async def search(
        self,
        keyword: str,
        *,
        page: int = 1,
        limit: int = 50,
    ) -> list[MarketplaceProduct]:
        """키워드로 상품을 검색한다."""

    @abstractmethod
    async def get_product(
        self,
        external_id: str,
    ) -> MarketplaceProduct:
        """Marketplace 상품 ID를 이용해 상세 정보를 조회한다."""

    @abstractmethod
    def normalize(
        self,
        raw_data: dict[str, Any],
    ) -> MarketplaceProduct:
        """Marketplace 원본 데이터를 공통 모델로 변환한다."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Marketplace 연결 상태를 확인한다."""
```

---

# 공통 상품 모델

모든 Marketplace 상품은 다음 공통 모델로 변환한다.

실제 코드 파일 위치 예시:

```text
app/models/marketplace_product.py
```

구현 예시:

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class MarketplaceProduct:
    """Marketplace에서 수집한 상품의 공통 데이터 모델."""

    marketplace: str
    external_id: str
    title: str
    price: Decimal
    currency: str
    product_url: str

    shipping_cost: Decimal | None = None
    seller_name: str | None = None
    image_url: str | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    condition: str | None = None
    stock_status: str | None = None
    rating: float | None = None
    review_count: int | None = None
    sku: str | None = None
    upc: str | None = None
    ean: str | None = None
    collected_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def total_price(self) -> Decimal | None:
        """상품 가격과 배송비를 합산한다."""

        if self.shipping_cost is None:
            return None

        return self.price + self.shipping_cost
```

---

# 필수 필드

모든 Marketplace 상품은 최소한 다음 필드를 제공해야 한다.

```text
marketplace
external_id
title
price
currency
product_url
```

필수 필드의 의미:

| 필드 | 설명 |
|---|---|
| marketplace | 상품이 수집된 Marketplace 이름 |
| external_id | Marketplace 내부 상품 ID |
| title | 원본 상품 제목 |
| price | 상품 가격 |
| currency | 원본 통화 |
| product_url | 원본 상품 페이지 주소 |

선택 필드는 데이터를 얻을 수 없는 경우 `None`으로 저장한다.

존재하지 않는 값을 임의로 생성하거나 추정해서 저장하지 않는다.

---

# 공통 필드 규칙

## marketplace

소문자로 통일한다.

예시:

```text
ebay
amazon
temu
coupang
naver
walmart
```

---

## external_id

Marketplace에서 상품을 고유하게 구분하는 ID를 저장한다.

동일 Marketplace 안에서는 중복되지 않아야 한다.

권장 Unique Key:

```text
marketplace + external_id
```

---

## title

Marketplace에서 제공한 원본 제목을 유지한다.

상품명 정규화는 별도 Product Matching 단계에서 수행한다.

Marketplace Layer에서 제목 내용을 과도하게 수정하지 않는다.

---

## price

금액 계산에는 `float`를 사용하지 않는다.

반드시 `Decimal`을 사용한다.

```python
from decimal import Decimal

price = Decimal("19.99")
```

잘못된 예:

```python
price = 19.99
```

---

## currency

ISO 4217 통화 코드를 사용한다.

예시:

```text
USD
KRW
JPY
CNY
EUR
GBP
```

Marketplace Layer에서는 환율을 변환하지 않는다.

원본 통화와 원본 가격을 그대로 유지한다.

---

## shipping_cost

배송비가 무료이면 `Decimal("0")`을 저장한다.

배송비를 확인할 수 없으면 `None`을 저장한다.

배송비를 알 수 없는데 임의로 `0`으로 처리하면 안 된다.

---

## rating

평점은 가능한 경우 `0.0`에서 `5.0` 범위로 정규화한다.

Marketplace가 다른 평점 체계를 사용하면 공통 기준으로 변환한다.

예시:

```text
100점 만점의 80점 → 4.0
10점 만점의 8점 → 4.0
```

변환이 불가능하거나 기준이 불명확하면 원본 값은 `raw_data`에 남기고
공통 `rating`은 `None`으로 처리한다.

---

## stock_status

권장 값:

```text
available
out_of_stock
limited
unknown
```

Marketplace가 제공하는 원본 재고 문구는 공통 값으로 변환한다.

---

## condition

권장 값:

```text
new
used
refurbished
open_box
unknown
```

---

# 검색 메서드

`search()`는 키워드로 상품 목록을 검색한다.

```python
async def search(
    self,
    keyword: str,
    *,
    page: int = 1,
    limit: int = 50,
) -> list[MarketplaceProduct]:
    ...
```

---

# 검색 입력 규칙

## keyword

빈 문자열을 허용하지 않는다.

```python
if not keyword.strip():
    raise ValueError("keyword must not be empty")
```

---

## page

페이지 번호는 `1` 이상이어야 한다.

---

## limit

검색 결과 개수 제한이다.

기본값:

```text
50
```

권장 최대값:

```text
100
```

Marketplace 자체 제한이 더 작다면 Marketplace 제한을 따른다.

---

# 검색 출력 규칙

검색 결과는 항상 다음 형식으로 반환한다.

```python
list[MarketplaceProduct]
```

검색 결과가 없으면 예외 대신 빈 목록을 반환한다.

```python
return []
```

한 상품의 변환이 실패하더라도 전체 검색 결과를 버리지 않는다.

가능한 상품은 계속 반환하고 실패한 상품은 로그로 기록한다.

---

# 검색 결과 중복 처리

동일한 `external_id`가 여러 번 등장하면 하나만 유지한다.

```python
unique_products: dict[str, MarketplaceProduct] = {}

for product in products:
    unique_products[product.external_id] = product

return list(unique_products.values())
```

---

# 상세 조회 메서드

`get_product()`는 Marketplace 상품 ID를 사용해 상세 정보를 조회한다.

```python
async def get_product(
    self,
    external_id: str,
) -> MarketplaceProduct:
    ...
```

상품이 존재하지 않으면 다음 예외를 발생시킨다.

```python
class MarketplaceProductNotFoundError(MarketplaceError):
    pass
```

---

# Normalize 규칙

Marketplace마다 다른 원본 데이터를 공통 모델로 변환한다.

예시:

```text
eBay title              → title
Amazon product_title    → title
Temu goodsName          → title
Coupang productName     → title
```

가격 예시:

```text
eBay price.value        → price
Amazon price.amount     → price
Temu salePrice          → price
```

---

# Normalize 예시

```python
from decimal import Decimal
from typing import Any

from app.models.marketplace_product import MarketplaceProduct


def normalize(
    self,
    raw_data: dict[str, Any],
) -> MarketplaceProduct:
    price_data = raw_data.get("price") or {}

    return MarketplaceProduct(
        marketplace=self.marketplace_name,
        external_id=str(raw_data["itemId"]),
        title=str(raw_data["title"]).strip(),
        price=Decimal(str(price_data["value"])),
        currency=str(price_data["currency"]).upper(),
        product_url=str(raw_data["itemWebUrl"]),
        shipping_cost=self._extract_shipping_cost(raw_data),
        seller_name=self._extract_seller_name(raw_data),
        image_url=self._extract_image_url(raw_data),
        brand=self._extract_brand(raw_data),
        model=self._extract_model(raw_data),
        category=self._extract_category(raw_data),
        condition=self._normalize_condition(raw_data),
        stock_status=self._normalize_stock_status(raw_data),
        rating=self._extract_rating(raw_data),
        review_count=self._extract_review_count(raw_data),
        raw_data=raw_data,
    )
```

---

# 가격 정규화

가격 문자열에서 통화 기호와 쉼표를 제거한 뒤 `Decimal`로 변환한다.

```python
from decimal import Decimal, InvalidOperation


def parse_decimal(value: object) -> Decimal:
    if value is None:
        raise ValueError("price value is missing")

    normalized = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .replace("₩", "")
        .replace("€", "")
        .strip()
    )

    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc

    if result < 0:
        raise ValueError("price must not be negative")

    return result
```

---

# Raw Data 보관

Marketplace의 원본 응답은 `raw_data`에 보관할 수 있다.

목적:

- 파싱 오류 분석
- Marketplace 응답 구조 변경 대응
- 누락 필드 재처리
- 디버깅
- 추후 데이터 재정규화

단, 다음 정보는 저장하지 않는다.

- Access Token
- API Secret
- 인증 Header
- Session Cookie
- 개인 정보
- 결제 정보

---

# Marketplace 오류 구조

공통 예외 계층을 사용한다.

```python
class MarketplaceError(Exception):
    """Marketplace 관련 기본 예외."""


class MarketplaceAuthenticationError(MarketplaceError):
    """인증 실패."""


class MarketplaceRateLimitError(MarketplaceError):
    """요청 제한 초과."""


class MarketplaceTemporaryError(MarketplaceError):
    """일시적인 네트워크 또는 서버 오류."""


class MarketplaceParsingError(MarketplaceError):
    """원본 데이터를 공통 모델로 변환하지 못한 오류."""


class MarketplaceProductNotFoundError(MarketplaceError):
    """요청한 상품을 찾지 못한 오류."""


class MarketplaceInvalidRequestError(MarketplaceError):
    """잘못된 Marketplace 요청."""
```

---

# HTTP 오류 변환 규칙

권장 매핑:

| HTTP 상태 | 공통 예외 |
|---|---|
| 400 | MarketplaceInvalidRequestError |
| 401 | MarketplaceAuthenticationError |
| 403 | MarketplaceAuthenticationError |
| 404 | MarketplaceProductNotFoundError |
| 408 | MarketplaceTemporaryError |
| 429 | MarketplaceRateLimitError |
| 500 | MarketplaceTemporaryError |
| 502 | MarketplaceTemporaryError |
| 503 | MarketplaceTemporaryError |
| 504 | MarketplaceTemporaryError |

---

# 재시도 정책

재시도 대상:

- Timeout
- 연결 실패
- HTTP 408
- HTTP 429
- HTTP 500
- HTTP 502
- HTTP 503
- HTTP 504
- 일시적인 DNS 오류

재시도하지 않는 오류:

- 인증 실패
- 잘못된 요청
- 상품 없음
- 필수 환경 변수 누락
- 영구적인 데이터 구조 오류

기본 정책:

```text
최대 재시도 횟수: 3회
대기 방식: Exponential Backoff
대기 예시: 1초 → 2초 → 4초
```

Jitter를 추가해 여러 요청이 동시에 재시도되는 것을 방지한다.

---

# Retry 구현 예시

```python
import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
) -> T:
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await operation()
        except MarketplaceTemporaryError as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            delay = (2**attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

    if last_error is None:
        raise RuntimeError("retry failed without captured exception")

    raise last_error
```

---

# Rate Limit

각 Marketplace Connector는 자체 Rate Limit을 관리한다.

관리 대상:

- 초당 요청 수
- 분당 요청 수
- 일일 요청 수
- 남은 요청 수
- 제한 초기화 시각
- Retry-After Header

Rate Limit 발생 시 전체 시스템을 중단하지 않는다.

처리 흐름:

```text
Rate Limit 감지
      ↓
Retry-After 확인
      ↓
해당 Marketplace 일시 중지
      ↓
다른 Marketplace 처리 계속
      ↓
대기 종료 후 재시도
```

---

# Timeout

모든 네트워크 요청에는 Timeout을 설정한다.

권장 기본값:

```text
연결 Timeout: 10초
전체 요청 Timeout: 30초
```

무제한 대기는 허용하지 않는다.

---

# 인증 정보 관리

인증 정보는 환경 변수로 관리한다.

예시:

```env
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=

AMAZON_ACCESS_KEY=
AMAZON_SECRET_KEY=

TEMU_API_KEY=

COUPANG_ACCESS_KEY=
COUPANG_SECRET_KEY=

NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
```

---

# 인증 보안 규칙

금지 사항:

- 소스 코드에 API Key 작성
- GitHub에 `.env` 업로드
- 로그에 Secret 출력
- 예외 메시지에 Authorization Header 포함
- 테스트 코드에 실제 운영 Key 사용
- Screenshot에 Secret 노출

`.gitignore` 예시:

```gitignore
.env
.env.*
!.env.example
```

---

# 환경 변수 검증

프로그램 시작 시 필요한 환경 변수를 검증한다.

예시:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
```

Marketplace가 비활성 상태라면 Key가 없어도 전체 프로그램은 실행할 수 있어야 한다.

---

# Marketplace Registry

Marketplace 구현체는 Registry에 등록한다.

```python
from app.marketplaces.amazon import AmazonMarketplace
from app.marketplaces.ebay import EbayMarketplace


MARKETPLACE_REGISTRY = {
    "ebay": EbayMarketplace,
    "amazon": AmazonMarketplace,
}
```

Service는 구체적인 Marketplace 클래스를 직접 참조하지 않는다.

---

# Marketplace Factory

```python
from app.marketplaces.base import BaseMarketplace


class MarketplaceFactory:
    def __init__(
        self,
        registry: dict[str, type[BaseMarketplace]],
    ) -> None:
        self._registry = registry

    def create(self, marketplace_name: str) -> BaseMarketplace:
        normalized_name = marketplace_name.strip().lower()

        marketplace_class = self._registry.get(normalized_name)

        if marketplace_class is None:
            raise ValueError(
                f"unsupported marketplace: {marketplace_name}"
            )

        return marketplace_class()
```

사용 예시:

```python
marketplace = marketplace_factory.create("ebay")
products = await marketplace.search("RTX 5070")
```

---

# Marketplace 상태 확인

각 Marketplace는 `health_check()`를 구현한다.

```python
async def health_check(self) -> bool:
    try:
        await self._client.ping()
    except MarketplaceError:
        return False

    return True
```

Health Check에서는 대량 검색을 수행하지 않는다.

가장 가벼운 인증 또는 연결 확인 요청을 사용한다.

---

# 부분 실패 처리

여러 Marketplace를 동시에 검색할 때 일부 실패를 허용한다.

예시 결과:

```python
{
    "successful_marketplaces": [
        "ebay",
        "amazon",
    ],
    "failed_marketplaces": [
        {
            "marketplace": "temu",
            "error": "rate_limit",
        }
    ],
    "products": [],
}
```

하나의 Marketplace 실패가 전체 검색 실패로 처리되지 않아야 한다.

---

# 동시 실행

Marketplace 검색은 가능한 경우 비동기로 병렬 실행한다.

```python
import asyncio


results = await asyncio.gather(
    ebay.search(keyword),
    amazon.search(keyword),
    temu.search(keyword),
    return_exceptions=True,
)
```

각 결과를 개별적으로 검사해 성공과 실패를 분리한다.

---

# Logging

Marketplace 로그에는 다음 정보를 포함한다.

- Marketplace 이름
- 요청 종류
- 검색 키워드
- 응답 시간
- 상품 개수
- 재시도 횟수
- HTTP 상태
- 오류 종류

로그에 포함하지 않는다.

- API Key
- Secret
- Access Token
- Cookie
- 전체 Authorization Header

---

# Marketplace 테스트

각 Marketplace 구현체는 다음 테스트를 포함해야 한다.

- 검색 성공
- 빈 검색 결과
- 상품 상세 조회
- 가격 정규화
- 배송비 정규화
- 통화 정규화
- 필수 필드 누락
- 잘못된 JSON
- 인증 실패
- Timeout
- Rate Limit
- 일시적인 서버 오류
- 중복 상품 제거
- 일부 상품 파싱 실패
- Health Check

실제 외부 API 대신 Mock 응답이나 Fixture를 사용한다.

---

# 새 Marketplace 추가 절차

1. Marketplace API 또는 수집 방식을 조사한다.
2. 필요한 인증 정보를 확인한다.
3. `BaseMarketplace`를 상속한다.
4. `search()`를 구현한다.
5. `get_product()`를 구현한다.
6. `normalize()`를 구현한다.
7. `health_check()`를 구현한다.
8. 오류를 공통 예외로 변환한다.
9. Rate Limit과 Retry를 처리한다.
10. 단위 테스트를 작성한다.
11. 통합 테스트를 실행한다.
12. Registry에 등록한다.
13. `.env.example`을 갱신한다.
14. CHANGELOG를 갱신한다.
15. Marketplace 문서를 갱신한다.

---

# Marketplace 구현 예시 구조

```text
app/
└── marketplaces/
    ├── __init__.py
    ├── base.py
    ├── exceptions.py
    ├── factory.py
    ├── registry.py
    ├── ebay/
    │   ├── __init__.py
    │   ├── client.py
    │   ├── marketplace.py
    │   └── normalizer.py
    ├── amazon/
    │   ├── __init__.py
    │   ├── client.py
    │   ├── marketplace.py
    │   └── normalizer.py
    └── temu/
        ├── __init__.py
        ├── client.py
        ├── marketplace.py
        └── normalizer.py
```

작은 Marketplace는 하나의 파일로 시작할 수 있다.

복잡도가 커지면 `client`, `marketplace`, `normalizer`로 분리한다.

---

# 절대 하지 않을 것

- Marketplace 모듈에서 Opportunity Score 계산
- Marketplace 모듈에서 Recommendation 생성
- Marketplace별 데이터를 Engine이 직접 읽게 만들기
- 원본 응답 구조를 Service에 그대로 전달
- 가격을 `float`로 계산
- 배송비 누락을 무료 배송으로 가정
- Secret을 코드에 저장
- 오류를 `except Exception: pass`로 무시
- 실제 API에 의존하는 불안정한 테스트 작성
- 특정 Marketplace 실패로 전체 검색 중단

---

# 완료 조건

새 Marketplace를 추가했을 때 다음 모듈은 수정하지 않아야 한다.

```text
Product Matching
Price Intelligence
Trend Analysis
Confidence Engine
Opportunity Engine
Recommendation Engine
```

Marketplace 추가 작업은 다음 범위 안에서 끝나는 것이 이상적이다.

```text
Marketplace 구현
Registry 등록
환경 변수 추가
테스트 추가
문서 갱신
```

---

# 최종 원칙

Marketplace Layer는 외부 시장의 서로 다른 데이터를
HYB Opportunity AI가 이해할 수 있는 하나의 공통 언어로 변환한다.

Marketplace는 상품을 가져온다.

Engine은 상품을 분석한다.

Service는 전체 흐름을 연결한다.

각 계층은 자신의 책임만 수행한다.