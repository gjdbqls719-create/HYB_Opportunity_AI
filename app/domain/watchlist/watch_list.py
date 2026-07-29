from __future__ import annotations

from collections.abc import Iterable

from app.domain.watchlist.models import (
    WatchIdentityStrength,
    WatchItem,
    WatchItemStatus,
)


class DuplicateWatchItemError(ValueError):
    """동일한 상품이 Watch List에 이미 존재할 때 발생한다."""


class WatchItemNotFoundError(LookupError):
    """요청한 Watch Item을 찾을 수 없을 때 발생한다."""


class WeakWatchIdentityError(ValueError):
    """약한 상품 식별자로 등록을 시도할 때 발생한다."""


class WatchList:
    """
    사용자가 지속적으로 관찰할 상품을 관리하는 Domain Aggregate.

    기본 정책에서는 Weak Identity 등록을 허용하지 않는다.
    제목만 비슷한 서로 다른 상품이 하나로 합쳐지는 오류를 막기 위함이다.
    """

    def __init__(
        self,
        items: Iterable[WatchItem] = (),
        *,
        allow_weak_identity: bool = False,
    ) -> None:
        self._items_by_watch_id: dict[str, WatchItem] = {}
        self._watch_id_by_identity: dict[str, str] = {}
        self._allow_weak_identity = allow_weak_identity

        for item in items:
            self.add(item)

    def add(self, item: WatchItem) -> None:
        """새 Watch Item을 등록한다."""
        if not isinstance(item, WatchItem):
            raise TypeError("item은 WatchItem이어야 합니다.")

        if (
            item.identity_strength is WatchIdentityStrength.WEAK
            and not self._allow_weak_identity
        ):
            raise WeakWatchIdentityError(
                "제목만으로 식별되는 상품은 Watch List에 "
                "등록할 수 없습니다."
            )

        if item.watch_id in self._items_by_watch_id:
            raise DuplicateWatchItemError(
                f"이미 존재하는 watch_id입니다: {item.watch_id}"
            )

        existing_watch_id = self._watch_id_by_identity.get(
            item.identity_key
        )

        if existing_watch_id is not None:
            raise DuplicateWatchItemError(
                "동일한 상품이 Watch List에 이미 존재합니다: "
                f"{item.identity_key}"
            )

        self._items_by_watch_id[item.watch_id] = item
        self._watch_id_by_identity[item.identity_key] = item.watch_id

    def get(self, watch_id: str) -> WatchItem:
        """watch_id에 해당하는 Watch Item을 반환한다."""
        cleaned_watch_id = self._clean_watch_id(watch_id)

        try:
            return self._items_by_watch_id[cleaned_watch_id]
        except KeyError as error:
            raise WatchItemNotFoundError(
                f"Watch Item을 찾을 수 없습니다: {cleaned_watch_id}"
            ) from error

    def find_by_identity(
        self,
        identity_key: str,
    ) -> WatchItem | None:
        """상품 식별자로 Watch Item을 조회한다."""
        cleaned_identity_key = identity_key.strip()

        if not cleaned_identity_key:
            raise ValueError(
                "identity_key는 비어 있을 수 없습니다."
            )

        watch_id = self._watch_id_by_identity.get(
            cleaned_identity_key
        )

        if watch_id is None:
            return None

        return self._items_by_watch_id[watch_id]

    def contains_identity(
        self,
        identity_key: str,
    ) -> bool:
        return self.find_by_identity(identity_key) is not None

    def remove(self, watch_id: str) -> WatchItem:
        """
        Watch Item을 목록에서 완전히 제거한다.

        사용자 화면에서만 숨기고 이력을 보존해야 하는 경우에는
        remove 대신 archive를 사용한다.
        """
        item = self.get(watch_id)

        del self._items_by_watch_id[item.watch_id]
        self._watch_id_by_identity.pop(
            item.identity_key,
            None,
        )

        return item

    def archive(self, watch_id: str) -> WatchItem:
        """Watch Item을 보관 상태로 변경한다."""
        item = self.get(watch_id)
        item.archive()
        return item

    def restore(self, watch_id: str) -> WatchItem:
        """보관된 Watch Item을 다시 감시 상태로 변경한다."""
        item = self.get(watch_id)
        item.restore()
        return item

    def list_all(self) -> tuple[WatchItem, ...]:
        """등록 순서대로 모든 Watch Item을 반환한다."""
        return tuple(self._items_by_watch_id.values())

    def list_watching(self) -> tuple[WatchItem, ...]:
        """현재 감시 중인 Watch Item만 반환한다."""
        return tuple(
            item
            for item in self._items_by_watch_id.values()
            if item.status is WatchItemStatus.WATCHING
        )

    def list_archived(self) -> tuple[WatchItem, ...]:
        """보관된 Watch Item만 반환한다."""
        return tuple(
            item
            for item in self._items_by_watch_id.values()
            if item.status is WatchItemStatus.ARCHIVED
        )

    def __len__(self) -> int:
        return len(self._items_by_watch_id)

    def __iter__(self):
        return iter(self._items_by_watch_id.values())

    @staticmethod
    def _clean_watch_id(watch_id: str) -> str:
        if not isinstance(watch_id, str):
            raise TypeError("watch_id는 문자열이어야 합니다.")

        cleaned_watch_id = watch_id.strip()

        if not cleaned_watch_id:
            raise ValueError(
                "watch_id는 비어 있을 수 없습니다."
            )

        return cleaned_watch_id