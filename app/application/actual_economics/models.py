from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RecordActualPurchase:
    opportunity_id: str
    currency: str
    purchase_price: Decimal
    shipping_cost: Decimal
    occurred_at: datetime
    expected_version: int = 0


@dataclass(frozen=True, slots=True)
class RecordActualSale:
    """Record a gross sale price before marketplace, payment, and fixed fees."""

    opportunity_id: str
    sale_price: Decimal
    occurred_at: datetime
    expected_version: int


@dataclass(frozen=True, slots=True)
class CompleteSettlement:
    """Preserve settlement facts; settlement_amount is not profit or ROI input."""

    opportunity_id: str
    marketplace_fee: Decimal
    payment_fee: Decimal
    fixed_fee: Decimal
    settlement_amount: Decimal
    occurred_at: datetime
    expected_version: int


@dataclass(frozen=True, slots=True)
class GetActualEconomics:
    opportunity_id: str
