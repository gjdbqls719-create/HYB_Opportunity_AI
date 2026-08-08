"""Production identity supplier for Conservative Economics history."""

from uuid import uuid4


class ProductionConservativeEconomicsIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionConservativeEconomicsIdentityGenerator"]
