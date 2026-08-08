"""Production identity supplier for Domestic Market Validation assessments."""

from uuid import uuid4


class ProductionDomesticMarketValidationIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionDomesticMarketValidationIdentityGenerator"]
