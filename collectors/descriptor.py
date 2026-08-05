from __future__ import annotations

from dataclasses import dataclass


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class CollectorDescriptor:
    """Collector-owned implementation identity."""

    collector_name: str
    collector_version: str

    def __post_init__(self) -> None:
        for name in ("collector_name", "collector_version"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), name),
            )


__all__ = ["CollectorDescriptor"]
