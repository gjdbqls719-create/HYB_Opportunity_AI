from __future__ import annotations

from uuid import uuid4


class _OpaqueSourcingIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionSupplierIdentityGenerator(_OpaqueSourcingIdentityGenerator):
    pass


class ProductionSourcingProductIdentityGenerator(_OpaqueSourcingIdentityGenerator):
    pass


class ProductionSupplierQuoteIdentityGenerator(_OpaqueSourcingIdentityGenerator):
    pass


class ProductionProductMatchVerificationIdentityGenerator(_OpaqueSourcingIdentityGenerator):
    pass


class ProductionFounderSourcingAdmissionIdentityGenerator(_OpaqueSourcingIdentityGenerator):
    pass


__all__ = [name for name in globals() if name.startswith("Production")]
