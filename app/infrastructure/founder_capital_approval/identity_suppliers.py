"""Production opaque identity supplier for Founder Capital Approval."""

from uuid import uuid4


class ProductionFounderCapitalApprovalIdentityGenerator:
    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionFounderCapitalApprovalIdentityGenerator"]
