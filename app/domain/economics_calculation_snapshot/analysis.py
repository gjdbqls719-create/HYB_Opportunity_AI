"""Canonical immutable representation of runtime Economics analysis values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
import hashlib
import json
from math import isfinite
from typing import Mapping


ECONOMICS_ANALYSIS_SCHEMA_VERSION = "economics-analysis-v1"


class UnsupportedEconomicsAnalysisValueError(TypeError):
    pass


class EconomicsAnalysisValueKind(StrEnum):
    NONE = "none"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    DECIMAL = "decimal"
    STRING = "string"
    ENUM = "enum"
    DATETIME = "datetime"
    TUPLE = "tuple"
    LIST = "list"
    MAPPING = "mapping"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _enum_type_name(value: Enum | type[Enum]) -> str:
    enum_type = value if isinstance(value, type) else type(value)
    return f"{enum_type.__module__}.{enum_type.__qualname__}"


@dataclass(frozen=True, slots=True)
class CanonicalEconomicsAnalysisValue:
    kind: EconomicsAnalysisValueKind
    scalar: object = None
    items: tuple[CanonicalEconomicsAnalysisValue, ...] = ()
    entries: tuple[tuple[str, CanonicalEconomicsAnalysisValue], ...] = ()
    enum_type: str | None = None
    enum_value: CanonicalEconomicsAnalysisValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EconomicsAnalysisValueKind):
            raise TypeError("analysis value kind must be EconomicsAnalysisValueKind")
        if not isinstance(self.items, tuple) or not isinstance(self.entries, tuple):
            raise TypeError("canonical analysis collections must be tuples")
        for item in self.items:
            if not isinstance(item, CanonicalEconomicsAnalysisValue):
                raise TypeError("canonical analysis items must be canonical values")
        keys: list[str] = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("canonical mapping entries must be key/value tuples")
            key, value = entry
            _required_text(key, "analysis mapping key")
            if not isinstance(value, CanonicalEconomicsAnalysisValue):
                raise TypeError("canonical mapping values must be canonical values")
            keys.append(key)
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            raise ValueError("canonical mapping entries must be unique and sorted")

        scalar_kinds = {
            EconomicsAnalysisValueKind.BOOL: bool,
            EconomicsAnalysisValueKind.INT: int,
            EconomicsAnalysisValueKind.FLOAT: float,
            EconomicsAnalysisValueKind.DECIMAL: Decimal,
            EconomicsAnalysisValueKind.STRING: str,
            EconomicsAnalysisValueKind.DATETIME: datetime,
        }
        if self.kind is EconomicsAnalysisValueKind.NONE:
            if self.scalar is not None:
                raise ValueError("none analysis values cannot carry a scalar")
        elif self.kind in scalar_kinds:
            expected = scalar_kinds[self.kind]
            if type(self.scalar) is not expected:
                raise TypeError(f"{self.kind.value} analysis scalar has the wrong type")
            if isinstance(self.scalar, float) and not isfinite(self.scalar):
                raise ValueError("analysis float values must be finite")
            if isinstance(self.scalar, Decimal) and not self.scalar.is_finite():
                raise ValueError("analysis Decimal values must be finite")
            if isinstance(self.scalar, datetime) and (
                self.scalar.tzinfo is None or self.scalar.utcoffset() is None
            ):
                raise ValueError("analysis datetime values must be timezone-aware")
        elif self.kind is EconomicsAnalysisValueKind.ENUM:
            _required_text(self.scalar, "analysis Enum member")
            _required_text(self.enum_type, "analysis Enum type")
            if not isinstance(self.enum_value, CanonicalEconomicsAnalysisValue):
                raise TypeError("analysis Enum value must be canonical")
        elif self.kind in {
            EconomicsAnalysisValueKind.TUPLE,
            EconomicsAnalysisValueKind.LIST,
        }:
            if self.scalar is not None or self.entries:
                raise ValueError("sequence analysis values may only carry items")
        elif self.kind is EconomicsAnalysisValueKind.MAPPING:
            if self.scalar is not None or self.items:
                raise ValueError("mapping analysis values may only carry entries")
        if self.kind is not EconomicsAnalysisValueKind.ENUM and self.enum_type is not None:
            raise ValueError("only Enum analysis values may carry enum_type")
        if self.kind is not EconomicsAnalysisValueKind.ENUM and self.enum_value is not None:
            raise ValueError("only Enum analysis values may carry enum_value")
        if self.kind not in {
            EconomicsAnalysisValueKind.TUPLE,
            EconomicsAnalysisValueKind.LIST,
        } and self.items:
            raise ValueError("only sequence analysis values may carry items")
        if self.kind is not EconomicsAnalysisValueKind.MAPPING and self.entries:
            raise ValueError("only mapping analysis values may carry entries")

    @classmethod
    def from_runtime(
        cls, value: object, *, _ancestors: frozenset[int] = frozenset()
    ) -> CanonicalEconomicsAnalysisValue:
        if value is None:
            return cls(EconomicsAnalysisValueKind.NONE)
        if isinstance(value, Enum):
            return cls(
                EconomicsAnalysisValueKind.ENUM,
                scalar=value.name,
                enum_type=_enum_type_name(value),
                enum_value=cls.from_runtime(value.value, _ancestors=_ancestors),
            )
        if isinstance(value, bool):
            return cls(EconomicsAnalysisValueKind.BOOL, scalar=value)
        if isinstance(value, int):
            return cls(EconomicsAnalysisValueKind.INT, scalar=value)
        if isinstance(value, float):
            if not isfinite(value):
                raise UnsupportedEconomicsAnalysisValueError(
                    "analysis float values must be finite"
                )
            return cls(EconomicsAnalysisValueKind.FLOAT, scalar=value)
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise UnsupportedEconomicsAnalysisValueError(
                    "analysis Decimal values must be finite"
                )
            return cls(EconomicsAnalysisValueKind.DECIMAL, scalar=value)
        if isinstance(value, str):
            return cls(EconomicsAnalysisValueKind.STRING, scalar=value)
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise UnsupportedEconomicsAnalysisValueError(
                    "analysis datetime values must be timezone-aware"
                )
            return cls(EconomicsAnalysisValueKind.DATETIME, scalar=value)
        if isinstance(value, (tuple, list, Mapping)):
            identity = id(value)
            if identity in _ancestors:
                raise UnsupportedEconomicsAnalysisValueError(
                    "cyclic analysis values are unsupported"
                )
            ancestors = _ancestors | {identity}
            if isinstance(value, Mapping):
                entries: list[tuple[str, CanonicalEconomicsAnalysisValue]] = []
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise UnsupportedEconomicsAnalysisValueError(
                            "analysis mapping keys must be text"
                        )
                    entries.append((key, cls.from_runtime(item, _ancestors=ancestors)))
                entries.sort(key=lambda entry: entry[0])
                return cls(EconomicsAnalysisValueKind.MAPPING, entries=tuple(entries))
            kind = (
                EconomicsAnalysisValueKind.TUPLE
                if isinstance(value, tuple)
                else EconomicsAnalysisValueKind.LIST
            )
            return cls(
                kind,
                items=tuple(cls.from_runtime(item, _ancestors=ancestors) for item in value),
            )
        raise UnsupportedEconomicsAnalysisValueError(
            f"unsupported analysis value type: {type(value).__module__}.{type(value).__qualname__}"
        )

    def to_runtime(self, enum_types: Mapping[str, type[Enum]]) -> object:
        if self.kind is EconomicsAnalysisValueKind.NONE:
            return None
        if self.kind in {
            EconomicsAnalysisValueKind.BOOL,
            EconomicsAnalysisValueKind.INT,
            EconomicsAnalysisValueKind.FLOAT,
            EconomicsAnalysisValueKind.DECIMAL,
            EconomicsAnalysisValueKind.STRING,
            EconomicsAnalysisValueKind.DATETIME,
        }:
            return self.scalar
        if self.kind is EconomicsAnalysisValueKind.ENUM:
            enum_type = enum_types.get(self.enum_type or "")
            if enum_type is None:
                raise UnsupportedEconomicsAnalysisValueError(
                    f"unsupported analysis Enum type: {self.enum_type}"
                )
            try:
                member = enum_type[str(self.scalar)]
            except KeyError as error:
                raise UnsupportedEconomicsAnalysisValueError(
                    f"unsupported analysis Enum member: {self.enum_type}.{self.scalar}"
                ) from error
            expected_value = self.enum_value.to_runtime(enum_types)
            if type(member.value) is not type(expected_value) or member.value != expected_value:
                raise UnsupportedEconomicsAnalysisValueError(
                    f"analysis Enum value changed: {self.enum_type}.{self.scalar}"
                )
            return member
        if self.kind is EconomicsAnalysisValueKind.TUPLE:
            return tuple(item.to_runtime(enum_types) for item in self.items)
        if self.kind is EconomicsAnalysisValueKind.LIST:
            return [item.to_runtime(enum_types) for item in self.items]
        if self.kind is EconomicsAnalysisValueKind.MAPPING:
            return {key: item.to_runtime(enum_types) for key, item in self.entries}
        raise UnsupportedEconomicsAnalysisValueError(
            f"unsupported canonical analysis kind: {self.kind}"
        )

    def fingerprint_value(self) -> object:
        if self.kind is EconomicsAnalysisValueKind.DECIMAL:
            scalar = str(self.scalar)
        elif self.kind is EconomicsAnalysisValueKind.DATETIME:
            scalar = self.scalar.isoformat()
        else:
            scalar = self.scalar
        return {
            "kind": self.kind.value,
            "scalar": scalar,
            "enum_type": self.enum_type,
            "enum_value": (
                self.enum_value.fingerprint_value()
                if self.enum_value is not None
                else None
            ),
            "items": [item.fingerprint_value() for item in self.items],
            "entries": [
                [key, item.fingerprint_value()] for key, item in self.entries
            ],
        }


@dataclass(frozen=True, slots=True)
class EconomicsAnalysisSnapshot:
    entries: tuple[tuple[str, CanonicalEconomicsAnalysisValue], ...]
    analysis_version: str = ECONOMICS_ANALYSIS_SCHEMA_VERSION
    fingerprint: str = ""

    @classmethod
    def from_runtime(
        cls,
        analysis: Mapping[str, object],
        *,
        analysis_version: str = ECONOMICS_ANALYSIS_SCHEMA_VERSION,
    ) -> EconomicsAnalysisSnapshot:
        if not isinstance(analysis, Mapping):
            raise TypeError("analysis must be a Mapping")
        value = CanonicalEconomicsAnalysisValue.from_runtime(analysis)
        return cls(value.entries, analysis_version)

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise TypeError("analysis entries must be a tuple")
        keys: list[str] = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("analysis entries must contain key/value tuples")
            key, value = entry
            _required_text(key, "analysis key")
            if not isinstance(value, CanonicalEconomicsAnalysisValue):
                raise TypeError("analysis values must be canonical values")
            keys.append(key)
        if keys != sorted(keys):
            raise ValueError("analysis entries must use deterministic key ordering")
        if len(set(keys)) != len(keys):
            raise ValueError("analysis keys must be unique")
        _required_text(self.analysis_version, "analysis_version")
        expected = self._fingerprint()
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("analysis fingerprint does not match canonical content")
        object.__setattr__(self, "fingerprint", expected)

    def to_runtime_mapping(
        self, enum_types: tuple[type[Enum], ...] = ()
    ) -> dict[str, object]:
        registry: dict[str, type[Enum]] = {}
        for enum_type in enum_types:
            if not isinstance(enum_type, type) or not issubclass(enum_type, Enum):
                raise TypeError("enum_types must contain Enum classes")
            registry[_enum_type_name(enum_type)] = enum_type
        return {key: value.to_runtime(registry) for key, value in self.entries}

    def _fingerprint(self) -> str:
        payload = {
            "analysis_version": self.analysis_version,
            "entries": [
                [key, value.fingerprint_value()] for key, value in self.entries
            ],
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
