"""Persistence command and result contracts for one Shadow registration boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Protocol

from app.domain.opportunity import (
    ShadowBaselineSnapshot,
    ShadowValidationRegistration,
    shadow_baseline_snapshot_to_canonical_data,
    shadow_validation_registration_to_canonical_data,
)


PERSIST_SHADOW_REGISTRATION_COMMAND_SCHEMA_VERSION = (
    "persist-shadow-registration-command-v1"
)
SHADOW_REGISTRATION_RECEIPT_SCHEMA_VERSION = "shadow-registration-receipt-v1"


class ShadowRegistrationPersistenceError(RuntimeError):
    pass


class ShadowRegistrationReplayConflictError(ShadowRegistrationPersistenceError):
    pass


class ShadowRegistrationHistoryError(ShadowRegistrationPersistenceError):
    pass


class ShadowRegistrationReceiptError(ShadowRegistrationPersistenceError):
    pass


class ShadowRegistrationCommitError(ShadowRegistrationPersistenceError):
    pass


class MalformedShadowRegistrationPersistenceError(
    ShadowRegistrationPersistenceError
):
    pass


class UnsupportedShadowRegistrationPersistenceVersionError(
    MalformedShadowRegistrationPersistenceError
):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical_time(value: datetime) -> str:
    return (
        _aware(value, "canonical datetime")
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fingerprint(value: str, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be lowercase SHA-256 text")
    return value


@dataclass(frozen=True, slots=True)
class PersistShadowRegistrationCommand:
    command_id: str
    registration: ShadowValidationRegistration
    baseline: ShadowBaselineSnapshot
    committed_at: datetime
    schema_version: str = PERSIST_SHADOW_REGISTRATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.registration, ShadowValidationRegistration):
            raise TypeError("registration must be ShadowValidationRegistration")
        if not isinstance(self.baseline, ShadowBaselineSnapshot):
            raise TypeError("baseline must be ShadowBaselineSnapshot")
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.committed_at < self.baseline.baseline_created_at:
            raise ValueError("committed_at cannot precede baseline creation")
        reference = self.baseline.registration
        if (
            reference.shadow_validation_id != self.registration.shadow_validation_id
            or reference.baseline_snapshot_id != self.registration.baseline_snapshot_id
            or reference.registration_fingerprint
            != self.registration.integrity_fingerprint
            or reference.subject_lineage_fingerprint
            != self.registration.subject.integrity_fingerprint
            or reference.screening_lineage_fingerprint
            != self.registration.screening_lineage.integrity_fingerprint
        ):
            raise ValueError("Registration and Baseline authority binding differs")
        if self.schema_version != PERSIST_SHADOW_REGISTRATION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow persistence command schema")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "registration": shadow_validation_registration_to_canonical_data(
                    self.registration
                ),
                "baseline": shadow_baseline_snapshot_to_canonical_data(self.baseline),
                "committed_at": _canonical_time(self.committed_at),
                "schema_version": self.schema_version,
            }
        )


@dataclass(frozen=True, slots=True)
class ShadowRegistrationReceipt:
    command_id: str
    shadow_validation_id: str
    baseline_snapshot_id: str
    command_fingerprint: str
    registration_fingerprint: str
    baseline_fingerprint: str
    committed_at: datetime
    schema_version: str = SHADOW_REGISTRATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "shadow_validation_id", "baseline_snapshot_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "command_fingerprint",
            "registration_fingerprint",
            "baseline_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != SHADOW_REGISTRATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow registration receipt schema")

    @classmethod
    def from_command(
        cls, command: PersistShadowRegistrationCommand
    ) -> "ShadowRegistrationReceipt":
        if not isinstance(command, PersistShadowRegistrationCommand):
            raise TypeError("command must be PersistShadowRegistrationCommand")
        return cls(
            command_id=command.command_id,
            shadow_validation_id=command.registration.shadow_validation_id,
            baseline_snapshot_id=command.registration.baseline_snapshot_id,
            command_fingerprint=command.fingerprint,
            registration_fingerprint=command.registration.integrity_fingerprint,
            baseline_fingerprint=command.baseline.integrity_fingerprint,
            committed_at=command.committed_at,
        )


@dataclass(frozen=True, slots=True)
class ShadowRegistrationPersistenceResult:
    registration: ShadowValidationRegistration
    baseline: ShadowBaselineSnapshot
    receipt: ShadowRegistrationReceipt
    replayed: bool
    aliased: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.registration, ShadowValidationRegistration):
            raise TypeError("registration must be ShadowValidationRegistration")
        if not isinstance(self.baseline, ShadowBaselineSnapshot):
            raise TypeError("baseline must be ShadowBaselineSnapshot")
        if not isinstance(self.receipt, ShadowRegistrationReceipt):
            raise TypeError("receipt must be ShadowRegistrationReceipt")
        if not isinstance(self.replayed, bool) or not isinstance(self.aliased, bool):
            raise TypeError("replayed and aliased must be bool")
        if self.replayed and self.aliased:
            raise ValueError("exact replay cannot also be a command alias")
        if (
            self.receipt.shadow_validation_id != self.registration.shadow_validation_id
            or self.receipt.baseline_snapshot_id != self.baseline.baseline_snapshot_id
            or self.receipt.registration_fingerprint
            != self.registration.integrity_fingerprint
            or self.receipt.baseline_fingerprint != self.baseline.integrity_fingerprint
        ):
            raise ValueError("receipt differs from persisted Shadow bundle")


class ShadowRegistrationBaselineRepository(Protocol):
    def save(
        self, command: PersistShadowRegistrationCommand
    ) -> ShadowRegistrationPersistenceResult: ...

    def get_registration(
        self, shadow_validation_id: str
    ) -> ShadowValidationRegistration | None: ...

    def get_baseline(
        self, baseline_snapshot_id: str
    ) -> ShadowBaselineSnapshot | None: ...

    def get_bundle(
        self, shadow_validation_id: str
    ) -> ShadowRegistrationPersistenceResult | None: ...


__all__ = [
    name
    for name in globals()
    if name.startswith("Shadow")
    or name.startswith("PersistShadow")
    or name.startswith("MalformedShadow")
    or name.startswith("UnsupportedShadow")
    or name.startswith("PERSIST_SHADOW")
    or name.startswith("SHADOW_REGISTRATION_RECEIPT")
]
