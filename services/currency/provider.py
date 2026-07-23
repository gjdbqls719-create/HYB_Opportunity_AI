from __future__ import annotations

from abc import ABC, abstractmethod

from services.currency.models import ExchangeRate


class ExchangeRateNotFoundError(LookupError):
    """Provider가 요청한 통화쌍의 환율을 제공하지 못할 때 발생한다."""


class ExchangeRateProvider(ABC):
    """환율 공급자가 구현해야 하는 최소 인터페이스."""

    @abstractmethod
    def get_rate(self, base_currency: str, quote_currency: str) -> ExchangeRate:
        """기준 통화 1단위에 대한 상대 통화 환율을 반환한다."""
        raise NotImplementedError
