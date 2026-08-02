from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re

from app.domain.market_intelligence.external_signal import ExternalSignalSourceType


class ArtifactType(StrEnum):
    SCREENSHOT = "screenshot"
    IMAGE = "image"
    PDF = "pdf"


class ArtifactOrigin(StrEnum):
    ITEMSCOUT = "itemscout"
    COUPANG = "coupang"
    MANUAL = "manual"
    UNKNOWN = "unknown"
    OTHER = "other"


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Immutable metadata reference; artifact bytes are intentionally external."""

    artifact_id: str
    artifact_type: ArtifactType
    artifact_origin: ArtifactOrigin
    source_type: ExternalSignalSourceType
    sha256: str
    captured_at: datetime
    width: int
    height: int
    mime_type: str
    file_size: int
    schema_version: str

    def __post_init__(self) -> None:
        try:
            artifact_type = ArtifactType(self.artifact_type)
        except ValueError as error:
            raise ValueError("unsupported artifact type") from error
        try:
            artifact_origin = ArtifactOrigin(self.artifact_origin)
        except ValueError as error:
            raise ValueError("unsupported artifact origin") from error
        try:
            source_type = ExternalSignalSourceType(self.source_type)
        except ValueError as error:
            raise ValueError("unsupported artifact source type") from error
        sha256 = _required_text(self.sha256, "sha256")
        if not _SHA256.fullmatch(sha256):
            raise ValueError("sha256 must be exactly 64 hexadecimal characters")
        if isinstance(self.file_size, bool) or not isinstance(self.file_size, int):
            raise TypeError("file_size must be int")
        if self.file_size < 0:
            raise ValueError("file_size cannot be negative")

        object.__setattr__(self, "artifact_id", _required_text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "artifact_type", artifact_type)
        object.__setattr__(self, "artifact_origin", artifact_origin)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "sha256", sha256.lower())
        object.__setattr__(self, "captured_at", _aware(self.captured_at, "captured_at"))
        object.__setattr__(self, "width", _positive_int(self.width, "width"))
        object.__setattr__(self, "height", _positive_int(self.height, "height"))
        object.__setattr__(self, "mime_type", _required_text(self.mime_type, "mime_type").lower())
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
