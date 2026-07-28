from __future__ import annotations

from dataclasses import dataclass

from market_data.snapshot import BaseSnapshot


@dataclass(frozen=True, slots=True)
class SellerSnapshot(BaseSnapshot):
    """
    특정 Marketplace 상품의
    특정 시점 판매자 상태 Snapshot.

    Snapshot은 생성 후 변경되지 않는다.
    판매자 정보 변화는 새로운 Snapshot 추가로 기록한다.
    """

    item_id: str

    seller_id: str | None

    seller_rating: float | None = None

    seller_review_count: int | None = None

    seller_count: int = 1

    is_verified: bool = False

    def __post_init__(self) -> None:
        BaseSnapshot.__post_init__(self)

        object.__setattr__(
            self,
            "item_id",
            self.item_id.strip(),
        )

        if self.seller_id is not None:
            object.__setattr__(
                self,
                "seller_id",
                self.seller_id.strip() or None,
            )

        if not self.item_id:
            raise ValueError(
                "Item ID는 비어 있을 수 없습니다."
            )

        if (
            self.seller_rating is not None
            and not 0 <= self.seller_rating <= 5
        ):
            raise ValueError(
                "판매자 평점은 0에서 5 사이여야 합니다."
            )

        if (
            self.seller_review_count is not None
            and self.seller_review_count < 0
        ):
            raise ValueError(
                "판매자 리뷰 수는 0 이상이어야 합니다."
            )

        if self.seller_count < 0:
            raise ValueError(
                "판매자 수는 0 이상이어야 합니다."
            )

        if not isinstance(
            self.is_verified,
            bool,
        ):
            raise TypeError(
                "is_verified는 bool이어야 합니다."
            )