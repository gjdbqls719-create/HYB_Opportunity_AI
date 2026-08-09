"""Production opaque identity for Purchase Execution Records."""

from uuid import uuid4


class ProductionPurchaseExecutionRecordIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionPurchaseExecutionRecordIdentityGenerator"]
