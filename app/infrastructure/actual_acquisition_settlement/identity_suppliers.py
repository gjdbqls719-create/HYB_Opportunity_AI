"""Production opaque identity for Actual Acquisition Settlement revisions."""

from uuid import uuid4


class ProductionActualAcquisitionSettlementIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionActualAcquisitionSettlementIdentityGenerator"]
