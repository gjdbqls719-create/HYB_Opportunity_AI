"""Production identity supplier for Domestic Market Validation v2 assessments."""

from uuid import uuid4


class ProductionDomesticMarketValidationV2IdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionDomesticMarketValidationV2IdentityGenerator"]
