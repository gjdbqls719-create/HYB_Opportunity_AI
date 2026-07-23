from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import requests

from services.currency import (
    ExchangeRateNotFoundError,
    ExchangeRateProviderError,
    FrankfurterExchangeRateProvider,
)


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        *,
        status_error: requests.RequestException | None = None,
        json_error: ValueError | None = None,
    ) -> None:
        self._payload = payload
        self._status_error = status_error
        self._json_error = json_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.error: requests.RequestException | None = None

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {"url": url, "params": params, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_frankfurter_provider_returns_latest_rate() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "amount": 1.0,
                "base": "USD",
                "date": "2026-07-23",
                "rates": {"KRW": 1382.45},
            }
        )
    )
    provider = FrankfurterExchangeRateProvider(
        session=session,
        timeout=3.5,
    )

    rate = provider.get_rate(" usd ", "krw")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == Decimal("1382.45")
    assert rate.retrieved_at.isoformat() == "2026-07-23T00:00:00+00:00"
    assert rate.source == "frankfurter"
    assert session.calls == [
        {
            "url": "https://api.frankfurter.dev/v1/latest",
            "params": {"base": "USD", "symbols": "KRW"},
            "timeout": 3.5,
        }
    ]


def test_frankfurter_provider_identity_rate_skips_network() -> None:
    session = FakeSession()
    provider = FrankfurterExchangeRateProvider(session=session)

    rate = provider.get_rate("EUR", "eur")

    assert rate.rate == Decimal("1")
    assert rate.source == "frankfurter:identity"
    assert session.calls == []


def test_frankfurter_provider_raises_when_pair_is_missing() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "base": "USD",
                "date": "2026-07-23",
                "rates": {},
            }
        )
    )
    provider = FrankfurterExchangeRateProvider(session=session)

    with pytest.raises(ExchangeRateNotFoundError, match="USD/KRW"):
        provider.get_rate("USD", "KRW")


def test_frankfurter_provider_wraps_network_error() -> None:
    session = FakeSession()
    session.error = requests.Timeout("timed out")
    provider = FrankfurterExchangeRateProvider(session=session)

    with pytest.raises(ExchangeRateProviderError, match="API 호출"):
        provider.get_rate("USD", "KRW")


def test_frankfurter_provider_rejects_invalid_json() -> None:
    session = FakeSession(
        FakeResponse({}, json_error=ValueError("invalid json"))
    )
    provider = FrankfurterExchangeRateProvider(session=session)

    with pytest.raises(ExchangeRateProviderError, match="JSON"):
        provider.get_rate("USD", "KRW")


def test_frankfurter_provider_rejects_invalid_rate_date() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "base": "USD",
                "date": "23-07-2026",
                "rates": {"KRW": 1382.45},
            }
        )
    )
    provider = FrankfurterExchangeRateProvider(session=session)

    with pytest.raises(ExchangeRateProviderError, match="기준일 형식"):
        provider.get_rate("USD", "KRW")


def test_frankfurter_provider_validates_configuration() -> None:
    with pytest.raises(ValueError, match="API 주소"):
        FrankfurterExchangeRateProvider(base_url="  ")

    with pytest.raises(ValueError, match="timeout"):
        FrankfurterExchangeRateProvider(timeout=0)
