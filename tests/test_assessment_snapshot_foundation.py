from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import sqlite3

import pytest

from app.application.assessment_snapshot import (
    AssessmentSnapshotProvenanceError,
    CompetitionAssessmentSnapshot,
    DemandAssessmentSnapshot,
    DuplicateAssessmentSnapshotError,
)
from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness
from app.domain.market_intelligence import MarketEvidenceStatus, analyze_competition, analyze_demand
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from test_competition_intelligence import NOW as COMP_NOW, observation as competition_observation
from test_demand_intelligence import NOW as DEMAND_NOW, observation as demand_observation
from test_market_observation_repository import external


def competition_snapshot(observation=None):
    observation = observation or competition_observation()
    assessment = analyze_competition(observation, generated_at=COMP_NOW)
    return CompetitionAssessmentSnapshot(
        snapshot_id=f"snapshot:{observation.observation_id}",
        identity=observation.identity,
        source_observation_id=observation.observation_id,
        assessment=assessment,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=assessment.confidence,
        freshness=DecisionFreshness.FRESH,
        generated_at=assessment.generated_at,
        schema_version="assessment-snapshot-v1",
        policy_version="competition-policy-v1",
    )


def demand_snapshot(observation=None):
    observation = observation or demand_observation()
    assessment = analyze_demand(observation, generated_at=DEMAND_NOW)
    return DemandAssessmentSnapshot(
        snapshot_id=f"snapshot:{observation.observation_id}",
        identity=observation.identity,
        source_observation_id=observation.observation_id,
        assessment=assessment,
        availability=DecisionEvidenceAvailability.COMPLETE,
        confidence=assessment.confidence,
        freshness=DecisionFreshness.STALE,
        generated_at=assessment.generated_at,
        schema_version="assessment-snapshot-v1",
        policy_version="demand-policy-v1",
    )


@pytest.mark.parametrize(
    ("observation", "snapshot", "getter"),
    (
        (competition_observation(), competition_snapshot(), "get_latest_competition_assessment_snapshot"),
        (demand_observation(), demand_snapshot(), "get_latest_demand_assessment_snapshot"),
    ),
)
def test_assessment_snapshot_atomic_persistence_and_exact_round_trip(
    observation, snapshot, getter
) -> None:
    repository = SQLiteMarketObservationRepository(":memory:")

    repository.save_assessment_snapshot(observation, snapshot)

    assert getattr(repository, getter)(observation.identity) == snapshot
    assert repository.get_history(
        "competition" if getter.startswith("get_latest_competition") else "demand",
        observation.identity,
    ) == (observation,)
    repository.close()


def test_snapshot_is_immutable_and_history_update_delete_are_blocked() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    observation = competition_observation()
    snapshot = competition_snapshot(observation)
    repository.save_assessment_snapshot(observation, snapshot)

    with pytest.raises(FrozenInstanceError):
        snapshot.policy_version = "changed"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute(
            "UPDATE market_assessment_snapshot_history SET payload_json='{}'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute("DELETE FROM market_assessment_snapshot_history")
    repository.close()


def test_duplicate_and_provenance_mismatch_are_rejected() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    observation = competition_observation()
    snapshot = competition_snapshot(observation)
    repository.save_assessment_snapshot(observation, snapshot)

    with pytest.raises(DuplicateAssessmentSnapshotError):
        repository.save_assessment_snapshot(observation, snapshot)
    with pytest.raises(AssessmentSnapshotProvenanceError, match="id"):
        repository.save_assessment_snapshot(
            replace(observation, observation_id="different"), snapshot
        )
    repository.close()


def test_snapshot_failure_rolls_back_observation_history_and_current() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_snapshot BEFORE INSERT
        ON market_assessment_snapshot_history
        BEGIN SELECT RAISE(ABORT, 'snapshot failure'); END"""
    )
    observation = competition_observation()

    with pytest.raises(DuplicateAssessmentSnapshotError):
        repository.save_assessment_snapshot(observation, competition_snapshot(observation))

    assert repository.get_history("competition", observation.identity) == ()
    assert repository.get_latest("competition", observation.identity) is None
    repository.close()


def test_latest_snapshot_projection_and_repeated_query_are_deterministic() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    first_observation = competition_observation()
    second_observation = replace(
        first_observation,
        observation_id="competition-2",
        observed_at=first_observation.observed_at + timedelta(minutes=1),
    )
    first = competition_snapshot(first_observation)
    second_assessment = analyze_competition(
        second_observation, generated_at=COMP_NOW + timedelta(minutes=1)
    )
    second = replace(
        competition_snapshot(second_observation),
        assessment=second_assessment,
        generated_at=second_assessment.generated_at,
    )
    repository.save_assessment_snapshot(first_observation, first)
    repository.save_assessment_snapshot(second_observation, second)

    assert repository.get_latest_competition_assessment_snapshot(first.identity) == second
    assert repository.get_latest_competition_assessment_snapshot(first.identity) == second
    repository.close()


def test_latest_human_verified_external_signal_series_excludes_superseded() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    base = external()

    def verified(signal_id, signal_name, minute):
        captured = base.captured_at + timedelta(minutes=minute)
        return replace(
            base,
            signal_id=signal_id,
            signal_name=signal_name,
            evidence=replace(base.evidence, status=MarketEvidenceStatus.HUMAN_VERIFIED),
            captured_at=captured,
            verified_at=captured,
            operator_id="founder",
            candidate_id=f"candidate:{signal_id}",
            verification_id=f"verification:{signal_id}",
        )

    repository.save(verified("signal-1a", "rating", 0))
    latest_rating = verified("signal-1b", "rating", 1)
    repository.save(latest_rating)
    review_count = verified("signal-2", "review_count", 0)
    repository.save(review_count)

    assert repository.get_latest_human_verified_external_signals(base.identity) == (
        latest_rating,
        review_count,
    )
    repository.close()
