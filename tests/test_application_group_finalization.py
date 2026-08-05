from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.application.discovery import (
    FinalizedGroupIdentityProvider,
    GroupFinalizationClock,
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
)
from app.application.discovery.group_finalization import (
    GroupFinalizationCorrelationError,
    assemble_finalized_product_groups,
)
from app.domain.discovery_identity import (
    MalformedFinalizedProductGroupError,
)
from engine import orchestrator
from engine.grouping_policy import GroupingPolicyDescriptor
from tests.test_discovery_correlation_contract import observation
from tests.test_discovery_phase_checkpoints import (
    CheckpointObservationRepository,
    CheckpointRuntime,
)
from tests.test_persisted_discovery_execution_entry import (
    RecordingObservationIdentityProvider,
    RecordingPersister,
    command,
)


FINALIZED_AT = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
POLICY = GroupingPolicyDescriptor("authoritative-grouping", "2.4.0")


class RecordingFinalizedGroupIdentityProvider:
    def __init__(self, *values: str, events: list[str] | None = None) -> None:
        self._values = iter(values)
        self.events = events
        self.calls = 0

    def provide_finalized_group_id(self) -> str:
        self.calls += 1
        value = next(self._values)
        if self.events is not None:
            self.events.append(f"group-id:{value}")
        return value


class RecordingGroupFinalizationClock:
    def __init__(
        self,
        *values: datetime,
        events: list[str] | None = None,
    ) -> None:
        self._values = iter(values)
        self.events = events
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        value = next(self._values)
        if self.events is not None:
            self.events.append(f"finalized-at:{value.isoformat()}")
        return value


def observations():
    return (
        observation(observation_id="observation-0"),
        observation(observation_id="observation-1"),
        observation(observation_id="observation-2"),
    )


def test_finalization_ports_are_explicit_application_contracts() -> None:
    identity_provider = RecordingFinalizedGroupIdentityProvider("group-1")
    clock = RecordingGroupFinalizationClock(FINALIZED_AT)

    assert isinstance(identity_provider, FinalizedGroupIdentityProvider)
    assert isinstance(clock, GroupFinalizationClock)
    assert not isinstance(object(), FinalizedGroupIdentityProvider)
    assert not isinstance(object(), GroupFinalizationClock)


def test_assembly_maps_ordered_observations_representatives_policy_ids_and_clock() -> None:
    identity_provider = RecordingFinalizedGroupIdentityProvider(
        "opaque-group-a",
        "opaque-group-b",
    )
    second_time = datetime(2026, 8, 6, 3, 0, 1, tzinfo=timezone.utc)
    clock = RecordingGroupFinalizationClock(FINALIZED_AT, second_time)

    groups = assemble_finalized_product_groups(
        discovery_execution_id="execution-1",
        observations=observations(),
        grouping_correlations=(
            GroupingCorrelation((2, 0), 0),
            GroupingCorrelation((1,), 1),
        ),
        grouping_policy_descriptor=POLICY,
        identity_provider=identity_provider,
        clock=clock,
    )

    assert tuple(group.finalized_group_id for group in groups) == (
        "opaque-group-a",
        "opaque-group-b",
    )
    assert groups[0].observation_ids == ("observation-2", "observation-0")
    assert groups[0].representative_observation_id == "observation-0"
    assert groups[1].observation_ids == ("observation-1",)
    assert groups[1].representative_observation_id == "observation-1"
    assert tuple(group.grouping_policy_version for group in groups) == (
        "2.4.0",
        "2.4.0",
    )
    assert tuple(group.finalized_at for group in groups) == (
        FINALIZED_AT,
        second_time,
    )
    assert all(group.discovery_execution_id == "execution-1" for group in groups)
    assert identity_provider.calls == 2
    assert clock.calls == 2


def test_assembly_uses_provider_ids_without_modification() -> None:
    groups = assemble_finalized_product_groups(
        discovery_execution_id="execution-1",
        observations=(observations()[0],),
        grouping_correlations=(GroupingCorrelation((0,), 0),),
        grouping_policy_descriptor=POLICY,
        identity_provider=RecordingFinalizedGroupIdentityProvider("opaque:id/01"),
        clock=RecordingGroupFinalizationClock(FINALIZED_AT),
    )

    assert groups[0].finalized_group_id == "opaque:id/01"


def test_zero_correlations_returns_empty_without_provider_or_clock_calls() -> None:
    identity_provider = RecordingFinalizedGroupIdentityProvider()
    clock = RecordingGroupFinalizationClock()

    groups = assemble_finalized_product_groups(
        discovery_execution_id="execution-1",
        observations=observations(),
        grouping_correlations=(),
        grouping_policy_descriptor=POLICY,
        identity_provider=identity_provider,
        clock=clock,
    )

    assert groups == ()
    assert identity_provider.calls == 0
    assert clock.calls == 0


def test_assembly_rejects_missing_collection_position_before_supply() -> None:
    identity_provider = RecordingFinalizedGroupIdentityProvider("unused")
    clock = RecordingGroupFinalizationClock(FINALIZED_AT)

    with pytest.raises(GroupFinalizationCorrelationError, match="position"):
        assemble_finalized_product_groups(
            discovery_execution_id="execution-1",
            observations=(observations()[0],),
            grouping_correlations=(GroupingCorrelation((1,), 1),),
            grouping_policy_descriptor=POLICY,
            identity_provider=identity_provider,
            clock=clock,
        )

    assert identity_provider.calls == 0
    assert clock.calls == 0


def test_assembly_rejects_observation_from_another_execution() -> None:
    with pytest.raises(GroupFinalizationCorrelationError, match="execution"):
        assemble_finalized_product_groups(
            discovery_execution_id="execution-1",
            observations=(
                observation(
                    observation_id="observation-other",
                    discovery_execution_id="execution-other",
                ),
            ),
            grouping_correlations=(GroupingCorrelation((0,), 0),),
            grouping_policy_descriptor=POLICY,
            identity_provider=RecordingFinalizedGroupIdentityProvider("unused"),
            clock=RecordingGroupFinalizationClock(FINALIZED_AT),
        )


def test_invalid_provider_id_and_clock_value_propagate_domain_validation() -> None:
    with pytest.raises(MalformedFinalizedProductGroupError, match="finalized_group_id"):
        assemble_finalized_product_groups(
            discovery_execution_id="execution-1",
            observations=(observations()[0],),
            grouping_correlations=(GroupingCorrelation((0,), 0),),
            grouping_policy_descriptor=POLICY,
            identity_provider=RecordingFinalizedGroupIdentityProvider(""),
            clock=RecordingGroupFinalizationClock(FINALIZED_AT),
        )

    with pytest.raises(MalformedFinalizedProductGroupError, match="timezone-aware"):
        assemble_finalized_product_groups(
            discovery_execution_id="execution-1",
            observations=(observations()[0],),
            grouping_correlations=(GroupingCorrelation((0,), 0),),
            grouping_policy_descriptor=POLICY,
            identity_provider=RecordingFinalizedGroupIdentityProvider("group-1"),
            clock=RecordingGroupFinalizationClock(FINALIZED_AT.replace(tzinfo=None)),
        )


def test_assembly_does_not_regroup_or_compare_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "group_similar_products",
        lambda *args, **kwargs: pytest.fail("must not regroup"),
    )
    monkeypatch.setattr(
        orchestrator,
        "compare_products",
        lambda *args, **kwargs: pytest.fail("must not compare Products"),
    )

    groups = assemble_finalized_product_groups(
        discovery_execution_id="execution-1",
        observations=(observations()[0],),
        grouping_correlations=(GroupingCorrelation((0,), 0),),
        grouping_policy_descriptor=POLICY,
        identity_provider=RecordingFinalizedGroupIdentityProvider("group-1"),
        clock=RecordingGroupFinalizationClock(FINALIZED_AT),
    )

    assert groups[0].observation_ids == ("observation-0",)


def test_entry_assembles_groups_at_checkpoint_and_returns_them_without_group_repository() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    identity_provider = RecordingFinalizedGroupIdentityProvider(
        "group-1",
        events=events,
    )
    clock = RecordingGroupFinalizationClock(FINALIZED_AT, events=events)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-0",
            "observation-1",
        ),
        observation_repository=CheckpointObservationRepository(events),
        finalized_group_identity_provider=identity_provider,
        group_finalization_clock=clock,
    ).execute(command())

    assert events == [
        "persist",
        "runtime",
        "collection-checkpoint",
        "observation:one",
        "observation:two",
        "grouping",
        "group-id:group-1",
        f"finalized-at:{FINALIZED_AT.isoformat()}",
        "grouping-checkpoint",
        "analysis",
    ]
    assert len(result.finalized_groups) == 1
    assert result.finalized_groups[0].observation_ids == (
        "observation-0",
        "observation-1",
    )
    assert result.finalized_groups[0].representative_observation_id == (
        "observation-0"
    )
    assert result.finalized_groups[0].grouping_policy_version == (
        orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR.policy_version
    )
