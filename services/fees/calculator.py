from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import (
    FeeBreakdown,
    FeeProfile,
    quantize_money,
    to_decimal,
)
from .profiles import get_fee_profile


class MarketplaceFeeCalculator:
    """
    판매가와 마켓플레이스 수수료 규칙을 기준으로
    수수료 상세 내역을 계산한다.
    """

    def calculate(
        self,
        marketplace: str,
        selling_price: Any,
        *,
        marketplace_fee_rate: Any | None = None,
        payment_fee_rate: Any | None = None,
        fixed_fee: Any | None = None,
    ) -> FeeBreakdown:
        """
        수수료를 계산한다.

        재정의 값이 하나라도 전달되면 source는 override가 된다.
        전달되지 않은 값은 해당 마켓플레이스 프로필 값을 사용한다.
        """
        profile = get_fee_profile(marketplace)

        normalized_selling_price = to_decimal(
            selling_price,
            "판매가",
        )

        if normalized_selling_price < 0:
            raise ValueError(
                "판매가는 0 이상이어야 합니다."
            )

        has_override = any(
            value is not None
            for value in (
                marketplace_fee_rate,
                payment_fee_rate,
                fixed_fee,
            )
        )

        resolved_profile = self._resolve_profile(
            profile=profile,
            marketplace_fee_rate=marketplace_fee_rate,
            payment_fee_rate=payment_fee_rate,
            fixed_fee=fixed_fee,
        )

        marketplace_fee = quantize_money(
            normalized_selling_price
            * resolved_profile.marketplace_fee_rate
        )

        payment_fee = quantize_money(
            normalized_selling_price
            * resolved_profile.payment_fee_rate
        )

        total_fee = quantize_money(
            marketplace_fee
            + payment_fee
            + resolved_profile.fixed_fee
        )

        return FeeBreakdown(
            marketplace=resolved_profile.marketplace,
            selling_price=normalized_selling_price,
            marketplace_fee_rate=(
                resolved_profile.marketplace_fee_rate
            ),
            payment_fee_rate=(
                resolved_profile.payment_fee_rate
            ),
            fixed_fee=resolved_profile.fixed_fee,
            marketplace_fee=marketplace_fee,
            payment_fee=payment_fee,
            total_fee=total_fee,
            source=(
                "override"
                if has_override
                else "profile"
            ),
        )

    def _resolve_profile(
        self,
        *,
        profile: FeeProfile,
        marketplace_fee_rate: Any | None,
        payment_fee_rate: Any | None,
        fixed_fee: Any | None,
    ) -> FeeProfile:
        """
        기본 프로필과 선택적 재정의 값을 합쳐
        실제 계산에 사용할 프로필을 만든다.
        """
        return FeeProfile(
            marketplace=profile.marketplace,
            marketplace_fee_rate=(
                profile.marketplace_fee_rate
                if marketplace_fee_rate is None
                else to_decimal(
                    marketplace_fee_rate,
                    "마켓플레이스 수수료율",
                )
            ),
            payment_fee_rate=(
                profile.payment_fee_rate
                if payment_fee_rate is None
                else to_decimal(
                    payment_fee_rate,
                    "결제 수수료율",
                )
            ),
            fixed_fee=(
                profile.fixed_fee
                if fixed_fee is None
                else to_decimal(
                    fixed_fee,
                    "고정 수수료",
                )
            ),
        )


def calculate_marketplace_fee(
    marketplace: str,
    selling_price: Any,
    *,
    marketplace_fee_rate: Any | None = None,
    payment_fee_rate: Any | None = None,
    fixed_fee: Any | None = None,
) -> FeeBreakdown:
    """
    클래스 생성 없이 사용할 수 있는 편의 함수.
    """
    calculator = MarketplaceFeeCalculator()

    return calculator.calculate(
        marketplace=marketplace,
        selling_price=selling_price,
        marketplace_fee_rate=marketplace_fee_rate,
        payment_fee_rate=payment_fee_rate,
        fixed_fee=fixed_fee,
    )