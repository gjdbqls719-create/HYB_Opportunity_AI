"""Persistence boundaries for durable discovery command correlation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from app.domain.discovery_identity import (
    DiscoveryCommand,
    DiscoveryExecutionResult,
    FinalizedProductGroup,
    UnsupportedDiscoveryCommandVersionError,
)


DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION = "discovery-command-receipt-v1"


class DiscoveryPersistenceError(RuntimeError):
    pass


class DiscoveryCommandPersistenceError(DiscoveryPersistenceError):
    pass


class DiscoveryCommandNotFoundError(DiscoveryPersistenceError):
    pass


class MissingDiscoveryCommand(DiscoveryCommandNotFoundError):
    pass


class DiscoveryReplayConflict(DiscoveryPersistenceError):
    pass


class DuplicateDiscoveryExecutionError(DiscoveryPersistenceError):
    pass


class MalformedDiscoveryCommandPersistenceError(DiscoveryPersistenceError):
    pass


class DiscoveryCommandHistoryError(DiscoveryCommandPersistenceError):
    pass


class DiscoveryCommandReceiptError(DiscoveryCommandPersistenceError):
    pass


class DiscoveryCommandCommitError(DiscoveryCommandPersistenceError):
    pass


class MalformedDiscoveryReceipt(ValueError):
    pass


class UnsupportedDiscoveryReceiptVersion(MalformedDiscoveryReceipt):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedDiscoveryReceipt(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise MalformedDiscoveryReceipt(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise MalformedDiscoveryReceipt(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class DiscoveryCommandReceipt:
    command_id: str
    execution_id: str
    canonical_payload_fingerprint: str
    committed_at: datetime
    schema_version: str = DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "execution_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        fingerprint = _required(
            self.canonical_payload_fingerprint,
            "canonical_payload_fingerprint",
        )
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise MalformedDiscoveryReceipt(
                "canonical_payload_fingerprint must be lowercase SHA-256 text"
            )
        object.__setattr__(
            self, "canonical_payload_fingerprint", fingerprint
        )
        _aware(self.committed_at, "committed_at")
        if self.schema_version != DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedDiscoveryReceiptVersion(
                f"unsupported discovery receipt version: {self.schema_version}"
            )


class DiscoveryCommandRepository(Protocol):
    def save_command(
        self,
        command: DiscoveryCommand,
        receipt: DiscoveryCommandReceipt,
    ) -> DiscoveryCommandReceipt: ...

    def get_command(self, command_id: str) -> DiscoveryCommand | None: ...

    def get_by_execution(
        self, discovery_execution_id: str
    ) -> DiscoveryCommand | None: ...

    def exists(self, command_id: str) -> bool: ...

    def validate_replay(
        self, command_id: str, canonical_payload_fingerprint: str
    ) -> DiscoveryCommandReceipt | None: ...


class DiscoveryGroupRepository(Protocol):
    def save_group(self, group: FinalizedProductGroup) -> FinalizedProductGroup: ...

    def get_group(self, finalized_group_id: str) -> FinalizedProductGroup | None: ...

    def get_by_execution(
        self, discovery_execution_id: str
    ) -> tuple[FinalizedProductGroup, ...]: ...

    def get_by_membership_fingerprint(
        self, membership_fingerprint: str
    ) -> tuple[FinalizedProductGroup, ...]: ...


class DiscoveryResultRepository(Protocol):
    def save_result(
        self, result: DiscoveryExecutionResult
    ) -> DiscoveryExecutionResult: ...

    def get_result(
        self, discovery_execution_id: str
    ) -> DiscoveryExecutionResult | None: ...

    def get_by_command(self, command_id: str) -> DiscoveryExecutionResult | None: ...


@dataclass(frozen=True, slots=True)
class PersistDiscoveryCommandResult:
    command: DiscoveryCommand
    receipt: DiscoveryCommandReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")
        if not isinstance(self.receipt, DiscoveryCommandReceipt):
            raise TypeError("receipt must be DiscoveryCommandReceipt")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class PersistDiscoveryCommand:
    """Persists or replays command identity without executing discovery."""

    def __init__(
        self,
        repository: DiscoveryCommandRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._repository = repository
        self._clock = clock

    def execute(self, command: DiscoveryCommand) -> PersistDiscoveryCommandResult:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")
        fingerprint = command.fingerprint
        try:
            existing_receipt = self._repository.validate_replay(
                command.command_id, fingerprint
            )
        except (
            DiscoveryReplayConflict,
            DiscoveryPersistenceError,
            MalformedDiscoveryReceipt,
            UnsupportedDiscoveryCommandVersionError,
        ):
            raise
        except Exception as error:
            raise DiscoveryPersistenceError(
                "discovery command replay validation failed"
            ) from error

        if existing_receipt is not None:
            if not isinstance(existing_receipt, DiscoveryCommandReceipt):
                raise MalformedDiscoveryReceipt(
                    "repository returned a malformed discovery receipt"
                )
            committed = self._repository.get_command(command.command_id)
            if committed is None:
                raise MissingDiscoveryCommand(
                    "committed discovery receipt has no command"
                )
            if (
                committed.command_id != existing_receipt.command_id
                or committed.discovery_execution_id
                != existing_receipt.execution_id
                or committed.fingerprint
                != existing_receipt.canonical_payload_fingerprint
                or fingerprint != existing_receipt.canonical_payload_fingerprint
            ):
                raise DiscoveryReplayConflict(
                    "discovery command conflicts with committed receipt"
                )
            return PersistDiscoveryCommandResult(
                committed, existing_receipt, True
            )

        receipt = DiscoveryCommandReceipt(
            command_id=command.command_id,
            execution_id=command.discovery_execution_id,
            canonical_payload_fingerprint=fingerprint,
            committed_at=self._clock(),
        )
        try:
            saved_receipt = self._repository.save_command(command, receipt)
        except (
            DiscoveryReplayConflict,
            DiscoveryPersistenceError,
            MalformedDiscoveryReceipt,
            UnsupportedDiscoveryCommandVersionError,
        ):
            raise
        except Exception as error:
            raise DiscoveryPersistenceError(
                "discovery command persistence failed"
            ) from error
        if not isinstance(saved_receipt, DiscoveryCommandReceipt):
            raise MalformedDiscoveryReceipt(
                "repository returned a malformed saved receipt"
            )
        if (
            saved_receipt.command_id != command.command_id
            or saved_receipt.execution_id != command.discovery_execution_id
            or saved_receipt.canonical_payload_fingerprint != fingerprint
        ):
            raise DiscoveryReplayConflict(
                "saved discovery receipt conflicts with the command"
            )
        replayed = saved_receipt != receipt
        committed = command
        if replayed:
            committed = self._repository.get_command(command.command_id)
            if committed is None:
                raise MissingDiscoveryCommand(
                    "saved discovery receipt has no command"
                )
            if committed.fingerprint != fingerprint:
                raise DiscoveryReplayConflict(
                    "saved discovery command conflicts with its receipt"
                )
        return PersistDiscoveryCommandResult(committed, saved_receipt, replayed)


__all__ = [
    "DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION",
    "DiscoveryCommandReceipt",
    "DiscoveryCommandCommitError",
    "DiscoveryCommandHistoryError",
    "DiscoveryCommandNotFoundError",
    "DiscoveryCommandPersistenceError",
    "DiscoveryCommandReceiptError",
    "DiscoveryCommandRepository",
    "DiscoveryGroupRepository",
    "DiscoveryPersistenceError",
    "DiscoveryReplayConflict",
    "DuplicateDiscoveryExecutionError",
    "DiscoveryResultRepository",
    "MalformedDiscoveryReceipt",
    "MalformedDiscoveryCommandPersistenceError",
    "MissingDiscoveryCommand",
    "PersistDiscoveryCommand",
    "PersistDiscoveryCommandResult",
    "UnsupportedDiscoveryReceiptVersion",
]
