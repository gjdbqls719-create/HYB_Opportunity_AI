from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable

from services.currency.models import ExchangeRate, normalize_currency_code
from services.currency.provider import ExchangeRateProvider


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class CachedExchangeRate:
    """캐시에 저장된 환율과 만료 시각."""

    exchange_rate: ExchangeRate
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("환율 캐시 만료 시각에는 시간대 정보가 필요합니다.")
        object.__setattr__(
            self,
            "expires_at",
            self.expires_at.astimezone(timezone.utc),
        )

    def is_expired(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("현재 시각에는 시간대 정보가 필요합니다.")
        return now.astimezone(timezone.utc) >= self.expires_at


class CachedExchangeRateProvider(ExchangeRateProvider):
    """다른 환율 Provider의 결과를 메모리에 일정 시간 보관한다.

    동일 통화쌍의 반복 요청은 TTL 동안 원본 Provider를 다시 호출하지 않는다.
    역방향 환율도 함께 저장해 USD/KRW 조회 후 KRW/USD 조회가 추가 호출 없이
    처리되도록 한다.
    """

    def __init__(
        self,
        provider: ExchangeRateProvider,
        *,
        ttl: timedelta = timedelta(hours=1),
        clock: Clock | None = None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("환율 캐시 TTL은 0보다 커야 합니다.")

        self._provider = provider
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: dict[tuple[str, str], CachedExchangeRate] = {}
        self._lock = RLock()

    def get_rate(self, base_currency: str, quote_currency: str) -> ExchangeRate:
        base = normalize_currency_code(base_currency, "기준 통화")
        quote = normalize_currency_code(quote_currency, "상대 통화")
        now = self._now()
        key = (base, quote)

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and not cached.is_expired(now):
                return cached.exchange_rate

            exchange_rate = self._provider.get_rate(base, quote)
            expires_at = now + self._ttl
            self._store(exchange_rate, expires_at)
            return exchange_rate

    def clear(self) -> None:
        """저장된 모든 환율 캐시를 제거한다."""
        with self._lock:
            self._cache.clear()

    def invalidate(self, base_currency: str, quote_currency: str) -> None:
        """지정한 통화쌍과 역방향 통화쌍의 캐시를 제거한다."""
        base = normalize_currency_code(base_currency, "기준 통화")
        quote = normalize_currency_code(quote_currency, "상대 통화")

        with self._lock:
            self._cache.pop((base, quote), None)
            self._cache.pop((quote, base), None)

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime):
            raise TypeError("환율 캐시 clock은 datetime을 반환해야 합니다.")
        if now.tzinfo is None:
            raise ValueError("환율 캐시 clock 시각에는 시간대 정보가 필요합니다.")
        return now.astimezone(timezone.utc)

    def _store(self, exchange_rate: ExchangeRate, expires_at: datetime) -> None:
        direct = CachedExchangeRate(
            exchange_rate=exchange_rate,
            expires_at=expires_at,
        )
        inverse = CachedExchangeRate(
            exchange_rate=exchange_rate.inverse(),
            expires_at=expires_at,
        )

        self._cache[
            (exchange_rate.base_currency, exchange_rate.quote_currency)
        ] = direct
        self._cache[
            (exchange_rate.quote_currency, exchange_rate.base_currency)
        ] = inverse
