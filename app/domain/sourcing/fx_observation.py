"""Domain contracts for authoritative FX observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


FX_OBSERVATION_SCHEMA_VERSION = "fx-observation-v1"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _currency_code(value: str, name: str) -> str:
    text = _text(value, name)
    normalized = text.upper()
    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
        raise ValueError(f"{name} must be a 3-letter ISO currency code")
    return normalized


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _decimal_rate(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class FXObservationProvenance:
    provider: str
    source_reference: str | None = None
    collection_method: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        if self.source_reference is not None:
            object.__setattr__(
                self,
                "source_reference",
                _text(self.source_reference, "source_reference"),
            )
        if self.collection_method is not None:
            object.__setattr__(
                self,
                "collection_method",
                _text(self.collection_method, "collection_method"),
            )


@dataclass(frozen=True, slots=True)
class FXObservation:
    observation_id: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    observed_at: datetime
    admitted_at: datetime
    provenance: FXObservationProvenance
    schema_version: str = FX_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text(self.observation_id, "observation_id"))
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        object.__setattr__(self, "quote_currency", _currency_code(self.quote_currency, "quote_currency"))
        if self.base_currency == self.quote_currency:
            raise ValueError("base and quote currencies must differ")
        object.__setattr__(self, "rate", _decimal_rate(self.rate, "rate"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "admitted_at", _aware(self.admitted_at, "admitted_at"))
        if not isinstance(self.provenance, FXObservationProvenance):
            raise TypeError("provenance must be FXObservationProvenance")
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        if self.schema_version != FX_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("unsupported FX observation schema")

    @property
    def pair(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"


__all__ = [
    "FX_OBSERVATION_SCHEMA_VERSION",
    "FXObservation",
    "FXObservationProvenance",
]
