# HYB Opportunity AI
## CODING STANDARD

Version: 1.0

---

# 목적

이 문서는 HYB Opportunity AI 프로젝트 전체에서 일관된 코드 품질과 구조를 유지하기 위한 기준을 정의한다.

코드는 작성자보다 오래 남는다는 원칙을 따른다.

---

# 기본 기준

- Python 3.12 이상을 기준으로 한다.
- PEP 8을 따른다.
- 공개 함수와 메서드에는 타입 힌트를 작성한다.
- 함수와 클래스는 하나의 명확한 책임을 가진다.
- 의미 없는 축약어를 사용하지 않는다.
- 복잡한 코드보다 읽기 쉬운 코드를 우선한다.
- 중복 코드보다 재사용 가능한 구조를 우선한다.
- 핵심 계산 로직은 테스트 가능하도록 분리한다.

---

# 이름 규칙

Python 파일, 함수, 변수는 `snake_case`를 사용한다.

```text
product_matching.py
calculate_opportunity_score
total_profit
```

클래스는 `PascalCase`를 사용한다.

```python
class OpportunityEngine:
    pass
```

상수는 `UPPER_SNAKE_CASE`를 사용한다.

```python
MAX_RETRY_COUNT = 3
DEFAULT_PAGE_SIZE = 50
MIN_CONFIDENCE_SCORE = 60
```

Boolean 값은 의미가 드러나도록 작성한다.

```python
is_available = True
has_shipping_cost = False
should_retry = True
```

---

# 타입 힌트

모든 공개 함수는 입력과 반환 타입을 명시한다.

```python
from decimal import Decimal


def calculate_roi(
    purchase_price: Decimal,
    sale_price: Decimal,
    total_cost: Decimal,
) -> Decimal:
    net_profit = sale_price - purchase_price - total_cost
    return (net_profit / purchase_price) * Decimal("100")
```

의미 없는 매개변수명은 사용하지 않는다.

---

# 함수 크기

하나의 함수는 가능한 한 30줄 이내를 목표로 한다.

다음 상황에서는 함수를 분리한다.

- 서로 다른 책임이 존재한다.
- 조건문이 과도하게 중첩된다.
- 동일 코드가 반복된다.
- 테스트하기 어렵다.
- 함수 이름만으로 기능을 설명하기 어렵다.

---

# Docstring

공개 클래스와 공개 함수에는 Docstring을 작성한다.

```python
from decimal import Decimal


def normalize_price(raw_price: str) -> Decimal:
    """Marketplace 가격 문자열을 Decimal 값으로 변환한다.

    Args:
        raw_price: 통화 기호를 포함할 수 있는 원본 가격 문자열.

    Returns:
        정규화된 가격.

    Raises:
        ValueError: 가격을 숫자로 변환할 수 없는 경우.
    """
```

---

# Import 순서

1. Python 표준 라이브러리
2. 외부 라이브러리
3. 프로젝트 내부 모듈

```python
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.engine.opportunity import OpportunityEngine
from app.models.product import Product
```

---

# 예외 처리

구체적인 예외를 처리한다.

```python
try:
    response = await client.get(url)
except TimeoutError as exc:
    raise MarketplaceTemporaryError("Request timed out") from exc
```

다음 방식은 사용하지 않는다.

```python
try:
    response = await client.get(url)
except Exception:
    pass
```

예외를 조용히 무시하지 않는다.

---

# 로깅

`print()` 대신 Logger를 사용한다.

```python
logger.info(
    "Marketplace scan completed",
    extra={
        "marketplace": marketplace_name,
        "product_count": len(products),
    },
)
```

로그 수준:

- `DEBUG`: 개발용 상세 정보
- `INFO`: 정상적인 주요 처리
- `WARNING`: 복구 가능한 문제
- `ERROR`: 기능 실패
- `CRITICAL`: 서비스 지속이 어려운 문제

로그에 Secret, Password, Access Token, Cookie, Authorization Header를 포함하지 않는다.

---

# 가격 계산

금액 계산에는 `float`를 사용하지 않는다.

```python
from decimal import Decimal

price = Decimal("19.99")
```

가격 값은 통화 정보와 함께 관리한다.

---

# 시간 처리

내부 시간은 UTC 기준으로 저장한다.

```python
from datetime import UTC, datetime

created_at = datetime.now(UTC)
```

사용자에게 표시할 때만 지역 시간대로 변환한다.

---

# 설정 관리

설정값은 환경 변수 또는 Config 객체에서 가져온다.

```python
settings.ebay_client_id
settings.database_url
```

API Key와 Database 주소를 코드에 직접 작성하지 않는다.

---

# 데이터 모델 분리

계층별 모델을 구분한다.

- Database ORM Model
- Domain Model
- API Request Schema
- API Response Schema

API Schema를 Engine 내부 모델로 직접 사용하지 않는다.

Database ORM 객체를 API Response로 직접 반환하지 않는다.

---

# 비동기 코드

외부 API, 네트워크, 비동기 DB 작업에는 `async`를 사용한다.

CPU 계산만 수행하는 함수는 일반 함수로 유지한다.

비동기 함수 안에서 동기 네트워크 요청을 실행하지 않는다.

---

# 주석

주석은 코드가 무엇을 하는지가 아니라 왜 그렇게 하는지를 설명한다.

```python
# 일부 Marketplace는 배송비가 누락되므로 None을 유지해
# Opportunity Score의 신뢰도를 낮추도록 한다.
```

---

# 코드 검사 도구

권장 도구:

- Ruff
- Black
- Mypy
- Pytest

```bash
ruff check .
black --check .
mypy app
pytest
```

자동 수정:

```bash
ruff check . --fix
black .
```

---

# Git Commit

작고 의미 있는 단위로 Commit한다.

```text
feat: add opportunity score calculator
fix: handle missing shipping cost
refactor: separate marketplace normalization
test: add product matching edge cases
docs: update marketplace interface
```

한 Commit에 서로 무관한 변경을 섞지 않는다.

---

# 보안 관련 금지 사항

- 비밀 정보 하드코딩
- `.env` Commit
- 운영 API Key를 테스트에 사용
- 인증 Header 전체 로깅
- 사용자 입력을 검증 없이 SQL 또는 명령어에 전달
- 외부 URL을 검증 없이 요청
- 오류 응답에 내부 경로와 Secret 노출

---

# 계층 의존성 규칙

```text
API / Dashboard
      ↓
Service
      ↓
Engine
      ↓
Marketplace / Storage Interface
      ↓
External API / Database
```

금지:

- Engine이 FastAPI 객체를 직접 참조
- Marketplace가 Recommendation 생성
- Database Layer가 Opportunity Score 계산
- UI가 Marketplace Client를 직접 호출
- Collector가 DB 구조에 강하게 의존

---

# 코드 리뷰 체크리스트

- 책임이 명확한가?
- 함수와 변수명이 의미를 전달하는가?
- 타입 힌트가 정확한가?
- 예외가 추적 가능한가?
- Secret이 노출되지 않는가?
- 테스트가 추가되었는가?
- 기존 구조를 깨지 않는가?
- 가격 계산에 Decimal을 사용하는가?
- 문서와 CHANGELOG 갱신이 필요한가?

---

# 완료 기준

코드는 다음 질문에 모두 `Yes`여야 한다.

- 읽기 쉬운가?
- 테스트 가능한가?
- 책임이 명확한가?
- 타입이 명확한가?
- 오류를 추적할 수 있는가?
- 프로젝트 구조를 지키는가?
- 비밀 정보가 노출되지 않는가?
- 미래 확장이 가능한가?
