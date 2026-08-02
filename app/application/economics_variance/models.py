from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.opportunity import EconomicsCalculation


@dataclass(frozen=True, slots=True)
class CaptureEstimatedEconomicsBaseline:
    opportunity_id: str
    economics: EconomicsCalculation
    captured_at: datetime
    snapshot_id: str | None = None
    baseline_kind: str = "admission"
    calculation_version: str = "legacy-opportunity-v1"
    variance_formula_version: str = "variance-v1"


@dataclass(frozen=True, slots=True)
class GetVariance:
    opportunity_id: str
