"""Production identity supplier for authoritative Economics Snapshots."""

from __future__ import annotations

from uuid import uuid4


class ProductionEconomicsSnapshotIdentityGenerator:
    """Supplies one opaque Economics Snapshot identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionEconomicsSnapshotIdentityGenerator"]
