from __future__ import annotations

from app.models import Product
from market_data.price_snapshot import PriceSnapshot
from storage.price_history import PriceHistoryRepository


class PriceHistoryObservationRecorder:
    """현재 가격 관측을 기존 append-only Price History에 기록한다."""

    def __init__(self, *, repository: PriceHistoryRepository) -> None:
        if not isinstance(repository, PriceHistoryRepository):
            raise TypeError(
                "repository는 PriceHistoryRepository여야 합니다."
            )

        self._repository = repository

    def record_observation(
        self,
        *,
        product: Product,
        snapshot: PriceSnapshot,
    ) -> int:
        if not isinstance(product, Product):
            raise TypeError("product는 Product여야 합니다.")
        if not isinstance(snapshot, PriceSnapshot):
            raise TypeError("snapshot은 PriceSnapshot이어야 합니다.")

        return self._repository.save_product_price(
            product,
            observed_at=snapshot.observed_at,
            canonical_product_id=snapshot.canonical_product_id,
            seller_id=snapshot.seller_id,
        )
