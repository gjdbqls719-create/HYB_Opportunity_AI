from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from services.currency.models import ExchangeRate, normalize_currency_code, to_decimal
from services.currency.provider import ExchangeRateNotFoundError, ExchangeRateProvider


class MockExchangeRateProvider(ExchangeRateProvider):
    """테스트와 로컬 개발에 사용하는 메모리 기반 환율 공급자."""

    def __init__(
        self,
        rates: Mapping[tuple[str, str], Any] | None = None,
        *,
        source: str = "mock",
        retrieved_at: datetime | None = None,
    ) -> None:
        self._source = source.strip()
        if not self._source:
            raise ValueError("환율 출처는 비어 있을 수 없습니다.")

        resolved_time = retrieved_at or datetime.now(timezone.utc)
        if resolved_time.tzinfo is None:
            raise ValueError("환율 조회 시각에는 시간대 정보가 필요합니다.")
        self._retrieved_at = resolved_time.astimezone(timezone.utc)
        self._rates: dict[tuple[str, str], Decimal] = {}

        for pair, rate in (rates or {}).items():
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("환율 키는 (기준 통화, 상대 통화) 튜플이어야 합니다.")
            self.set_rate(pair[0], pair[1], rate)

    def set_rate(self, base_currency: str, quote_currency: str, rate: Any) -> None:
        base = normalize_currency_code(base_currency, "기준 통화")
        quote = normalize_currency_code(quote_currency, "상대 통화")
        decimal_rate = to_decimal(rate, "환율")
        if decimal_rate <= 0:
            raise ValueError("환율은 0보다 커야 합니다.")
        self._rates[(base, quote)] = decimal_rate

    def get_rate(self, base_currency: str, quote_currency: str) -> ExchangeRate:
        base = normalize_currency_code(base_currency, "기준 통화")
        quote = normalize_currency_code(quote_currency, "상대 통화")

        if base == quote:
            rate = Decimal("1")
        elif (base, quote) in self._rates:
            rate = self._rates[(base, quote)]
        elif (quote, base) in self._rates:
            rate = Decimal("1") / self._rates[(quote, base)]
        else:
            raise ExchangeRateNotFoundError(
                f"{base}/{quote} 환율을 찾을 수 없습니다."
            )

        return ExchangeRate(
            base_currency=base,
            quote_currency=quote,
            rate=rate,
            retrieved_at=self._retrieved_at,
            source=self._source,
        )
