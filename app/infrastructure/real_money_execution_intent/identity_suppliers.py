"""Production opaque identity for Real-Money Execution Intents."""

from uuid import uuid4


class ProductionRealMoneyExecutionIntentIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionRealMoneyExecutionIntentIdentityGenerator"]
