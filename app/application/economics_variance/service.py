from __future__ import annotations

from uuid import uuid4

from app.application.economics_variance.mapper import map_economics_calculation_to_snapshot
from app.application.economics_variance.models import CaptureEstimatedEconomicsBaseline, GetVariance
from app.application.economics_variance.ports import (
    ActualEconomicsForVarianceNotFoundError,
    ActualEconomicsRepository,
    EstimatedBaselineNotFoundError,
    EstimatedEconomicsSnapshotRepository,
)
from app.domain.opportunity import (
    EconomicsVariance,
    EstimatedEconomicsSnapshot,
    calculate_economics_variance,
)


class EconomicsVarianceService:
    def __init__(
        self,
        *,
        baseline_repository: EstimatedEconomicsSnapshotRepository,
        actual_repository: ActualEconomicsRepository,
    ) -> None:
        self._baselines = baseline_repository
        self._actuals = actual_repository

    def capture(self, command: CaptureEstimatedEconomicsBaseline) -> EstimatedEconomicsSnapshot:
        snapshot = self.build_snapshot(command)
        self._baselines.create(snapshot)
        return snapshot

    @staticmethod
    def build_snapshot(command: CaptureEstimatedEconomicsBaseline) -> EstimatedEconomicsSnapshot:
        return map_economics_calculation_to_snapshot(
            snapshot_id=command.snapshot_id or uuid4().hex,
            opportunity_id=command.opportunity_id,
            baseline_kind=command.baseline_kind,
            economics=command.economics,
            calculation_version=command.calculation_version,
            variance_formula_version=command.variance_formula_version,
            captured_at=command.captured_at,
        )

    def get(self, query: GetVariance) -> EconomicsVariance:
        estimated = self._baselines.get_admission_baseline(query.opportunity_id)
        if estimated is None:
            raise EstimatedBaselineNotFoundError(query.opportunity_id)
        actual = self._actuals.get(query.opportunity_id)
        if actual is None:
            raise ActualEconomicsForVarianceNotFoundError(query.opportunity_id)
        return calculate_economics_variance(estimated, actual)
