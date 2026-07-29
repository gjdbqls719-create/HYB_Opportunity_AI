from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.watchlist import WatchItem


@runtime_checkable
class WatchListRepository(Protocol):
    """
    Watch Item 영속성을 위한 Application Port.

    Application과 Domain 계층은 SQLite 같은 구체적인 저장 기술을
    알지 않고 이 계약에만 의존한다.
    """

    def save(self, item: WatchItem) -> None:
        """
        Watch Item을 저장한다.

        같은 watch_id가 이미 존재하면 현재 상태로 갱신한다.
        다른 watch_id가 동일한 identity_key를 사용하면
        중복 상품으로 처리해야 한다.
        """
        ...

    def get(
        self,
        watch_id: str,
    ) -> WatchItem | None:
        """watch_id로 Watch Item을 조회한다."""
        ...

    def find_by_identity(
        self,
        identity_key: str,
    ) -> WatchItem | None:
        """상품 Identity로 Watch Item을 조회한다."""
        ...

    def list_all(self) -> tuple[WatchItem, ...]:
        """저장된 모든 Watch Item을 등록 순서대로 반환한다."""
        ...

    def list_watching(self) -> tuple[WatchItem, ...]:
        """현재 감시 중인 Watch Item을 반환한다."""
        ...

    def list_archived(self) -> tuple[WatchItem, ...]:
        """보관된 Watch Item을 반환한다."""
        ...

    def exists(
        self,
        watch_id: str,
    ) -> bool:
        """watch_id가 존재하는지 반환한다."""
        ...

    def exists_identity(
        self,
        identity_key: str,
    ) -> bool:
        """상품 Identity가 존재하는지 반환한다."""
        ...

    def delete(
        self,
        watch_id: str,
    ) -> bool:
        """
        Watch Item을 완전히 삭제한다.

        삭제된 항목이 있으면 True,
        존재하지 않았으면 False를 반환한다.
        """
        ...

    def count(self) -> int:
        """저장된 Watch Item 전체 개수를 반환한다."""
        ...