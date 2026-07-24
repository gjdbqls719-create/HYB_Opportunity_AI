from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


MONEY_QUANTUM = Decimal("0.01")


def to_decimal(
    value: Any,
    field_name: str,
) -> Decimal:
    """
    숫자 입력을 Decimal로 안전하게 변환한다.
    """
    try:
        return Decimal(str(value))
    except Exception as error:
        raise ValueError(
            f"{field_name}은(는) 숫자여야 합니다."
        ) from error


def quantize_money(value: Decimal) -> Decimal:
    """
    금액을 소수점 둘째 자리까지 반올림한다.
    """
    return value.quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


@dataclass(frozen=True, slots=True)
class FeeProfile:
    """
    마켓플레이스별 기본 수수료 규칙.

    모든 비율은 0.15와 같은 0~1 사이 소수로 저장한다.
    """

    marketplace: str
    marketplace_fee_rate: Decimal
    payment_fee_rate: Decimal = Decimal("0")
    fixed_fee: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        marketplace = self.marketplace.strip().lower()

        if not marketplace:
            raise ValueError(
                "마켓플레이스 이름은 비어 있을 수 없습니다."
            )

        marketplace_fee_rate = to_decimal(
            self.marketplace_fee_rate,
            "마켓플레이스 수수료율",
        )
        payment_fee_rate = to_decimal(
            self.payment_fee_rate,
            "결제 수수료율",
        )
        fixed_fee = to_decimal(
            self.fixed_fee,
            "고정 수수료",
        )

        for rate, field_name in (
            (
                marketplace_fee_rate,
                "마켓플레이스 수수료율",
            ),
            (
                payment_fee_rate,
                "결제 수수료율",
            ),
        ):
            if not Decimal("0") <= rate <= Decimal("1"):
                raise ValueError(
                    f"{field_name}은(는) "
                    "0 이상 1 이하여야 합니다."
                )

        if fixed_fee < 0:
            raise ValueError(
                "고정 수수료는 0 이상이어야 합니다."
            )

        object.__setattr__(
            self,
            "marketplace",
            marketplace,
        )
        object.__setattr__(
            self,
            "marketplace_fee_rate",
            marketplace_fee_rate,
        )
        object.__setattr__(
            self,
            "payment_fee_rate",
            payment_fee_rate,
        )
        object.__setattr__(
            self,
            "fixed_fee",
            quantize_money(fixed_fee),
        )


@dataclass(frozen=True, slots=True)
class FeeBreakdown:
    """
    판매가를 기준으로 계산된 수수료 상세 결과.
    """

    marketplace: str
    selling_price: Decimal

    marketplace_fee_rate: Decimal
    payment_fee_rate: Decimal
    fixed_fee: Decimal

    marketplace_fee: Decimal
    payment_fee: Decimal
    total_fee: Decimal

    source: str

    def __post_init__(self) -> None:
        marketplace = self.marketplace.strip().lower()
        source = self.source.strip().lower()

        if not marketplace:
            raise ValueError(
                "마켓플레이스 이름은 비어 있을 수 없습니다."
            )

        if source not in {"profile", "override"}:
            raise ValueError(
                "수수료 출처는 profile 또는 "
                "override여야 합니다."
            )

        decimal_fields = {
            "selling_price": (
                self.selling_price,
                "판매가",
            ),
            "marketplace_fee_rate": (
                self.marketplace_fee_rate,
                "마켓플레이스 수수료율",
            ),
            "payment_fee_rate": (
                self.payment_fee_rate,
                "결제 수수료율",
            ),
            "fixed_fee": (
                self.fixed_fee,
                "고정 수수료",
            ),
            "marketplace_fee": (
                self.marketplace_fee,
                "마켓플레이스 수수료",
            ),
            "payment_fee": (
                self.payment_fee,
                "결제 수수료",
            ),
            "total_fee": (
                self.total_fee,
                "총수수료",
            ),
        }

        converted: dict[str, Decimal] = {}

        for attribute, (
            raw_value,
            field_name,
        ) in decimal_fields.items():
            value = to_decimal(
                raw_value,
                field_name,
            )

            if value < 0:
                raise ValueError(
                    f"{field_name}은(는) "
                    "0 이상이어야 합니다."
                )

            converted[attribute] = value

        for attribute in (
            "marketplace_fee_rate",
            "payment_fee_rate",
        ):
            if converted[attribute] > Decimal("1"):
                field_name = (
                    "마켓플레이스 수수료율"
                    if attribute
                    == "marketplace_fee_rate"
                    else "결제 수수료율"
                )

                raise ValueError(
                    f"{field_name}은(는) "
                    "0 이상 1 이하여야 합니다."
                )

        object.__setattr__(
            self,
            "marketplace",
            marketplace,
        )
        object.__setattr__(
            self,
            "source",
            source,
        )

        for attribute, value in converted.items():
            if attribute in {
                "selling_price",
                "fixed_fee",
                "marketplace_fee",
                "payment_fee",
                "total_fee",
            }:
                value = quantize_money(value)

            object.__setattr__(
                self,
                attribute,
                value,
            )

    @property
    def total_fee_rate(self) -> Decimal:
        """
        변동 수수료율 합계.
        고정 수수료는 포함하지 않는다.
        """
        return (
            self.marketplace_fee_rate
            + self.payment_fee_rate
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Opportunity 분석 결과에 넣기 쉬운 dict로 변환한다.
        """
        return {
            "fee_marketplace": self.marketplace,
            "marketplace_fee_rate": float(
                self.marketplace_fee_rate
            ),
            "payment_fee_rate": float(
                self.payment_fee_rate
            ),
            "fixed_fee": float(self.fixed_fee),
            "marketplace_fee": float(
                self.marketplace_fee
            ),
            "payment_fee": float(
                self.payment_fee
            ),
            "total_fee": float(self.total_fee),
            "total_fee_rate": float(
                self.total_fee_rate
            ),
            "fee_source": self.source,
        }