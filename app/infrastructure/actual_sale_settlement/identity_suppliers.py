"""Production opaque identity for Actual Sale Settlement revisions."""

from uuid import uuid4


class ProductionActualSaleSettlementIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionActualSaleSettlementIdentityGenerator"]
