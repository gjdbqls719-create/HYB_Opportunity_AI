"""Collector-owned boundary that publishes Candidate-scoped Product snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.domain.discovery_identity import CollectedProductObservation, FinalizedProductGroup
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.product_observation import ProductObservationSnapshot


PRODUCT_SNAPSHOT_CAPTURE_COMMAND_SCHEMA_VERSION = "product-snapshot-capture-command-v1"
PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION = "product-snapshot-source-binding-v1"
PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION = "product-snapshot-capture-receipt-v1"


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CaptureProductSnapshotsCommand:
    command_id: str
    candidate_identity: OpportunityCandidateIdentity
    finalized_group_id: str
    observation_snapshot_ids: tuple[tuple[str, str], ...]
    market_observation_identity: MarketObservationIdentity
    requested_at: datetime
    schema_version: str = PRODUCT_SNAPSHOT_CAPTURE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.command_id, "command_id"); _required(self.finalized_group_id, "finalized_group_id")
        if not isinstance(self.candidate_identity, OpportunityCandidateIdentity): raise TypeError("candidate_identity must be OpportunityCandidateIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity): raise TypeError("market_observation_identity must be MarketObservationIdentity")
        if not isinstance(self.observation_snapshot_ids, tuple) or not self.observation_snapshot_ids: raise ValueError("observation_snapshot_ids must be a non-empty tuple")
        for item in self.observation_snapshot_ids:
            if not isinstance(item, tuple) or len(item) != 2: raise ValueError("observation_snapshot_ids must contain pairs")
            _required(item[0], "observation_id"); _required(item[1], "snapshot_id")
        if len({item[0] for item in self.observation_snapshot_ids}) != len(self.observation_snapshot_ids): raise ValueError("observation IDs must be unique")
        if len({item[1] for item in self.observation_snapshot_ids}) != len(self.observation_snapshot_ids): raise ValueError("snapshot IDs must be unique")
        _aware(self.requested_at, "requested_at")
        if self.schema_version != PRODUCT_SNAPSHOT_CAPTURE_COMMAND_SCHEMA_VERSION: raise ValueError("unsupported capture command version")

    @property
    def fingerprint(self) -> str:
        payload={"candidate":repr(self.candidate_identity),"group":self.finalized_group_id,
            "sources":self.observation_snapshot_ids,"market":repr(self.market_observation_identity),
            "requested_at":self.requested_at.isoformat(),"schema_version":self.schema_version}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProductSnapshotSourceBinding:
    product_snapshot_id: str; collected_observation_id: str; candidate_id: str
    capture_command_id: str; bound_at: datetime
    schema_version: str = PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION
    def __post_init__(self):
        for name in ("product_snapshot_id","collected_observation_id","candidate_id","capture_command_id"): _required(getattr(self,name),name)
        _aware(self.bound_at,"bound_at")
        if self.schema_version != PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION: raise ValueError("unsupported source binding version")


@dataclass(frozen=True, slots=True)
class ProductSnapshotCaptureReceipt:
    command_id: str; command_fingerprint: str; candidate_id: str
    product_snapshot_ids: tuple[str, ...]; committed_at: datetime
    schema_version: str = PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION
    def __post_init__(self):
        for name in ("command_id","command_fingerprint","candidate_id"): _required(getattr(self,name),name)
        if len(self.command_fingerprint)!=64 or any(v not in "0123456789abcdef" for v in self.command_fingerprint): raise ValueError("command_fingerprint must be SHA-256 text")
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids or len(set(self.product_snapshot_ids))!=len(self.product_snapshot_ids): raise ValueError("product_snapshot_ids must be a non-empty unique tuple")
        _aware(self.committed_at,"committed_at")
        if self.schema_version != PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION: raise ValueError("unsupported capture receipt version")


class SnapshotOwnerPersistenceError(RuntimeError): pass
class SnapshotOwnerCommitError(SnapshotOwnerPersistenceError): pass
class SnapshotOwnerCommandConflictError(SnapshotOwnerPersistenceError): pass
class ProductSnapshotSourceObservationNotFoundError(SnapshotOwnerPersistenceError): pass
class ProductSnapshotSourceConflictError(SnapshotOwnerPersistenceError): pass
class ProductSnapshotCaptureHistoryError(SnapshotOwnerPersistenceError): pass
class MalformedProductSnapshotCapturePersistenceError(SnapshotOwnerPersistenceError): pass
class UnsupportedProductSnapshotCaptureVersionError(MalformedProductSnapshotCapturePersistenceError): pass


@dataclass(frozen=True, slots=True)
class ProductSnapshotCaptureResult:
    snapshots: tuple[ProductObservationSnapshot, ...]
    bindings: tuple[ProductSnapshotSourceBinding, ...]
    receipt: ProductSnapshotCaptureReceipt
    replayed: bool


class ProductSnapshotCaptureRepository(Protocol):
    def get_receipt(self, command_id: str) -> ProductSnapshotCaptureReceipt | None: ...
    def get_result(self, receipt: ProductSnapshotCaptureReceipt) -> ProductSnapshotCaptureResult: ...
    def get_candidate_lineage(self, candidate_id: str) -> tuple[str, str, object] | None: ...
    def get_group(self, finalized_group_id: str) -> FinalizedProductGroup | None: ...
    def get_observation(self, observation_id: str) -> CollectedProductObservation | None: ...
    def persist_capture(
        self,
        command: CaptureProductSnapshotsCommand,
        snapshots: tuple[ProductObservationSnapshot, ...],
        bindings: tuple[ProductSnapshotSourceBinding, ...],
        receipt: ProductSnapshotCaptureReceipt,
    ) -> ProductSnapshotCaptureResult: ...


class CaptureProductSnapshots:
    """Copies exact persisted collector facts after Candidate issuance."""

    def __init__(
        self,
        repository: ProductSnapshotCaptureRepository,
        *,
        receipt_clock: Callable[[], datetime],
    ) -> None:
        if not callable(receipt_clock):
            raise TypeError("receipt_clock must be callable")
        self._repository = repository
        self._receipt_clock = receipt_clock

    def execute(self, command: CaptureProductSnapshotsCommand) -> ProductSnapshotCaptureResult:
        if not isinstance(command, CaptureProductSnapshotsCommand):
            raise TypeError("command must be CaptureProductSnapshotsCommand")
        existing = self._repository.get_receipt(command.command_id)
        if existing is not None:
            if existing.command_fingerprint != command.fingerprint:
                raise SnapshotOwnerCommandConflictError("capture command payload conflicts")
            result = self._repository.get_result(existing)
            return ProductSnapshotCaptureResult(
                result.snapshots, result.bindings, result.receipt, True
            )

        lineage = self._repository.get_candidate_lineage(
            command.candidate_identity.candidate_id
        )
        if lineage is None:
            raise ProductSnapshotSourceConflictError("Candidate lineage is missing")
        discovery_reference, finalized_group_id, market_identity = lineage
        if (
            discovery_reference != command.candidate_identity.discovery_reference
            or finalized_group_id != command.finalized_group_id
            or market_identity != command.market_observation_identity
        ):
            raise ProductSnapshotSourceConflictError("Candidate source lineage differs")

        group = self._repository.get_group(command.finalized_group_id)
        if group is None:
            raise ProductSnapshotSourceConflictError("finalized Product group is missing")
        requested_observation_ids = tuple(
            observation_id for observation_id, _ in command.observation_snapshot_ids
        )
        if requested_observation_ids != group.observation_ids:
            raise ProductSnapshotSourceConflictError(
                "capture sources must exactly preserve finalized group order"
            )

        observations = []
        for observation_id in requested_observation_ids:
            observation = self._repository.get_observation(observation_id)
            if observation is None:
                raise ProductSnapshotSourceObservationNotFoundError(observation_id)
            if observation.discovery_execution_id != group.discovery_execution_id:
                raise ProductSnapshotSourceConflictError(
                    "collector observation execution lineage differs"
                )
            if (
                observation.candidate_market_identity is not None
                and observation.candidate_market_identity
                != command.market_observation_identity
            ):
                raise ProductSnapshotSourceConflictError(
                    "explicit collector observation Market identity differs"
                )
            observations.append(observation)

        committed_at = self._receipt_clock()
        if (
            not isinstance(committed_at, datetime)
            or committed_at.tzinfo is None
            or committed_at.utcoffset() is None
        ):
            raise ValueError("receipt_clock must return a timezone-aware datetime")
        snapshots = tuple(
            ProductObservationSnapshot(
                snapshot_id=snapshot_id,
                candidate_identity=command.candidate_identity,
                market_observation_identity=command.market_observation_identity,
                product=observation.product,
                collector_provenance=observation.collector_provenance,
                observed_at=observation.observed_at,
            )
            for observation, (_, snapshot_id) in zip(
                observations, command.observation_snapshot_ids, strict=True
            )
        )
        bindings = tuple(
            ProductSnapshotSourceBinding(
                product_snapshot_id=snapshot.snapshot_id,
                collected_observation_id=observation.observation_id,
                candidate_id=command.candidate_identity.candidate_id,
                capture_command_id=command.command_id,
                bound_at=committed_at,
            )
            for snapshot, observation in zip(snapshots, observations, strict=True)
        )
        receipt = ProductSnapshotCaptureReceipt(
            command_id=command.command_id,
            command_fingerprint=command.fingerprint,
            candidate_id=command.candidate_identity.candidate_id,
            product_snapshot_ids=tuple(value.snapshot_id for value in snapshots),
            committed_at=committed_at,
        )
        return self._repository.persist_capture(command, snapshots, bindings, receipt)


__all__ = [
    "CaptureProductSnapshotsCommand", "ProductSnapshotSourceBinding",
    "ProductSnapshotCaptureReceipt", "PRODUCT_SNAPSHOT_CAPTURE_COMMAND_SCHEMA_VERSION",
    "PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION", "PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION",
    "CaptureProductSnapshots", "ProductSnapshotCaptureRepository",
    "ProductSnapshotCaptureResult", "SnapshotOwnerPersistenceError",
    "SnapshotOwnerCommitError", "SnapshotOwnerCommandConflictError",
    "ProductSnapshotSourceObservationNotFoundError",
    "ProductSnapshotSourceConflictError", "ProductSnapshotCaptureHistoryError",
    "MalformedProductSnapshotCapturePersistenceError",
    "UnsupportedProductSnapshotCaptureVersionError",
]
