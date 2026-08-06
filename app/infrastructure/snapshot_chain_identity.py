"""Production identity supplier for authoritative Snapshot Chain bindings."""

from __future__ import annotations

from uuid import uuid4


class ProductionSnapshotChainBindingIdentityGenerator:
    """Supplies one opaque Snapshot Chain binding identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionSnapshotChainBindingIdentityGenerator"]
