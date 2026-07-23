from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.currency import (
    CachedExchangeRateProvider,
    MockExchangeRateProvider,
)


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class CountingProvider(MockExchangeRateProvider):
    def __init__(self) -> None:
        super().__init__({("USD", "KRW"): "1400"})
        self.call_count = 0

    def get_rate(self, base_currency: str, quote_currency: str):
        self.call_count += 1
        return super().get_rate(base_currency, quote_currency)


def test_cached_provider_reuses_rate_before_expiration() -> None:
    provider = CountingProvider()
    cached = CachedExchangeRateProvider(provider)

    first = cached.get_rate("USD", "KRW")
    second = cached.get_rate("usd", "krw")

    assert first is second
    assert provider.call_count == 1
    assert cached.cache_size == 2


def test_cached_provider_stores_inverse_rate() -> None:
    provider = CountingProvider()
    cached = CachedExchangeRateProvider(provider)

    cached.get_rate("USD", "KRW")
    inverse = cached.get_rate("KRW", "USD")

    assert inverse.rate == Decimal("1") / Decimal("1400")
    assert provider.call_count == 1


def test_cached_provider_refreshes_expired_rate() -> None:
    clock = MutableClock(datetime(2026, 7, 24, tzinfo=timezone.utc))
    provider = CountingProvider()
    cached = CachedExchangeRateProvider(
        provider,
        ttl=timedelta(minutes=30),
        clock=clock,
    )

    cached.get_rate("USD", "KRW")
    clock.advance(timedelta(minutes=31))
    cached.get_rate("USD", "KRW")

    assert provider.call_count == 2


def test_cached_provider_invalidate_removes_both_directions() -> None:
    provider = CountingProvider()
    cached = CachedExchangeRateProvider(provider)

    cached.get_rate("USD", "KRW")
    cached.invalidate("USD", "KRW")

    assert cached.cache_size == 0

    cached.get_rate("KRW", "USD")
    assert provider.call_count == 2


def test_cached_provider_clear_removes_all_rates() -> None:
    provider = CountingProvider()
    cached = CachedExchangeRateProvider(provider)

    cached.get_rate("USD", "KRW")
    cached.clear()

    assert cached.cache_size == 0


def test_cached_provider_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValueError, match="TTL"):
        CachedExchangeRateProvider(
            CountingProvider(),
            ttl=timedelta(0),
        )


def test_cached_provider_requires_timezone_aware_clock() -> None:
    cached = CachedExchangeRateProvider(
        CountingProvider(),
        clock=lambda: datetime(2026, 7, 24),
    )

    with pytest.raises(ValueError, match="시간대"):
        cached.get_rate("USD", "KRW")
