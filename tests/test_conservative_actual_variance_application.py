from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from app.application.conservative_actual_variance import (
    CalculateConservativeActualVariance,
    CalculateConservativeActualVarianceCommand,
    ConservativeActualVariancePublication,
)
from app.domain.opportunity.conservative_actual_variance import (
    VarianceCalibrationEligibility,
    VarianceCalibrationReason,
)
from app.infrastructure.conservative_actual_variance import (
    SQLiteConservativeActualVarianceRepository,
)
from test_conservative_actual_variance_production_api import _variance_journey
from test_o2_economics_production_chain_api import economics_chain_client


class _ApplicationRepository:
    def __init__(self, source, conservative):
        self.source = source
        self.conservative = conservative
        self.saved = None

    def __getattr__(self, name):
        return getattr(self.source, name)

    def get_conservative_result(self, result_id):
        assert result_id == self.conservative.result_id
        return self.conservative

    def validate_replay(self, _command_id, _fingerprint):
        return None

    def find_by_scope(self, _scope_fingerprint):
        return None

    def save(self, _command, variance, receipt, _scope_fingerprint):
        self.saved = (variance, receipt)
        return ConservativeActualVariancePublication(variance, receipt, False, False)


def test_application_post_purchase_prediction_is_numeric_but_ineligible(
    economics_chain_client,
):
    result = _variance_journey(economics_chain_client)
    with SQLiteConservativeActualVarianceRepository(result["database"]) as source:
        conservative_id = result["variance_payload"]["conservative_economics_result_id"]
        conservative = source.get_conservative_result(conservative_id)
        outcome = source.get_actual_outcome(result["outcome"]["outcome_id"])
        purchase = json.loads(outcome.source_manifest.acquisition_source_snapshot)["source_manifest"]
        purchase_executed_at = datetime.fromisoformat(purchase["purchase_executed_at"])
        late_conservative = replace(
            conservative,
            calculated_at=purchase_executed_at + timedelta(microseconds=1),
        )
        repository = _ApplicationRepository(source, late_conservative)
        requested_at = datetime.now(timezone.utc)
        publication = CalculateConservativeActualVariance(
            repository,
            variance_id_generator=lambda: "variance-post-purchase",
            calculated_clock=lambda: requested_at + timedelta(seconds=1),
            committed_clock=lambda: requested_at + timedelta(seconds=2),
        ).execute(
            CalculateConservativeActualVarianceCommand(
                command_id="variance-post-purchase-command",
                opportunity_id=result["opportunity_id"],
                conservative_economics_result_id=conservative_id,
                actual_outcome_id=outcome.outcome_id,
                requested_at=requested_at,
            )
        )

    assert publication.variance.calibration_eligibility is VarianceCalibrationEligibility.INELIGIBLE
    assert VarianceCalibrationReason.PREDICTION_AFTER_EXECUTION in (
        publication.variance.calibration_reasons
    )
    assert publication.variance.core_metrics[0].variance is not None


class _ReplayRepository:
    def __init__(self, publication):
        self.publication = publication
        self.source_reads = 0

    def validate_replay(self, _command_id, _fingerprint):
        return self.publication

    def get_conservative_result(self, _result_id):
        self.source_reads += 1
        raise AssertionError("replay must precede source reads")


def test_application_replay_precedes_sources_identity_and_clocks(economics_chain_client):
    result = _variance_journey(economics_chain_client)
    first = result["client"].post(result["variance_route"], json=result["variance_payload"])
    assert first.status_code == 201, first.text
    with SQLiteConservativeActualVarianceRepository(result["database"]) as repository:
        variance = repository.get_variance(first.json()["variance_id"])
        receipt = repository._load_receipt(repository._receipt_row("variance-command-1"))
    prior = ConservativeActualVariancePublication(variance, receipt, False, False)
    replay_repository = _ReplayRepository(prior)

    def forbidden():
        raise AssertionError("replay must precede identity and clocks")

    publication = CalculateConservativeActualVariance(
        replay_repository,
        variance_id_generator=forbidden,
        calculated_clock=forbidden,
        committed_clock=forbidden,
    ).execute(
        CalculateConservativeActualVarianceCommand(
            command_id="variance-command-1",
            opportunity_id=result["opportunity_id"],
            conservative_economics_result_id=result["variance_payload"]["conservative_economics_result_id"],
            actual_outcome_id=result["outcome"]["outcome_id"],
            requested_at=datetime.fromisoformat(result["variance_payload"]["requested_at"]),
        )
    )
    assert publication.replayed is True
    assert replay_repository.source_reads == 0
