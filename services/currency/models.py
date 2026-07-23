from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def normalize_currency_code(value: str, field_name: str = "통화 코드") -> str:
    """ISO 4217 형태의 3자리 영문 통화 코드를 정규화한다."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name}은(는) 문자열이어야 합니다.")

    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
        raise ValueError(f"{field_name}은(는) 3자리 영문 코드여야 합니다.")
    return normalized


def to_decimal(value: Any, field_name: str) -> Decimal:
    """외부 숫자 입력을 부동소수점 오차 없이 Decimal로 변환한다."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name}은(는) 숫자여야 합니다.")

    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"{field_name}은(는) 숫자여야 합니다.") from error

    if not result.is_finite():
        raise ValueError(f"{field_name}은(는) 유한한 숫자여야 합니다.")
    return result


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    """기준 통화 1단위가 상대 통화로 얼마인지 나타내는 환율."""

    base_currency: str
    quote_currency: str
    rate: Decimal
    retrieved_at: datetime
    source: str = "unknown"

    def __post_init__(self) -> None:
        base = normalize_currency_code(self.base_currency, "기준 통화")
        quote = normalize_currency_code(self.quote_currency, "상대 통화")
        rate = to_decimal(self.rate, "환율")

        if rate <= 0:
            raise ValueError("환율은 0보다 커야 합니다.")
        if not isinstance(self.retrieved_at, datetime):
            raise TypeError("환율 조회 시각은 datetime이어야 합니다.")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("환율 조회 시각에는 시간대 정보가 필요합니다.")

        source = self.source.strip()
        if not source:
            raise ValueError("환율 출처는 비어 있을 수 없습니다.")

        object.__setattr__(self, "base_currency", base)
        object.__setattr__(self, "quote_currency", quote)
        object.__setattr__(self, "rate", rate)
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(timezone.utc))
        object.__setattr__(self, "source", source)

    @property
    def pair(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"

    def inverse(self) -> ExchangeRate:
        """현재 환율의 역환율을 반환한다."""
        return ExchangeRate(
            base_currency=self.quote_currency,
            quote_currency=self.base_currency,
            rate=Decimal("1") / self.rate,
            retrieved_at=self.retrieved_at,
            source=self.source,
        )
