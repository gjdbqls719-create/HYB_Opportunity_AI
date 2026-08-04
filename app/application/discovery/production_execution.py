"""Application owner for a persisted production discovery execution entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.discovery_persistence import (
    PersistDiscoveryCommand,
    PersistDiscoveryCommandResult,
)
from app.domain.discovery import DiscoveryResult
from app.domain.discovery_identity import DiscoveryCommand


class ProductionDiscoveryRuntime(Protocol):
    """Runs discovery from an already committed command."""

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> tuple[DiscoveryResult, ...]: ...


@dataclass(frozen=True, slots=True)
class PersistedDiscoveryExecutionResult:
    command_result: PersistDiscoveryCommandResult
    discovery_results: tuple[DiscoveryResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.command_result, PersistDiscoveryCommandResult):
            raise TypeError(
                "command_result must be PersistDiscoveryCommandResult"
            )
        if not isinstance(self.discovery_results, tuple):
            raise TypeError("discovery_results must be tuple")
        if not all(
            isinstance(result, DiscoveryResult)
            for result in self.discovery_results
        ):
            raise TypeError(
                "discovery_results must contain DiscoveryResult values"
            )


class PersistedDiscoveryExecutionEntry:
    """Persists command identity before running the production discovery runtime."""

    def __init__(
        self,
        *,
        persist_command: PersistDiscoveryCommand,
        runtime: ProductionDiscoveryRuntime,
    ) -> None:
        self._persist_command = persist_command
        self._runtime = runtime

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> PersistedDiscoveryExecutionResult:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")

        command_result = self._persist_command.execute(command)
        discovery_results = self._runtime.execute(command_result.command)

        return PersistedDiscoveryExecutionResult(
            command_result=command_result,
            discovery_results=tuple(discovery_results),
        )


__all__ = [
    "PersistedDiscoveryExecutionEntry",
    "PersistedDiscoveryExecutionResult",
    "ProductionDiscoveryRuntime",
]
