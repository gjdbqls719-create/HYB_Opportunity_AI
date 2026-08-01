from __future__ import annotations

import re


_SEPARATORS = re.compile(r"\s*[:|/\\]+\s*")


def canonicalize_discovery_reference(value: str) -> str:
    """Return a deterministic lowercase ``namespace:identity`` reference."""
    if not isinstance(value, str):
        raise TypeError("discovery_reference must be text")
    cleaned = value.strip().lower()
    canonical = _SEPARATORS.sub(":", cleaned).strip(":")
    parts = tuple(part.strip() for part in canonical.split(":") if part.strip())
    if len(parts) < 2:
        raise ValueError("discovery_reference must contain namespace and identity")
    return ":".join(parts)
