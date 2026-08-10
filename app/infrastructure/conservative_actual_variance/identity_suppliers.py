"""Production opaque identity for Conservative-to-Actual variance v2."""

from uuid import uuid4


class ProductionConservativeActualVarianceIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionConservativeActualVarianceIdentityGenerator"]
