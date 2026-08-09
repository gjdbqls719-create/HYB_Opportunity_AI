"""Production opaque identity supplier for Capital Gate assessments."""

from uuid import uuid4


class ProductionCapitalGateIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionCapitalGateIdentityGenerator"]
