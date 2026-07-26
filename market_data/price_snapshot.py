from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from market_data.snapshot import BaseSnapshot


@dataclass(frozen=True, slots=True)
class PriceSnapshot(BaseSnapshot):
    """
    특정 Marketplace에서 관찰된 가격 Snapshot.

    Snapshot은 특정 시점의 가격 관찰 기록이며
    생성 후 변경되지 않는다.
    """

    item_id: str
    price: Decimal
    currency: str
    condition: str
    seller_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        
        object.__setattr__(
            self,
            "item_id",
            self.item_id.strip(),
        )

        object.__setattr__(
            self,
            "currency",
            self.currency.strip().upper(),
        )

        object.__setattr__(
            self,
            "condition",
            self.condition.strip(),
        )

        if not self.item_id:
            raise ValueError(
                "Item ID는 비어 있을 수 없습니다."
            )

        if self.price < 0:
            raise ValueError(
                "가격은 0보다 작을 수 없습니다."
            )

        if not self.currency:
            raise ValueError(
                "통화는 비어 있을 수 없습니다."
            )

        if not self.condition:
            raise ValueError(
                "상품 상태는 비어 있을 수 없습니다."
            )

        if self.seller_id is not None:
            object.__setattr__(
                self,
                "seller_id",
                self.seller_id.strip() or None,
            )