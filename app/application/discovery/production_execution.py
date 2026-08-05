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
from collectors.collection_fact import CollectionFact


class DiscoveryRuntimeCorrelationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProductionDiscoveryRuntimeResult:
    discovery_execution_id: str
    discovery_results: tuple[DiscoveryResult, ...]
    collection_facts: tuple[CollectionFact, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.discovery_execution_id, str)
            or not self.discovery_execution_id.strip()
        ):
            raise ValueError("discovery_execution_id must be non-empty text")
        if not isinstance(self.discovery_results, tuple):
            raise TypeError("discovery_results must be tuple")
        if not all(
            isinstance(result, DiscoveryResult)
            for result in self.discovery_results
        ):
            raise TypeError(
                "discovery_results must contain DiscoveryResult values"
            )
        if not isinstance(self.collection_facts, tuple):
            raise TypeError("collection_facts must be tuple")
        if not all(
            isinstance(fact, CollectionFact) for fact in self.collection_facts
        ):
            raise TypeError("collection_facts must contain CollectionFact values")


class ProductionDiscoveryRuntime(Protocol):
    """Runs discovery from an already committed command."""

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> ProductionDiscoveryRuntimeResult: ...


@dataclass(frozen=True, slots=True)
class PersistedDiscoveryExecutionResult:
    command_result: PersistDiscoveryCommandResult
    discovery_results: tuple[DiscoveryResult, ...]
    collection_facts: tuple[CollectionFact, ...]

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
        if not isinstance(self.collection_facts, tuple):
            raise TypeError("collection_facts must be tuple")
        if not all(
            isinstance(fact, CollectionFact) for fact in self.collection_facts
        ):
            raise TypeError("collection_facts must contain CollectionFact values")


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
        runtime_result = self._runtime.execute(command_result.command)
        if not isinstance(runtime_result, ProductionDiscoveryRuntimeResult):
            raise TypeError(
                "runtime must return ProductionDiscoveryRuntimeResult"
            )
        if (
            runtime_result.discovery_execution_id
            != command_result.command.discovery_execution_id
        ):
            raise DiscoveryRuntimeCorrelationError(
                "runtime execution identity conflicts with committed command"
            )

        return PersistedDiscoveryExecutionResult(
            command_result=command_result,
            discovery_results=runtime_result.discovery_results,
            collection_facts=runtime_result.collection_facts,
        )


__all__ = [
    "DiscoveryRuntimeCorrelationError",
    "PersistedDiscoveryExecutionEntry",
    "PersistedDiscoveryExecutionResult",
    "ProductionDiscoveryRuntime",
    "ProductionDiscoveryRuntimeResult",
]
