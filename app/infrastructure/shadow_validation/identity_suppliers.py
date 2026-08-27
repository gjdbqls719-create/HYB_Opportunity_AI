"""Production UUIDv4 identity suppliers for Shadow registration facts."""

from uuid import uuid4


class ProductionShadowValidationIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionShadowBaselineSnapshotIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = [
    "ProductionShadowBaselineSnapshotIdentityGenerator",
    "ProductionShadowValidationIdentityGenerator",
]
