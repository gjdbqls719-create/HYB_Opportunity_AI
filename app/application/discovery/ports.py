from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.discovery import DiscoveryResult


@runtime_checkable
class ObservationIdentityProvider(Protocol):
    """Supplies an authoritative opaque identity for one observation."""

    def provide_observation_id(self) -> str: ...


@runtime_checkable
class FinalizedGroupIdentityProvider(Protocol):
    """Supplies one authoritative opaque finalized Group identity."""

    def provide_finalized_group_id(self) -> str: ...


@runtime_checkable
class GroupFinalizationClock(Protocol):
    """Supplies the authoritative time for one finalized Group."""

    def __call__(self) -> datetime: ...


@runtime_checkable
class DiscoveryCompletionClock(Protocol):
    """Supplies the authoritative completion time for one Discovery execution."""

    def __call__(self) -> datetime: ...


class OpportunityDiscoveryGateway(Protocol):
    """Application Layer가 기회 탐색 구현에 요구하는 최소 규약."""

    def discover(
        self,
        *,
        query: str,
        limit: int,
    ) -> list[DiscoveryResult]:
        """검색어와 수집 제한을 받아 분석이 끝난 후보를 반환한다."""
        ...
