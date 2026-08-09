"""Production identity supplier for planned acquisition capital requirements."""

from uuid import uuid4


class ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionPlannedAcquisitionCapitalRequirementIdentityGenerator"]
