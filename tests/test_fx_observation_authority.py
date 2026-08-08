from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.sourcing import (
    AdmitFXObservation,
    AdmitFXObservationCommand,
    FXObservationAdmissionResult,
    FXObservationReplayConflictError,
    FX_OBSERVATION_COMMAND_SCHEMA_VERSION,
)
from app.domain.sourcing import (
    FXObservation,
    FX_OBSERVATION_SCHEMA_VERSION,
)


NOW = datetime(2026, 8, 9, 9, 0, 0, tzinfo=timezone.utc)


def command(**changes):
    values = dict(
        command_id="fx-observation-command-1",
        base_currency="USD",
        quote_currency="KRW",
        rate=Decimal("1380"),
        observed_at=NOW,
        provider="provider-alpha",
        source_reference="ext:obs:1",
        collection_method="scheduled-pull",
        schema_version=FX_OBSERVATION_COMMAND_SCHEMA_VERSION,
    )
    values.update(changes)
    return AdmitFXObservationCommand(**values)


class Identity:
    def __init__(self, value: str):
        self.value = value
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.value


class MemoryRepository:
    def __init__(self):
        self.validate_calls = 0
        self.save_calls = 0
        self._history: dict[str, tuple[str, FXObservationAdmissionResult]] = {}

    def validate_replay(self, command_id: str, fingerprint: str):
        self.validate_calls += 1
        stored = self._history.get(command_id)
        if stored is None:
            return None
        stored_fingerprint, stored_result = stored
        if stored_fingerprint != fingerprint:
            raise FXObservationReplayConflictError("payload conflict")
        return stored_result

    def save_observation(
        self,
        command: AdmitFXObservationCommand,
        observation: FXObservation,
    ) -> FXObservationAdmissionResult:
        self.save_calls += 1
        result = FXObservationAdmissionResult(observation, False)
        self._history[command.command_id] = (command.fingerprint, result)
        return result


def owner_with(
    *, repository: MemoryRepository | None = None, identity: str = "fx-obs-1", admitted_at: datetime = NOW,
):
    repository = repository or MemoryRepository()
    owner = AdmitFXObservation(
        repository,
        observation_id_generator=Identity(identity),
        admitted_clock=lambda: admitted_at,
    )
    return owner, repository


def test_valid_fx_observation_admission_preserves_authority_facts():
    owner, repository = owner_with(identity="obs-1")
    result = owner.execute(command())

    assert result.replayed is False
    assert repository.validate_calls == 1
    assert repository.save_calls == 1
    assert result.observation.observation_id == "obs-1"
    assert result.observation.schema_version == FX_OBSERVATION_SCHEMA_VERSION
    assert result.observation.base_currency == "USD"
    assert result.observation.quote_currency == "KRW"
    assert result.observation.rate == Decimal("1380")
    assert result.observation.pair == "USD/KRW"
    assert result.observation.observed_at == NOW
    assert result.observation.admitted_at == NOW
    assert result.observation.provenance.provider == "provider-alpha"
    assert result.observation.provenance.source_reference == "ext:obs:1"
    assert result.observation.provenance.collection_method == "scheduled-pull"


def test_exact_replay_returns_stored_observation_without_identity_or_clock_calls():
    repository = MemoryRepository()
    first_owner, _ = owner_with(
        repository=repository,
        identity="obs-primary",
        admitted_at=NOW,
    )
    first = first_owner.execute(command())

    replay_identity = Identity("obs-replay")
    replay_owner = AdmitFXObservation(
        repository,
        observation_id_generator=replay_identity,
        admitted_clock=lambda: pytest.fail("admitted clock must not be called"),
    )
    replay = replay_owner.execute(command())

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.observation == first.observation
    assert repository.save_calls == 1
    assert replay_identity.calls == 0


def test_replay_requires_matching_fingerprint_and_conflicts_on_changed_payload():
    repository = MemoryRepository()
    owner = owner_with(repository=repository)[0]
    owner.execute(command())

    identity = Identity("server-2")
    owner_conflict = AdmitFXObservation(
        repository,
        observation_id_generator=identity,
        admitted_clock=lambda: NOW,
    )

    with pytest.raises(FXObservationReplayConflictError):
        owner_conflict.execute(command(rate=Decimal("1390")))
    assert identity.calls == 0


def test_base_and_quote_must_be_distinct():
    with pytest.raises(ValueError, match="must differ"):
        command(quote_currency="USD")


def test_rate_positive_decimal_enforced():
    with pytest.raises(ValueError, match="greater than zero"):
        command(rate=Decimal("0"))
    with pytest.raises(ValueError, match="greater than zero"):
        command(rate=Decimal("-1"))
    with pytest.raises(ValueError, match="finite"):
        command(rate=Decimal("NaN"))
    with pytest.raises(TypeError, match="must be Decimal"):
        command(rate=1.0)  # type: ignore[arg-type]


def test_observed_at_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        command(observed_at=datetime(2026, 8, 9, 9, 0, 0))


def test_canonical_pair_direction_and_no_inverse_fabrication():
    result = owner_with()[0].execute(command(base_currency="USD", quote_currency="KRW"))
    assert result.observation.pair == "USD/KRW"
    assert result.observation.rate == Decimal("1380")


def test_no_freshness_or_conversion_policy_applied_at_authority_boundary():
    result = owner_with()[0].execute(command())
    # FX boundary only stores authoritative observation facts; no conversion / inverse
    # policy is made at this layer.
    assert result.observation.pair == "USD/KRW"
    assert result.observation.base_currency == "USD"
    assert result.observation.quote_currency == "KRW"


def test_unsupported_command_schema_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        command(schema_version="fx-observation-command-v0")


def test_no_automatic_inverse_or_mutation_is_not_performed():
    baseline = owner_with()[0].execute(command(base_currency="EUR", quote_currency="USD", rate=Decimal("1.2")))
    assert baseline.observation.pair == "EUR/USD"
    assert baseline.observation.rate == Decimal("1.2")


def test_immutable_domain_contracts():
    result = owner_with()[0].execute(command())
    with pytest.raises(FrozenInstanceError):
        result.observation.observed_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
