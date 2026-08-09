"""Production opaque identity for Actual Outcomes."""

from uuid import uuid4


class ProductionActualOutcomeIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionActualOutcomeIdentityGenerator"]
