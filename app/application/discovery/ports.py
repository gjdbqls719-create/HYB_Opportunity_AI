from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.discovery import DiscoveryResult


@runtime_checkable
class ObservationIdentityProvider(Protocol):
    """Supplies an authoritative opaque identity for one observation."""

    def provide_observation_id(self) -> str: ...


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
