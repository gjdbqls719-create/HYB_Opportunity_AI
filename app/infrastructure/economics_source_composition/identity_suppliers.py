"""Production identity supplier for Economics Source Composition history."""

from uuid import uuid4


class ProductionEconomicsSourceCompositionIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionEconomicsSourceCompositionIdentityGenerator"]
