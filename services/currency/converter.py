from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.currency.models import ExchangeRate, normalize_currency_code, to_decimal
from services.currency.provider import ExchangeRateProvider


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """환전 결과와 계산에 사용한 환율 정보를 함께 보관한다."""

    original_amount: Decimal
    converted_amount: Decimal
    exchange_rate: ExchangeRate


class CurrencyConverter:
    """환율 공급자를 사용해 Decimal 기반으로 통화를 변환한다."""

    def __init__(
        self,
        provider: ExchangeRateProvider,
        *,
        quantum: Decimal | int | float | str | None = Decimal("0.01"),
        rounding: str = ROUND_HALF_UP,
    ) -> None:
        self._provider = provider
        self._quantum = self._resolve_quantum(quantum)
        self._rounding = rounding

    @staticmethod
    def _resolve_quantum(
        quantum: Decimal | int | float | str | None,
    ) -> Decimal | None:
        if quantum is None:
            return None

        resolved = to_decimal(quantum, "반올림 단위")
        if resolved <= 0:
            raise ValueError("반올림 단위는 0보다 커야 합니다.")
        return resolved

    def convert(
        self,
        amount: Any,
        from_currency: str,
        to_currency: str,
        *,
        quantum: Decimal | int | float | str | None | object = ...,
    ) -> Decimal:
        """금액을 변환한다. quantum=None이면 반올림하지 않는다."""
        return self.convert_with_details(
            amount,
            from_currency,
            to_currency,
            quantum=quantum,
        ).converted_amount

    def convert_with_details(
        self,
        amount: Any,
        from_currency: str,
        to_currency: str,
        *,
        quantum: Decimal | int | float | str | None | object = ...,
    ) -> ConversionResult:
        original_amount = to_decimal(amount, "환전 금액")
        if original_amount < 0:
            raise ValueError("환전 금액은 0 이상이어야 합니다.")

        source = normalize_currency_code(from_currency, "기준 통화")
        target = normalize_currency_code(to_currency, "상대 통화")
        exchange_rate = self._provider.get_rate(source, target)
        converted_amount = original_amount * exchange_rate.rate

        resolved_quantum = (
            self._quantum
            if quantum is ...
            else self._resolve_quantum(quantum)
        )
        if resolved_quantum is not None:
            converted_amount = converted_amount.quantize(
                resolved_quantum,
                rounding=self._rounding,
            )

        return ConversionResult(
            original_amount=original_amount,
            converted_amount=converted_amount,
            exchange_rate=exchange_rate,
        )
