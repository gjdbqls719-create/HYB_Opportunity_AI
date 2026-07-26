from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DiscoverySessionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class DiscoverySession:
    """한 번의 Opportunity Discovery 실행 수명주기."""

    query: str
    requested_limit: int
    session_id: str = field(default_factory=lambda: uuid4().hex)
    status: DiscoverySessionStatus = DiscoverySessionStatus.RUNNING
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        self.query = self.query.strip()

        if not self.query:
            raise ValueError("검색어를 입력해야 합니다.")

        if self.requested_limit < 1:
            raise ValueError("requested_limit은 1 이상이어야 합니다.")

        if not self.session_id.strip():
            raise ValueError("session_id는 비어 있을 수 없습니다.")

        if self.started_at.tzinfo is None:
            raise ValueError("started_at은 timezone-aware datetime이어야 합니다.")

    def complete(self, *, finished_at: datetime | None = None) -> None:
        self._finish(
            status=DiscoverySessionStatus.COMPLETED,
            error_message=None,
            finished_at=finished_at,
        )

    def fail(
        self,
        error: Exception,
        *,
        finished_at: datetime | None = None,
    ) -> None:
        self._finish(
            status=DiscoverySessionStatus.FAILED,
            error_message=str(error),
            finished_at=finished_at,
        )

    def _finish(
        self,
        *,
        status: DiscoverySessionStatus,
        error_message: str | None,
        finished_at: datetime | None,
    ) -> None:
        if self.status is not DiscoverySessionStatus.RUNNING:
            raise RuntimeError("이미 종료된 DiscoverySession입니다.")

        resolved_finished_at = finished_at or utc_now()

        if resolved_finished_at.tzinfo is None:
            raise ValueError("finished_at은 timezone-aware datetime이어야 합니다.")

        if resolved_finished_at < self.started_at:
            raise ValueError("finished_at은 started_at보다 빠를 수 없습니다.")

        self.status = status
        self.finished_at = resolved_finished_at
        self.error_message = error_message
