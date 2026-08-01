from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    DEFAULT = "default"
    CALCULATED = "calculated"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class EconomicEvidence:
    status: EvidenceStatus
    source: str
    observed_at: datetime | None = None
    reference: str | None = None

    def __post_init__(self) -> None:
        try:
            status = EvidenceStatus(self.status)
        except ValueError as error:
            raise ValueError("지원하지 않는 경제 증거 상태입니다.") from error

        source = self.source.strip()
        if not source:
            raise ValueError("경제 증거 출처는 비어 있을 수 없습니다.")

        if self.observed_at is not None:
            if not isinstance(self.observed_at, datetime):
                raise TypeError("observed_at은 datetime이어야 합니다.")
            if self.observed_at.tzinfo is None:
                raise ValueError("observed_at에는 시간대 정보가 필요합니다.")
            object.__setattr__(
                self,
                "observed_at",
                self.observed_at.astimezone(timezone.utc),
            )

        reference = (
            self.reference.strip()
            if self.reference is not None
            else None
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "reference", reference or None)


@dataclass(frozen=True, slots=True)
class MoneyInput:
    amount: Decimal | None
    currency: str
    evidence: EconomicEvidence

    def __post_init__(self) -> None:
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency는 3자리 영문 코드여야 합니다.")
        if not isinstance(self.evidence, EconomicEvidence):
            raise TypeError("evidence는 EconomicEvidence여야 합니다.")

        amount = _optional_decimal(self.amount, "amount")
        absent = self.evidence.status in {
            EvidenceStatus.MISSING,
            EvidenceStatus.UNSUPPORTED,
        }
        if absent and amount is not None:
            raise ValueError("missing/unsupported 금액에는 값이 없어야 합니다.")
        if not absent and amount is None:
            raise ValueError("경제 금액 상태에는 값이 필요합니다.")
        if (
            amount is not None
            and amount < 0
            and self.evidence.status is not EvidenceStatus.CALCULATED
        ):
            raise ValueError("경제 금액은 0 이상이어야 합니다.")

        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)


@dataclass(frozen=True, slots=True)
class RateInput:
    rate: Decimal | None
    evidence: EconomicEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, EconomicEvidence):
            raise TypeError("evidence는 EconomicEvidence여야 합니다.")

        rate = _optional_decimal(self.rate, "rate")
        absent = self.evidence.status in {
            EvidenceStatus.MISSING,
            EvidenceStatus.UNSUPPORTED,
        }
        if absent and rate is not None:
            raise ValueError("missing/unsupported 비율에는 값이 없어야 합니다.")
        if not absent and rate is None:
            raise ValueError("경제 비율 상태에는 값이 필요합니다.")
        if rate is not None and rate < 0:
            raise ValueError("경제 비율은 0 이상이어야 합니다.")

        object.__setattr__(self, "rate", rate)


@dataclass(frozen=True, slots=True)
class VerifiedEconomicsInput:
    purchase_cost: MoneyInput
    shipping_cost: MoneyInput
    marketplace_fee_rate: RateInput
    payment_fee_rate: RateInput
    fixed_fee: MoneyInput
    tax_rate: RateInput
    duty_cost: MoneyInput
    other_cost: MoneyInput
    expected_sale_price: MoneyInput

    def __post_init__(self) -> None:
        money_fields = (
            "purchase_cost",
            "shipping_cost",
            "fixed_fee",
            "duty_cost",
            "other_cost",
            "expected_sale_price",
        )
        currencies = set()
        for field_name in money_fields:
            value = getattr(self, field_name)
            if not isinstance(value, MoneyInput):
                raise TypeError(f"{field_name}는 MoneyInput이어야 합니다.")
            currencies.add(value.currency)
        if len(currencies) != 1:
            raise ValueError("모든 경제 금액은 동일한 통화여야 합니다.")

        for field_name in (
            "marketplace_fee_rate",
            "payment_fee_rate",
            "tax_rate",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, RateInput):
                raise TypeError(f"{field_name}는 RateInput이어야 합니다.")
            if value.rate is not None and value.rate > Decimal("1"):
                raise ValueError(f"{field_name}는 1 이하여야 합니다.")

    @property
    def currency(self) -> str:
        return self.purchase_cost.currency

    @property
    def readiness_missing_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        required_values = (
            ("purchase_price", self.purchase_cost, False),
            ("shipping_cost", self.shipping_cost, True),
            ("expected_selling_price", self.expected_sale_price, False),
            ("marketplace_fee_rate", self.marketplace_fee_rate, True),
            ("payment_fee_rate", self.payment_fee_rate, True),
            ("fixed_fee", self.fixed_fee, True),
        )
        for field_name, value, requires_verified in required_values:
            evidence = value.evidence
            numeric_value = (
                value.amount
                if isinstance(value, MoneyInput)
                else value.rate
            )
            if numeric_value is None or evidence.status in {
                EvidenceStatus.MISSING,
                EvidenceStatus.UNSUPPORTED,
            }:
                missing.append(field_name)
            elif requires_verified and evidence.status is not EvidenceStatus.VERIFIED:
                missing.append(field_name)
        return tuple(missing)

    @property
    def is_ready(self) -> bool:
        return not self.readiness_missing_fields


@dataclass(frozen=True, slots=True)
class EconomicsCalculation:
    inputs: VerifiedEconomicsInput
    marketplace_fee: MoneyInput
    payment_fee: MoneyInput
    tax_cost: MoneyInput
    landed_cost: MoneyInput
    selling_cost: MoneyInput
    total_cost: MoneyInput
    net_profit: MoneyInput
    roi: Decimal
    landed_cost_roi: Decimal
    margin_rate: Decimal
    analysis: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, VerifiedEconomicsInput):
            raise TypeError("inputs는 VerifiedEconomicsInput이어야 합니다.")
        for field_name in (
            "marketplace_fee",
            "payment_fee",
            "tax_cost",
            "landed_cost",
            "selling_cost",
            "total_cost",
            "net_profit",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, MoneyInput):
                raise TypeError(f"{field_name}는 MoneyInput이어야 합니다.")
            if value.currency != self.inputs.currency:
                raise ValueError("계산 결과 통화는 입력 통화와 같아야 합니다.")
        for field_name in ("roi", "landed_cost_roi", "margin_rate"):
            object.__setattr__(
                self,
                field_name,
                _decimal(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "analysis", MappingProxyType(dict(self.analysis)))


def _optional_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, field_name)


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}는 숫자여야 합니다.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name}는 숫자여야 합니다.") from error
    if not result.is_finite():
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")
    return result
