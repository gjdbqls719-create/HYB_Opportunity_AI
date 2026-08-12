"""Production UUIDv4 identity suppliers for new-to-market admission."""

from uuid import uuid4


class ProductionNewToMarketDomesticOpportunityIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionNewToMarketDomesticSellingTargetIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionNewToMarketDomesticSellingAdmissionIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = [
    "ProductionNewToMarketDomesticOpportunityIdentityGenerator",
    "ProductionNewToMarketDomesticSellingAdmissionIdentityGenerator",
    "ProductionNewToMarketDomesticSellingTargetIdentityGenerator",
]
