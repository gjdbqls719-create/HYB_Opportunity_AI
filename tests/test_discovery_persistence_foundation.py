from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import inspect

import pytest

from app.application.discovery_persistence import (
    DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION,
    DiscoveryCommandReceipt,
    DiscoveryCommandRepository,
    DiscoveryGroupRepository,
    DiscoveryPersistenceError,
    DiscoveryReplayConflict,
    DiscoveryResultRepository,
    MalformedDiscoveryReceipt,
    MissingDiscoveryCommand,
    PersistDiscoveryCommand,
    UnsupportedDiscoveryReceiptVersion,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from test_discovery_correlation_contract import NOW, command, group


COMMITTED_AT = datetime(2026, 8, 5, 11, tzinfo=timezone.utc)


class MemoryDiscoveryCommands:
    def __init__(self):
        self.commands = {}
        self.receipts = {}
        self.save_calls = 0
        self.read_calls = 0

    def save_command(self, value, receipt):
        self.save_calls += 1
        existing = self.receipts.get(value.command_id)
        if existing is not None:
            if existing.canonical_payload_fingerprint != value.fingerprint:
                raise DiscoveryReplayConflict("command payload conflict")
            return existing
        self.commands[value.command_id] = value
        self.receipts[value.command_id] = receipt
        return receipt

    def get_command(self, command_id):
        self.read_calls += 1
        return self.commands.get(command_id)

    def get_by_execution(self, discovery_execution_id):
        self.read_calls += 1
        return next(
            (
                value
                for value in self.commands.values()
                if value.discovery_execution_id == discovery_execution_id
            ),
            None,
        )

    def exists(self, command_id):
        self.read_calls += 1
        return command_id in self.commands

    def validate_replay(self, command_id, canonical_payload_fingerprint):
        self.read_calls += 1
        receipt = self.receipts.get(command_id)
        if (
            receipt is not None
            and receipt.canonical_payload_fingerprint
            != canonical_payload_fingerprint
        ):
            raise DiscoveryReplayConflict("command payload conflict")
        return receipt


class MemoryDiscoveryGroups:
    def __init__(self):
        self.values = {}

    def save_group(self, value):
        self.values[value.finalized_group_id] = value
        return value

    def get_group(self, finalized_group_id):
        return self.values.get(finalized_group_id)

    def get_by_execution(self, discovery_execution_id):
        return tuple(
            value
            for value in self.values.values()
            if value.discovery_execution_id == discovery_execution_id
        )

    def get_by_membership_fingerprint(self, membership_fingerprint):
        return tuple(
            value
            for value in self.values.values()
            if value.membership_fingerprint == membership_fingerprint
        )


class MemoryDiscoveryResults:
    def __init__(self):
        self.values = {}

    def save_result(self, value):
        self.values[value.discovery_execution_id] = value
        return value

    def get_result(self, discovery_execution_id):
        return self.values.get(discovery_execution_id)

    def get_by_command(self, command_id):
        return next(
            (value for value in self.values.values() if value.command_id == command_id),
            None,
        )


class CountingClock:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return COMMITTED_AT


def receipt() -> DiscoveryCommandReceipt:
    value = command()
    return DiscoveryCommandReceipt(
        value.command_id,
        value.discovery_execution_id,
        value.fingerprint,
        COMMITTED_AT,
    )


def test_receipt_is_immutable_equal_versioned_and_timezone_aware() -> None:
    value = receipt()
    assert value == receipt()
    assert value.schema_version == DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION
    assert value.committed_at == COMMITTED_AT
    with pytest.raises(FrozenInstanceError):
        value.command_id = "changed"
    with pytest.raises(MalformedDiscoveryReceipt, match="timezone-aware"):
        replace(value, committed_at=COMMITTED_AT.replace(tzinfo=None))


def test_receipt_rejects_malformed_fingerprint_and_unsupported_version() -> None:
    with pytest.raises(MalformedDiscoveryReceipt, match="SHA-256"):
        replace(receipt(), canonical_payload_fingerprint="not-a-fingerprint")
    with pytest.raises(UnsupportedDiscoveryReceiptVersion):
        replace(receipt(), schema_version="future")


def test_repository_protocols_support_the_required_boundaries() -> None:
    commands: DiscoveryCommandRepository = MemoryDiscoveryCommands()
    groups: DiscoveryGroupRepository = MemoryDiscoveryGroups()
    results: DiscoveryResultRepository = MemoryDiscoveryResults()
    value = command()
    stored_receipt = receipt()
    assert commands.save_command(value, stored_receipt) == stored_receipt
    assert commands.get_command(value.command_id) == value
    assert commands.get_by_execution(value.discovery_execution_id) == value
    assert commands.exists(value.command_id) is True
    assert commands.validate_replay(value.command_id, value.fingerprint) == stored_receipt

    finalized = group()
    assert groups.save_group(finalized) == finalized
    assert groups.get_group(finalized.finalized_group_id) == finalized
    assert groups.get_by_execution(finalized.discovery_execution_id) == (finalized,)
    assert groups.get_by_membership_fingerprint(finalized.membership_fingerprint) == (finalized,)

    result = DiscoveryExecutionResult(
        value.command_id,
        value.discovery_execution_id,
        (finalized.finalized_group_id,),
        NOW,
    )
    assert results.save_result(result) == result
    assert results.get_result(value.discovery_execution_id) == result
    assert results.get_by_command(value.command_id) == result


def test_application_boundary_persists_once_and_replays_exact_result() -> None:
    repository = MemoryDiscoveryCommands()
    clock = CountingClock()
    service = PersistDiscoveryCommand(repository, clock=clock)
    first = service.execute(command())
    replay = service.execute(command())

    assert first.command == command()
    assert first.receipt == receipt()
    assert first.replayed is False
    assert replay == replace(first, replayed=True)
    assert replay.receipt is first.receipt
    assert repository.save_calls == 1
    assert clock.calls == 1


def test_same_command_changed_payload_is_an_explicit_conflict() -> None:
    repository = MemoryDiscoveryCommands()
    service = PersistDiscoveryCommand(repository, clock=lambda: COMMITTED_AT)
    service.execute(command())
    with pytest.raises(DiscoveryReplayConflict):
        service.execute(
            command(parameters=replace(command().parameters, limit=20))
        )
    assert repository.save_calls == 1


def test_different_command_with_same_payload_is_a_new_execution() -> None:
    repository = MemoryDiscoveryCommands()
    clock = CountingClock()
    service = PersistDiscoveryCommand(repository, clock=clock)
    first = service.execute(command())
    second_command = command(
        command_id="command-2", discovery_execution_id="execution-2"
    )
    second = service.execute(second_command)
    assert first.command.command_id != second.command.command_id
    assert first.replayed is False and second.replayed is False
    assert repository.save_calls == 2
    assert clock.calls == 2


def test_receipt_without_committed_command_is_explicitly_missing() -> None:
    repository = MemoryDiscoveryCommands()
    repository.receipts["command-1"] = receipt()
    with pytest.raises(MissingDiscoveryCommand):
        PersistDiscoveryCommand(repository, clock=lambda: COMMITTED_AT).execute(
            command()
        )


def test_repository_failure_is_mapped_to_persistence_error() -> None:
    class BrokenRepository(MemoryDiscoveryCommands):
        def validate_replay(self, command_id, canonical_payload_fingerprint):
            raise OSError("storage unavailable")

    with pytest.raises(DiscoveryPersistenceError) as captured:
        PersistDiscoveryCommand(
            BrokenRepository(), clock=lambda: COMMITTED_AT
        ).execute(command())
    assert not isinstance(captured.value.__cause__, DiscoveryReplayConflict)


def test_save_race_can_return_the_winning_committed_receipt() -> None:
    winning_receipt = replace(receipt(), committed_at=COMMITTED_AT.replace(hour=10))

    class WinningRepository(MemoryDiscoveryCommands):
        def save_command(self, value, attempted_receipt):
            self.save_calls += 1
            self.commands[value.command_id] = value
            self.receipts[value.command_id] = winning_receipt
            return winning_receipt

    repository = WinningRepository()
    result = PersistDiscoveryCommand(
        repository, clock=lambda: COMMITTED_AT
    ).execute(command())
    assert result.replayed is True
    assert result.receipt is winning_receipt
    assert result.command == command()


def test_application_boundary_has_no_execution_or_infrastructure_dependencies() -> None:
    source = inspect.getsource(PersistDiscoveryCommand).lower()
    for forbidden in (
        "collector",
        "search_products",
        "group_similar_products",
        "economics",
        "safety",
        "candidate",
        "sqlite",
        "begin immediate",
    ):
        assert forbidden not in source
