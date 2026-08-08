"""Foundation application contracts for authoritative FX observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Protocol

from app.domain.sourcing import FXObservation, FXObservationProvenance, FX_OBSERVATION_SCHEMA_VERSION

FX_OBSERVATION_COMMAND_SCHEMA_VERSION = "fx-observation-command-v1"


class FXObservationAuthorityError(RuntimeError):
    """Raised for FX observation authority-level failures."""


class FXObservationReplayConflictError(FXObservationAuthorityError):
    """Raised when replay payload is semantically different from persisted history."""


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _canonical_payload(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_payload(item) for item in value]
    if isinstance(value, Decimal):
        # preserve value stability for fingerprinting
        return format(value, "f")
    return value


def _sha256(payload: object) -> str:
    serialized = json.dumps(
        _canonical_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class FXObservationRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> "FXObservationAdmissionResult | None": ...
    def save_observation(
        self,
        command: "AdmitFXObservationCommand",
        observation: FXObservation,
    ) -> "FXObservationAdmissionResult": ...


@dataclass(frozen=True, slots=True)
class AdmitFXObservationCommand:
    command_id: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    observed_at: datetime
    provider: str
    source_reference: str | None = None
    collection_method: str | None = None
    schema_version: str = FX_OBSERVATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "base_currency", _text(self.base_currency, "base_currency").upper())
        object.__setattr__(self, "quote_currency", _text(self.quote_currency, "quote_currency").upper())
        if self.base_currency == self.quote_currency:
            raise ValueError("base and quote currencies must differ")
        if not isinstance(self.rate, Decimal):
            raise TypeError("rate must be Decimal")
        if not self.rate.is_finite():
            raise ValueError("rate must be finite")
        if self.rate <= 0:
            raise ValueError("rate must be greater than zero")
        _aware(self.observed_at, "observed_at")
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        if self.source_reference is not None:
            object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))
        if self.collection_method is not None:
            object.__setattr__(self, "collection_method", _text(self.collection_method, "collection_method"))
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != FX_OBSERVATION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported FX observation command version")

    @property
    def fingerprint(self) -> str:
        payload = {
            "command_id": self.command_id,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "rate": format(self.rate, "f"),
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "provider": self.provider,
            "source_reference": self.source_reference,
            "collection_method": self.collection_method,
            "schema_version": self.schema_version,
        }
        return _sha256(payload)


@dataclass(frozen=True, slots=True)
class FXObservationAdmissionResult:
    observation: FXObservation
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.observation, FXObservation):
            raise TypeError("observation must be FXObservation")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class AdmitFXObservation:
    """
    Authoritative admission boundary for one FX observation fact.

    This boundary performs only validation and source conversion into authoritative
    Domain facts. It does not perform FX conversion, inverse derivation, freshness
    policy, or downstream normalization.
    """

    def __init__(
        self,
        repository: FXObservationRepository,
        *,
        observation_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
    ) -> None:
        if not callable(observation_id_generator):
            raise TypeError("observation_id_generator must be callable")
        if not callable(admitted_clock):
            raise TypeError("admitted_clock must be callable")
        self._repository = repository
        self._identity = observation_id_generator
        self._admitted_clock = admitted_clock

    def execute(self, command: AdmitFXObservationCommand) -> FXObservationAdmissionResult:
        if not isinstance(command, AdmitFXObservationCommand):
            raise TypeError("command must be AdmitFXObservationCommand")

        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return FXObservationAdmissionResult(
                observation=replay.observation,
                replayed=True,
            )

        observation = FXObservation(
            observation_id=_text(self._identity(), "observation_id"),
            base_currency=command.base_currency,
            quote_currency=command.quote_currency,
            rate=command.rate,
            observed_at=command.observed_at,
            admitted_at=_aware(self._admitted_clock(), "admitted_at"),
            provenance=FXObservationProvenance(
                provider=command.provider,
                source_reference=command.source_reference,
                collection_method=command.collection_method,
            ),
            schema_version=FX_OBSERVATION_SCHEMA_VERSION,
        )
        return self._repository.save_observation(command, observation)


__all__ = [
    "AdmitFXObservation",
    "AdmitFXObservationCommand",
    "FXObservationAuthorityError",
    "FXObservationReplayConflictError",
    "FXObservationRepository",
    "FXObservationAdmissionResult",
    "FX_OBSERVATION_COMMAND_SCHEMA_VERSION",
]
