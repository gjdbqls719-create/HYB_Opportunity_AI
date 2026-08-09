"""Small production clock for authoritative UTC timestamps."""

from datetime import datetime, timezone


class ProductionUTCClock:
    """Return one timezone-aware UTC timestamp per call."""

    __slots__ = ()

    def __call__(self) -> datetime:
        return datetime.now(timezone.utc)


__all__ = ["ProductionUTCClock"]
