"""Production opaque identity for Goods Receipt Records."""

from uuid import uuid4


class ProductionGoodsReceiptRecordIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionGoodsReceiptRecordIdentityGenerator"]
