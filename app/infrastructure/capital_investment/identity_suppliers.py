"""Production opaque identities for Founder Capital investment facts."""

from uuid import uuid4


class ProductionIntendedOrderQuantityIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionDeployableCapitalSnapshotIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = [name for name in globals() if name.startswith("Production")]
