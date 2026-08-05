"""Production identity suppliers for authoritative Discovery facts."""

from __future__ import annotations

from uuid import uuid4


class ProductionCandidateIdentityGenerator:
    """Supplies one opaque Candidate identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionObservationIdentityProvider:
    """Supplies one server-owned opaque observation identity per call."""

    __slots__ = ()

    def provide_observation_id(self) -> str:
        return uuid4().hex


class ProductionFinalizedGroupIdentityProvider:
    """Supplies one server-owned opaque finalized Group identity per call."""

    __slots__ = ()

    def provide_finalized_group_id(self) -> str:
        return uuid4().hex


__all__ = [
    "ProductionCandidateIdentityGenerator",
    "ProductionFinalizedGroupIdentityProvider",
    "ProductionObservationIdentityProvider",
]
