"""Production identity supplier for authoritative Price Snapshots."""

from __future__ import annotations

from uuid import uuid4


class ProductionPriceSnapshotIdentityGenerator:
    """Supplies one opaque Price Snapshot identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionPriceSnapshotIdentityGenerator"]
