"""Production identity supplier for Capital Readiness assessments."""

from uuid import uuid4


class ProductionCapitalReadinessIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionCapitalReadinessIdentityGenerator"]
