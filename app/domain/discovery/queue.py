from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol

from app.models import Product


ProductIdentityResolver = Callable[[Product], str]


class OpportunityQueue(Protocol):
    """Discovery 분석 대기열이 따라야 하는 최소 규약."""

    def enqueue(self, product: Product) -> bool:
        """새 상품이면 추가하고 True, 중복이면 False를 반환한다."""
        ...

    def dequeue(self) -> Product | None:
        """다음 상품을 반환하며, 비어 있으면 None을 반환한다."""
        ...

    def clear(self) -> None:
        """대기열과 중복 추적 상태를 모두 비운다."""
        ...

    def __len__(self) -> int:
        ...


def default_product_identity(product: Product) -> str:
    """Strong Identity가 연결되기 전까지 사용하는 안전한 기본 식별 규칙."""
    marketplace = product.marketplace.strip().lower()
    item_id = product.item_id.strip()

    if item_id:
        return f"{marketplace}:{item_id}"

    url = product.url.strip()

    if url:
        return f"{marketplace}:{url}"

    return f"{marketplace}:{product.title.strip().lower()}"


class InMemoryOpportunityQueue:
    """단일 실행 세션용 FIFO 대기열과 중복 제거 구현."""

    def __init__(
        self,
        *,
        identity_resolver: ProductIdentityResolver = default_product_identity,
    ) -> None:
        self._items: deque[Product] = deque()
        self._queued_keys: set[str] = set()
        self._identity_resolver = identity_resolver

    def enqueue(self, product: Product) -> bool:
        key = self._identity_resolver(product)

        if not key:
            raise ValueError("상품 식별 키는 비어 있을 수 없습니다.")

        if key in self._queued_keys:
            return False

        self._items.append(product)
        self._queued_keys.add(key)
        return True

    def dequeue(self) -> Product | None:
        if not self._items:
            return None

        product = self._items.popleft()
        self._queued_keys.discard(
            self._identity_resolver(product)
        )
        return product

    def clear(self) -> None:
        self._items.clear()
        self._queued_keys.clear()

    def __len__(self) -> int:
        return len(self._items)
