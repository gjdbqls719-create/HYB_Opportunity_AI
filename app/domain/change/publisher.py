from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.change.events import (
    ChangeDetectedEvent,
)


@runtime_checkable
class ChangeEventPublisher(Protocol):
    """
    Change Domain 이벤트 발행 포트.

    Domain은 이벤트를 어떻게 저장하거나 전달하는지
    알지 않는다. 인프라 계층이 이 Protocol을 구현한다.
    """

    def publish(
        self,
        event: ChangeDetectedEvent,
    ) -> None:
        ...


@runtime_checkable
class ChangeEventBatchPublisher(Protocol):
    """
    여러 Change Domain 이벤트를 한 번에 발행하는 포트.
    """

    def publish_many(
        self,
        events: tuple[
            ChangeDetectedEvent,
            ...,
        ],
    ) -> None:
        ...