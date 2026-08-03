from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProductionSafetyStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PROFITABILITY_FAILED = "PROFITABILITY_FAILED"


@dataclass(frozen=True, slots=True)
class ProductionSafetyAssessment:
    status: ProductionSafetyStatus
    missing_fields: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("missing_fields", "failed_checks"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} must contain non-empty text")

    @property
    def can_recommend_buy(self) -> bool:
        return self.status is ProductionSafetyStatus.READY
