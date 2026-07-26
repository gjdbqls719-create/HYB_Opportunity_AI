from __future__ import annotations

from dataclasses import dataclass

from market_data.snapshot import BaseSnapshot


@dataclass(frozen=True, slots=True)
class InventorySnapshot(BaseSnapshot):
    """
    특정 Marketplace 상품의
    특정 시점 재고 상태 Snapshot.

    Snapshot은 생성 후 변경되지 않는다.
    재고 변화는 새로운 Snapshot 추가로 기록한다.
    """

    item_id: str

    available: bool

    quantity: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()

        object.__setattr__(
            self,
            "item_id",
            self.item_id.strip(),
        )

        if not self.item_id:
            raise ValueError(
                "Item ID는 비어 있을 수 없습니다."
            )

        if self.quantity is not None:
            if self.quantity < 0:
                raise ValueError(
                    "재고 수량은 0 이상이어야 합니다."
                )

        if not isinstance(
            self.available,
            bool,
        ):
            raise TypeError(
                "available은 bool이어야 합니다."
            )

        if (
            self.available
            and self.quantity == 0
        ):
            raise ValueError(
                "재고 있음 상태에서 "
                "수량은 0일 수 없습니다."
            )