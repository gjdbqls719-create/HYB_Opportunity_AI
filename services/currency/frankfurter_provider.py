from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any, Protocol

import requests

from services.currency.models import (
    ExchangeRate,
    normalize_currency_code,
    to_decimal,
)
from services.currency.provider import (
    ExchangeRateNotFoundError,
    ExchangeRateProvider,
)


DEFAULT_FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


class HTTPSession(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> Any:
        ...


class ExchangeRateProviderError(RuntimeError):
    """외부 환율 서비스 호출 또는 응답 처리에 실패했을 때 발생한다."""


class FrankfurterExchangeRateProvider(ExchangeRateProvider):
    """Frankfurter v1 API에서 최신 기준 환율을 조회한다.

    네트워크 호출은 ``session``으로 주입할 수 있어 테스트에서 실제 API를
    호출하지 않는다. 동일 통화쌍은 외부 호출 없이 1:1 환율을 반환한다.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_FRANKFURTER_BASE_URL,
        timeout: float = 10.0,
        session: HTTPSession | None = None,
    ) -> None:
        cleaned_base_url = base_url.strip().rstrip("/")
        if not cleaned_base_url:
            raise ValueError("Frankfurter API 주소는 비어 있을 수 없습니다.")
        if timeout <= 0:
            raise ValueError("환율 API timeout은 0보다 커야 합니다.")

        self._base_url = cleaned_base_url
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def get_rate(self, base_currency: str, quote_currency: str) -> ExchangeRate:
        base = normalize_currency_code(base_currency, "기준 통화")
        quote = normalize_currency_code(quote_currency, "상대 통화")

        if base == quote:
            return ExchangeRate(
                base_currency=base,
                quote_currency=quote,
                rate=Decimal("1"),
                retrieved_at=datetime.now(timezone.utc),
                source="frankfurter:identity",
            )

        try:
            response = self._session.get(
                f"{self._base_url}/latest",
                params={"base": base, "symbols": quote},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise ExchangeRateProviderError(
                f"Frankfurter 환율 API 호출에 실패했습니다: {error}"
            ) from error
        except ValueError as error:
            raise ExchangeRateProviderError(
                "Frankfurter 환율 API가 올바른 JSON을 반환하지 않았습니다."
            ) from error

        return self._parse_response(
            payload,
            requested_base=base,
            requested_quote=quote,
        )

    @staticmethod
    def _parse_response(
        payload: Any,
        *,
        requested_base: str,
        requested_quote: str,
    ) -> ExchangeRate:
        if not isinstance(payload, dict):
            raise ExchangeRateProviderError(
                "Frankfurter 환율 응답 형식이 올바르지 않습니다."
            )

        response_base = normalize_currency_code(
            str(payload.get("base", requested_base)),
            "응답 기준 통화",
        )
        if response_base != requested_base:
            raise ExchangeRateProviderError(
                "Frankfurter 응답의 기준 통화가 요청과 일치하지 않습니다."
            )

        rates = payload.get("rates")
        if not isinstance(rates, dict) or requested_quote not in rates:
            raise ExchangeRateNotFoundError(
                f"{requested_base}/{requested_quote} 환율을 찾을 수 없습니다."
            )

        rate = to_decimal(rates[requested_quote], "Frankfurter 환율")
        if rate <= 0:
            raise ExchangeRateProviderError(
                "Frankfurter 환율은 0보다 커야 합니다."
            )

        raw_date = payload.get("date")
        if not isinstance(raw_date, str):
            raise ExchangeRateProviderError(
                "Frankfurter 응답에 환율 기준일이 없습니다."
            )

        try:
            rate_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as error:
            raise ExchangeRateProviderError(
                "Frankfurter 환율 기준일 형식이 올바르지 않습니다."
            ) from error

        return ExchangeRate(
            base_currency=requested_base,
            quote_currency=requested_quote,
            rate=rate,
            retrieved_at=datetime.combine(
                rate_date,
                time.min,
                tzinfo=timezone.utc,
            ),
            source="frankfurter",
        )
