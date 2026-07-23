from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.currency import (
    CurrencyConverter,
    ExchangeRate,
    ExchangeRateNotFoundError,
    MockExchangeRateProvider,
)


FIXED_TIME = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)


def test_exchange_rate_normalizes_currency_codes() -> None:
    rate = ExchangeRate(" usd ", "krw", Decimal("1380.5"), FIXED_TIME, "test")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.pair == "USD/KRW"
    assert rate.rate == Decimal("1380.5")


def test_exchange_rate_rejects_invalid_code() -> None:
    with pytest.raises(ValueError, match="3자리 영문 코드"):
        ExchangeRate("US", "KRW", Decimal("1380"), FIXED_TIME, "test")


def test_exchange_rate_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="0보다 커야"):
        ExchangeRate("USD", "KRW", Decimal("0"), FIXED_TIME, "test")


def test_exchange_rate_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="시간대 정보"):
        ExchangeRate("USD", "KRW", Decimal("1380"), datetime(2026, 7, 24), "test")


def test_exchange_rate_can_create_inverse() -> None:
    rate = ExchangeRate("USD", "KRW", Decimal("1400"), FIXED_TIME, "test")

    inverse = rate.inverse()

    assert inverse.pair == "KRW/USD"
    assert inverse.rate == Decimal("1") / Decimal("1400")


def test_mock_provider_returns_configured_rate() -> None:
    provider = MockExchangeRateProvider(
        {("USD", "KRW"): "1385.25"}, retrieved_at=FIXED_TIME
    )

    rate = provider.get_rate("usd", "krw")

    assert rate.rate == Decimal("1385.25")
    assert rate.source == "mock"
    assert rate.retrieved_at == FIXED_TIME


def test_mock_provider_resolves_inverse_rate() -> None:
    provider = MockExchangeRateProvider(
        {("USD", "KRW"): "1400"}, retrieved_at=FIXED_TIME
    )

    rate = provider.get_rate("KRW", "USD")

    assert rate.rate == Decimal("1") / Decimal("1400")


def test_mock_provider_returns_identity_rate() -> None:
    provider = MockExchangeRateProvider(retrieved_at=FIXED_TIME)

    rate = provider.get_rate("KRW", "krw")

    assert rate.rate == Decimal("1")


def test_mock_provider_raises_for_unknown_pair() -> None:
    provider = MockExchangeRateProvider(retrieved_at=FIXED_TIME)

    with pytest.raises(ExchangeRateNotFoundError, match="USD/EUR"):
        provider.get_rate("USD", "EUR")


def test_converter_converts_and_rounds_money() -> None:
    provider = MockExchangeRateProvider(
        {("USD", "KRW"): "1385.25"}, retrieved_at=FIXED_TIME
    )
    converter = CurrencyConverter(provider)

    result = converter.convert("19.99", "USD", "KRW")

    assert result == Decimal("27691.15")


def test_converter_can_return_unrounded_decimal() -> None:
    provider = MockExchangeRateProvider(
        {("USD", "KRW"): "1385.25"}, retrieved_at=FIXED_TIME
    )
    converter = CurrencyConverter(provider)

    result = converter.convert("19.99", "USD", "KRW", quantum=None)

    assert result == Decimal("19.99") * Decimal("1385.25")


def test_converter_rejects_invalid_quantum() -> None:
    converter = CurrencyConverter(MockExchangeRateProvider(retrieved_at=FIXED_TIME))

    with pytest.raises(ValueError, match="반올림 단위"):
        converter.convert(100, "KRW", "KRW", quantum=0)
