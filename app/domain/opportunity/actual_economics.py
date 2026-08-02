from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _money(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


class ActualEconomicsStatus(StrEnum):
    EMPTY = "empty"
    PURCHASE_RECORDED = "purchase_recorded"
    SALE_RECORDED = "sale_recorded"
    SETTLED = "settled"


class ActualEconomicsAction(StrEnum):
    RECORD_PURCHASE = "record_purchase"
    RECORD_SALE = "record_sale"
    COMPLETE_SETTLEMENT = "complete_settlement"


class InvalidActualEconomicsTransitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActualEconomicsEvent:
    opportunity_id: str
    action: ActualEconomicsAction
    previous_status: ActualEconomicsStatus
    new_status: ActualEconomicsStatus
    version: int
    occurred_at: datetime
    currency: str | None = None
    purchase_price: Decimal | None = None
    shipping_cost: Decimal | None = None
    sale_price: Decimal | None = None
    marketplace_fee: Decimal | None = None
    payment_fee: Decimal | None = None
    fixed_fee: Decimal | None = None
    settlement_amount: Decimal | None = None
    event_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event_id"))
        object.__setattr__(self, "opportunity_id", _required_text(self.opportunity_id, "opportunity_id"))
        if not isinstance(self.action, ActualEconomicsAction):
            object.__setattr__(self, "action", ActualEconomicsAction(self.action))
        if not isinstance(self.previous_status, ActualEconomicsStatus):
            object.__setattr__(self, "previous_status", ActualEconomicsStatus(self.previous_status))
        if not isinstance(self.new_status, ActualEconomicsStatus):
            object.__setattr__(self, "new_status", ActualEconomicsStatus(self.new_status))
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        _aware(self.occurred_at, "occurred_at")
        if self.currency is not None:
            if not isinstance(self.currency, str) or len(self.currency.strip()) != 3 or not self.currency.strip().isalpha():
                raise ValueError("event currency must be a three-letter code")
            object.__setattr__(self, "currency", self.currency.strip().upper())
        for name in (
            "purchase_price", "shipping_cost", "sale_price", "marketplace_fee",
            "payment_fee", "fixed_fee", "settlement_amount",
        ):
            value = getattr(self, name)
            if value is not None:
                _money(value, name)


class ActualEconomics:
    """Actual transaction facts, independent from lifecycle and estimates.

    ``EMPTY``/version 0 is transient-only and represents the absence of a
    database current-state row. The first persisted state is produced by
    ``record_purchase()`` as ``PURCHASE_RECORDED``/version 1. Consequently,
    one opportunity aggregate is created in storage by its first purchase.

    ``sale_price`` is the gross sale price before marketplace, payment, and
    fixed fees. ``settlement_amount`` is a preserved fact only; it is not an
    input to actual profit or ROI and is not reconciled in this foundation.
    """

    __slots__ = (
        "_opportunity_id", "_currency", "_status", "_purchase_price",
        "_shipping_cost", "_purchased_at", "_sale_price", "_sold_at",
        "_marketplace_fee", "_payment_fee", "_fixed_fee",
        "_settlement_amount", "_settled_at", "_version", "_created_at",
        "_updated_at",
    )

    def __init__(
        self,
        opportunity_id: str,
        currency: str,
        *,
        created_at: datetime | None = None,
    ) -> None:
        created = created_at or utc_now()
        self._initialize(
            opportunity_id=opportunity_id,
            currency=currency,
            status=ActualEconomicsStatus.EMPTY,
            purchase_price=None,
            shipping_cost=None,
            purchased_at=None,
            sale_price=None,
            sold_at=None,
            marketplace_fee=None,
            payment_fee=None,
            fixed_fee=None,
            settlement_amount=None,
            settled_at=None,
            version=0,
            created_at=created,
            updated_at=created,
        )

    @classmethod
    def _reconstitute(cls, **state: object) -> ActualEconomics:
        instance = cls.__new__(cls)
        instance._initialize(**state)
        return instance

    def _initialize(
        self,
        *,
        opportunity_id: str,
        currency: str,
        status: ActualEconomicsStatus,
        purchase_price: Decimal | None,
        shipping_cost: Decimal | None,
        purchased_at: datetime | None,
        sale_price: Decimal | None,
        sold_at: datetime | None,
        marketplace_fee: Decimal | None,
        payment_fee: Decimal | None,
        fixed_fee: Decimal | None,
        settlement_amount: Decimal | None,
        settled_at: datetime | None,
        version: int,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        opportunity_id = _required_text(opportunity_id, "opportunity_id")
        if not isinstance(currency, str) or len(currency.strip()) != 3 or not currency.strip().isalpha():
            raise ValueError("currency must be a three-letter code")
        currency = currency.strip().upper()
        if not isinstance(status, ActualEconomicsStatus):
            status = ActualEconomicsStatus(status)
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise ValueError("version must be a non-negative integer")
        _aware(created_at, "created_at")
        _aware(updated_at, "updated_at")
        if updated_at < created_at:
            raise ValueError("updated_at cannot precede created_at")
        for name, value in (
            ("purchase_price", purchase_price), ("shipping_cost", shipping_cost),
            ("sale_price", sale_price), ("marketplace_fee", marketplace_fee),
            ("payment_fee", payment_fee), ("fixed_fee", fixed_fee),
            ("settlement_amount", settlement_amount),
        ):
            if value is not None:
                _money(value, name)
        for name, value in (("purchased_at", purchased_at), ("sold_at", sold_at), ("settled_at", settled_at)):
            if value is not None:
                _aware(value, name)
        self._validate_state(status, purchase_price, shipping_cost, purchased_at, sale_price, sold_at,
                             marketplace_fee, payment_fee, fixed_fee, settlement_amount, settled_at)
        object.__setattr__(self, "_opportunity_id", opportunity_id)
        object.__setattr__(self, "_currency", currency)
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_purchase_price", purchase_price)
        object.__setattr__(self, "_shipping_cost", shipping_cost)
        object.__setattr__(self, "_purchased_at", purchased_at)
        object.__setattr__(self, "_sale_price", sale_price)
        object.__setattr__(self, "_sold_at", sold_at)
        object.__setattr__(self, "_marketplace_fee", marketplace_fee)
        object.__setattr__(self, "_payment_fee", payment_fee)
        object.__setattr__(self, "_fixed_fee", fixed_fee)
        object.__setattr__(self, "_settlement_amount", settlement_amount)
        object.__setattr__(self, "_settled_at", settled_at)
        object.__setattr__(self, "_version", version)
        object.__setattr__(self, "_created_at", created_at)
        object.__setattr__(self, "_updated_at", updated_at)

    @staticmethod
    def _validate_state(status, purchase_price, shipping_cost, purchased_at, sale_price, sold_at,
                        marketplace_fee, payment_fee, fixed_fee, settlement_amount, settled_at) -> None:
        purchase_complete = purchase_price is not None and shipping_cost is not None and purchased_at is not None
        sale_complete = sale_price is not None and sold_at is not None
        settlement_complete = all(value is not None for value in (
            marketplace_fee, payment_fee, fixed_fee, settlement_amount, settled_at,
        ))
        if status is ActualEconomicsStatus.EMPTY and any(value is not None for value in (
            purchase_price, shipping_cost, purchased_at, sale_price, sold_at, marketplace_fee,
            payment_fee, fixed_fee, settlement_amount, settled_at,
        )):
            raise ValueError("empty economics cannot contain transaction facts")
        if status is not ActualEconomicsStatus.EMPTY and not purchase_complete:
            raise ValueError("purchase facts are incomplete")
        if status in {ActualEconomicsStatus.SALE_RECORDED, ActualEconomicsStatus.SETTLED} and not sale_complete:
            raise ValueError("sale facts are incomplete")
        if status is ActualEconomicsStatus.SETTLED and not settlement_complete:
            raise ValueError("settlement facts are incomplete")

    @property
    def opportunity_id(self): return self._opportunity_id
    @property
    def currency(self): return self._currency
    @property
    def status(self): return self._status
    @property
    def purchase_price(self): return self._purchase_price
    @property
    def shipping_cost(self): return self._shipping_cost
    @property
    def purchased_at(self): return self._purchased_at
    @property
    def sale_price(self): return self._sale_price
    @property
    def sold_at(self): return self._sold_at
    @property
    def marketplace_fee(self): return self._marketplace_fee
    @property
    def payment_fee(self): return self._payment_fee
    @property
    def fixed_fee(self): return self._fixed_fee
    @property
    def settlement_amount(self): return self._settlement_amount
    @property
    def settled_at(self): return self._settled_at
    @property
    def version(self): return self._version
    @property
    def created_at(self): return self._created_at
    @property
    def updated_at(self): return self._updated_at

    def record_purchase(self, *, purchase_price: Decimal, shipping_cost: Decimal, occurred_at: datetime) -> ActualEconomicsEvent:
        if self.status is not ActualEconomicsStatus.EMPTY:
            raise InvalidActualEconomicsTransitionError("purchase can only be recorded from EMPTY")
        _money(purchase_price, "purchase_price")
        _money(shipping_cost, "shipping_cost")
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_purchase_price", purchase_price)
        object.__setattr__(self, "_shipping_cost", shipping_cost)
        object.__setattr__(self, "_purchased_at", occurred_at)
        self._advance(ActualEconomicsStatus.PURCHASE_RECORDED, occurred_at)
        return self._event(
            ActualEconomicsAction.RECORD_PURCHASE,
            previous,
            currency=self.currency,
            purchase_price=purchase_price,
            shipping_cost=shipping_cost,
        )

    def record_sale(self, *, sale_price: Decimal, occurred_at: datetime) -> ActualEconomicsEvent:
        """Record the gross sale price before marketplace-related fees."""
        if self.status is not ActualEconomicsStatus.PURCHASE_RECORDED:
            raise InvalidActualEconomicsTransitionError("sale can only be recorded after purchase")
        _money(sale_price, "sale_price")
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_sale_price", sale_price)
        object.__setattr__(self, "_sold_at", occurred_at)
        self._advance(ActualEconomicsStatus.SALE_RECORDED, occurred_at)
        return self._event(
            ActualEconomicsAction.RECORD_SALE,
            previous,
            purchase_price=self.purchase_price,
            shipping_cost=self.shipping_cost,
            sale_price=sale_price,
        )

    def complete_settlement(self, *, marketplace_fee: Decimal, payment_fee: Decimal,
                            fixed_fee: Decimal, settlement_amount: Decimal,
                            occurred_at: datetime) -> ActualEconomicsEvent:
        if self.status is not ActualEconomicsStatus.SALE_RECORDED:
            raise InvalidActualEconomicsTransitionError("settlement can only be completed after sale")
        for name, value in (("marketplace_fee", marketplace_fee), ("payment_fee", payment_fee),
                            ("fixed_fee", fixed_fee), ("settlement_amount", settlement_amount)):
            _money(value, name)
        self._validate_change_time(occurred_at)
        previous = self.status
        object.__setattr__(self, "_marketplace_fee", marketplace_fee)
        object.__setattr__(self, "_payment_fee", payment_fee)
        object.__setattr__(self, "_fixed_fee", fixed_fee)
        object.__setattr__(self, "_settlement_amount", settlement_amount)
        object.__setattr__(self, "_settled_at", occurred_at)
        self._advance(ActualEconomicsStatus.SETTLED, occurred_at)
        return self._event(ActualEconomicsAction.COMPLETE_SETTLEMENT, previous,
                           purchase_price=self.purchase_price, shipping_cost=self.shipping_cost,
                           sale_price=self.sale_price,
                           marketplace_fee=marketplace_fee, payment_fee=payment_fee,
                           fixed_fee=fixed_fee, settlement_amount=settlement_amount)

    def calculate_actual_profit(self) -> Decimal:
        if self.status is not ActualEconomicsStatus.SETTLED:
            raise InvalidActualEconomicsTransitionError("actual profit requires completed settlement")
        return self.sale_price - self.purchase_price - self.shipping_cost - self.marketplace_fee - self.payment_fee - self.fixed_fee

    def calculate_actual_roi(self) -> Decimal:
        if self.status is not ActualEconomicsStatus.SETTLED:
            raise InvalidActualEconomicsTransitionError("actual ROI requires completed settlement")
        if self.purchase_price == 0:
            return Decimal("0")
        return self.calculate_actual_profit() / self.purchase_price * Decimal("100")

    def _validate_change_time(self, occurred_at: datetime) -> None:
        _aware(occurred_at, "occurred_at")
        if occurred_at < self.updated_at:
            raise ValueError("occurred_at cannot precede updated_at")

    def _advance(self, status: ActualEconomicsStatus, occurred_at: datetime) -> None:
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_version", self.version + 1)
        object.__setattr__(self, "_updated_at", occurred_at)

    def _event(
        self,
        action: ActualEconomicsAction,
        previous: ActualEconomicsStatus,
        *,
        currency: str | None = None,
        **facts: Decimal,
    ) -> ActualEconomicsEvent:
        return ActualEconomicsEvent(
            opportunity_id=self.opportunity_id, action=action, previous_status=previous,
            new_status=self.status, version=self.version, occurred_at=self.updated_at,
            currency=currency, **facts,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ActualEconomics):
            return NotImplemented
        return all(getattr(self, name) == getattr(other, name) for name in (
            "opportunity_id", "currency", "status", "purchase_price", "shipping_cost",
            "purchased_at", "sale_price", "sold_at", "marketplace_fee", "payment_fee",
            "fixed_fee", "settlement_amount", "settled_at", "version", "created_at", "updated_at",
        ))

    def __repr__(self) -> str:
        return f"ActualEconomics(opportunity_id={self.opportunity_id!r}, status={self.status!r}, version={self.version!r})"
