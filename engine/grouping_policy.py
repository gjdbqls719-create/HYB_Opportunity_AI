from __future__ import annotations

from dataclasses import dataclass


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    resolved = value.strip()
    if not resolved:
        raise ValueError(f"{name} must be non-empty text")
    return resolved


@dataclass(frozen=True, slots=True)
class GroupingPolicyDescriptor:
    """Engine-owned semantic identity of a grouping implementation."""

    policy_name: str
    policy_version: str

    def __post_init__(self) -> None:
        for name in ("policy_name", "policy_version"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), name),
            )


__all__ = ["GroupingPolicyDescriptor"]
