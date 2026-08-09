"""Production identity suppliers for domestic-selling Opportunity admission."""

from uuid import uuid4


class ProductionDomesticSellingOpportunityIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionDomesticSellingOpportunityAdmissionIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = [
    "ProductionDomesticSellingOpportunityAdmissionIdentityGenerator",
    "ProductionDomesticSellingOpportunityIdentityGenerator",
]
