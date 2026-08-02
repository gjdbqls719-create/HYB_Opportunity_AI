from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.application.actual_economics import (
    ActualEconomicsRepository,
    ActualEconomicsSemanticError,
    ActualEconomicsVersionConflictError,
    DuplicateActualEconomicsError,
)
from app.domain.opportunity import (
    ActualEconomics,
    ActualEconomicsAction,
    ActualEconomicsEvent,
    ActualEconomicsStatus,
)


_CURRENT_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_actual_economics (
    opportunity_id TEXT PRIMARY KEY,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    purchase_price TEXT,
    shipping_cost TEXT,
    purchased_at TEXT,
    sale_price TEXT,
    sold_at TEXT,
    marketplace_fee TEXT,
    payment_fee TEXT,
    fixed_fee TEXT,
    settlement_amount TEXT,
    settled_at TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (status IN ('purchase_recorded','sale_recorded','settled'))
)
"""

_EVENT_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_actual_economics_events (
    event_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    occurred_at TEXT NOT NULL,
    currency TEXT,
    purchase_price TEXT,
    shipping_cost TEXT,
    sale_price TEXT,
    marketplace_fee TEXT,
    payment_fee TEXT,
    fixed_fee TEXT,
    settlement_amount TEXT,
    UNIQUE (opportunity_id, version),
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_actual_economics(opportunity_id)
)
"""

_ACTION_STATES = {
    ActualEconomicsAction.RECORD_PURCHASE: (ActualEconomicsStatus.EMPTY, ActualEconomicsStatus.PURCHASE_RECORDED),
    ActualEconomicsAction.RECORD_SALE: (ActualEconomicsStatus.PURCHASE_RECORDED, ActualEconomicsStatus.SALE_RECORDED),
    ActualEconomicsAction.COMPLETE_SETTLEMENT: (ActualEconomicsStatus.SALE_RECORDED, ActualEconomicsStatus.SETTLED),
}


class SQLiteActualEconomicsRepository(ActualEconomicsRepository):
    """Persist actual economics after its transient EMPTY/version 0 state.

    No row represents EMPTY. The first current-state row and history event are
    created together for PURCHASE_RECORDED/version 1.
    """
    def __init__(self, database_path: str | Path = "data/hyb_opportunity.db", *, connection: sqlite3.Connection | None = None) -> None:
        self._owns_connection = connection is None
        if connection is None:
            resolved = str(database_path)
            if resolved != ":memory:":
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(resolved)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._connection:
            self._connection.execute(_CURRENT_TABLE)
            self._connection.execute(_EVENT_TABLE)
            event_columns = {
                row["name"]
                for row in self._connection.execute(
                    "PRAGMA table_info(opportunity_actual_economics_events)"
                )
            }
            if "currency" not in event_columns:
                self._connection.execute(
                    "ALTER TABLE opportunity_actual_economics_events ADD COLUMN currency TEXT"
                )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_actual_economics_events ON opportunity_actual_economics_events(opportunity_id, version)"
            )

    def create(self, economics: ActualEconomics, event: ActualEconomicsEvent) -> None:
        self._validate_create(economics, event)
        try:
            with self._connection:
                self._insert_current(economics)
                self._insert_event(event)
        except sqlite3.IntegrityError as error:
            raise DuplicateActualEconomicsError(economics.opportunity_id) from error

    def get(self, opportunity_id: str) -> ActualEconomics | None:
        row = self._connection.execute(
            "SELECT * FROM opportunity_actual_economics WHERE opportunity_id = ?", (opportunity_id,)
        ).fetchone()
        if row is None:
            return None
        return ActualEconomics._reconstitute(
            opportunity_id=row["opportunity_id"], currency=row["currency"],
            status=ActualEconomicsStatus(row["status"]),
            purchase_price=self._decimal(row["purchase_price"]),
            shipping_cost=self._decimal(row["shipping_cost"]),
            purchased_at=self._datetime(row["purchased_at"]),
            sale_price=self._decimal(row["sale_price"]), sold_at=self._datetime(row["sold_at"]),
            marketplace_fee=self._decimal(row["marketplace_fee"]),
            payment_fee=self._decimal(row["payment_fee"]), fixed_fee=self._decimal(row["fixed_fee"]),
            settlement_amount=self._decimal(row["settlement_amount"]),
            settled_at=self._datetime(row["settled_at"]), version=row["version"],
            created_at=self._datetime(row["created_at"]), updated_at=self._datetime(row["updated_at"]),
        )

    def save_event(self, economics: ActualEconomics, event: ActualEconomicsEvent, *, expected_version: int) -> None:
        row = self._connection.execute(
            "SELECT * FROM opportunity_actual_economics WHERE opportunity_id = ?", (economics.opportunity_id,)
        ).fetchone()
        if row is None:
            raise ActualEconomicsVersionConflictError("actual economics does not exist")
        self._validate_save(economics, event, expected_version, row)
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """UPDATE opportunity_actual_economics SET
                    status=?, purchase_price=?, shipping_cost=?, purchased_at=?, sale_price=?, sold_at=?,
                    marketplace_fee=?, payment_fee=?, fixed_fee=?, settlement_amount=?, settled_at=?,
                    version=?, updated_at=? WHERE opportunity_id=? AND version=?""",
                    self._update_values(economics) + (economics.opportunity_id, expected_version),
                )
                if cursor.rowcount != 1:
                    raise ActualEconomicsVersionConflictError("actual economics was updated concurrently")
                self._insert_event(event)
        except sqlite3.IntegrityError as error:
            raise ActualEconomicsVersionConflictError("actual economics event conflict") from error

    def list_events(self, opportunity_id: str) -> tuple[ActualEconomicsEvent, ...]:
        rows = self._connection.execute(
            "SELECT * FROM opportunity_actual_economics_events WHERE opportunity_id=? ORDER BY version", (opportunity_id,)
        ).fetchall()
        return tuple(ActualEconomicsEvent(
            event_id=row["event_id"], opportunity_id=row["opportunity_id"],
            action=ActualEconomicsAction(row["action"]),
            previous_status=ActualEconomicsStatus(row["previous_status"]),
            new_status=ActualEconomicsStatus(row["new_status"]), version=row["version"],
            occurred_at=self._datetime(row["occurred_at"]), currency=row["currency"],
            purchase_price=self._decimal(row["purchase_price"]),
            shipping_cost=self._decimal(row["shipping_cost"]), sale_price=self._decimal(row["sale_price"]),
            marketplace_fee=self._decimal(row["marketplace_fee"]), payment_fee=self._decimal(row["payment_fee"]),
            fixed_fee=self._decimal(row["fixed_fee"]), settlement_amount=self._decimal(row["settlement_amount"]),
        ) for row in rows)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _insert_current(self, item: ActualEconomics) -> None:
        self._connection.execute(
            """INSERT INTO opportunity_actual_economics
            (opportunity_id,currency,status,purchase_price,shipping_cost,purchased_at,sale_price,sold_at,
             marketplace_fee,payment_fee,fixed_fee,settlement_amount,settled_at,version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", self._current_values(item),
        )

    def _current_values(self, item: ActualEconomics) -> tuple:
        return (
            item.opportunity_id, item.currency, item.status.value, self._str(item.purchase_price),
            self._str(item.shipping_cost), self._iso(item.purchased_at), self._str(item.sale_price),
            self._iso(item.sold_at), self._str(item.marketplace_fee), self._str(item.payment_fee),
            self._str(item.fixed_fee), self._str(item.settlement_amount), self._iso(item.settled_at),
            item.version, item.created_at.isoformat(), item.updated_at.isoformat(),
        )

    def _update_values(self, item: ActualEconomics) -> tuple:
        return (
            item.status.value, self._str(item.purchase_price), self._str(item.shipping_cost),
            self._iso(item.purchased_at), self._str(item.sale_price), self._iso(item.sold_at),
            self._str(item.marketplace_fee), self._str(item.payment_fee), self._str(item.fixed_fee),
            self._str(item.settlement_amount), self._iso(item.settled_at), item.version,
            item.updated_at.isoformat(),
        )

    def _insert_event(self, event: ActualEconomicsEvent) -> None:
        self._connection.execute(
            """INSERT INTO opportunity_actual_economics_events
            (event_id,opportunity_id,action,previous_status,new_status,version,occurred_at,currency,purchase_price,
             shipping_cost,sale_price,marketplace_fee,payment_fee,fixed_fee,settlement_amount)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event.event_id, event.opportunity_id, event.action.value, event.previous_status.value,
             event.new_status.value, event.version, event.occurred_at.isoformat(), event.currency,
             self._str(event.purchase_price), self._str(event.shipping_cost), self._str(event.sale_price),
             self._str(event.marketplace_fee), self._str(event.payment_fee), self._str(event.fixed_fee),
             self._str(event.settlement_amount)),
        )

    @staticmethod
    def _validate_create(item: ActualEconomics, event: ActualEconomicsEvent) -> None:
        if (item.status is not ActualEconomicsStatus.PURCHASE_RECORDED or item.version != 1
                or event.action is not ActualEconomicsAction.RECORD_PURCHASE
                or event.previous_status is not ActualEconomicsStatus.EMPTY
                or event.new_status is not item.status or event.version != item.version
                or event.opportunity_id != item.opportunity_id or event.occurred_at != item.updated_at):
            raise ActualEconomicsSemanticError("invalid actual economics creation event")
        SQLiteActualEconomicsRepository._validate_event_facts(item, event)

    @classmethod
    def _validate_save(cls, item: ActualEconomics, event: ActualEconomicsEvent,
                       expected_version: int, row: sqlite3.Row) -> None:
        persisted_version = row["version"]
        persisted_status = ActualEconomicsStatus(row["status"])
        if persisted_version != expected_version:
            raise ActualEconomicsVersionConflictError(
                f"expected version {expected_version}, found {persisted_version}"
            )
        if item.version != expected_version + 1:
            raise ActualEconomicsSemanticError(
                "aggregate version must advance expected_version exactly once"
            )
        if event.version != item.version:
            raise ActualEconomicsSemanticError(
                "event version does not match aggregate version"
            )
        expected_states = _ACTION_STATES.get(event.action)
        if (expected_states != (persisted_status, item.status)
                or event.previous_status is not persisted_status or event.new_status is not item.status
                or event.opportunity_id != item.opportunity_id or event.occurred_at != item.updated_at):
            raise ActualEconomicsSemanticError("event does not match current and aggregate state")
        if item.currency != row["currency"] or item.created_at != cls._datetime(row["created_at"]):
            raise ActualEconomicsSemanticError("aggregate identity, currency, and created_at are immutable")
        if event.occurred_at < cls._datetime(row["updated_at"]):
            raise ActualEconomicsSemanticError("event timestamp precedes current state")
        cls._validate_event_facts(item, event, persisted_row=row)

    @classmethod
    def _validate_event_facts(
        cls,
        item: ActualEconomics,
        event: ActualEconomicsEvent,
        *,
        persisted_row: sqlite3.Row | None = None,
    ) -> None:
        fact_names = (
            "purchase_price", "shipping_cost", "sale_price", "marketplace_fee",
            "payment_fee", "fixed_fee", "settlement_amount",
        )
        required_by_action = {
            ActualEconomicsAction.RECORD_PURCHASE: {"purchase_price", "shipping_cost"},
            ActualEconomicsAction.RECORD_SALE: {"purchase_price", "shipping_cost", "sale_price"},
            ActualEconomicsAction.COMPLETE_SETTLEMENT: set(fact_names),
        }
        required = required_by_action.get(event.action)
        if required is None:
            raise ActualEconomicsSemanticError("event action is unsupported")

        if event.action is ActualEconomicsAction.RECORD_PURCHASE:
            if event.currency is None or event.currency != item.currency:
                raise ActualEconomicsSemanticError(
                    "purchase event currency does not match aggregate"
                )
        elif event.currency is not None:
            raise ActualEconomicsSemanticError(
                f"{event.action.value} event cannot contain currency"
            )

        for name in fact_names:
            value = getattr(event, name)
            if name in required:
                if value is None or not isinstance(value, Decimal):
                    raise ActualEconomicsSemanticError(
                        f"{event.action.value} event requires Decimal {name}"
                    )
                if value != getattr(item, name):
                    raise ActualEconomicsSemanticError(
                        f"event {name} does not match aggregate"
                    )
            elif value is not None:
                raise ActualEconomicsSemanticError(
                    f"{event.action.value} event cannot contain {name}"
                )

        fact_time_by_action = {
            ActualEconomicsAction.RECORD_PURCHASE: item.purchased_at,
            ActualEconomicsAction.RECORD_SALE: item.sold_at,
            ActualEconomicsAction.COMPLETE_SETTLEMENT: item.settled_at,
        }
        if event.occurred_at != fact_time_by_action[event.action]:
            raise ActualEconomicsSemanticError(
                f"{event.action.value} timestamp does not match aggregate fact timestamp"
            )

        if persisted_row is None:
            return
        prior_fact_names = {
            ActualEconomicsAction.RECORD_SALE: ("purchase_price", "shipping_cost"),
            ActualEconomicsAction.COMPLETE_SETTLEMENT: (
                "purchase_price", "shipping_cost", "sale_price",
            ),
        }.get(event.action, ())
        for name in prior_fact_names:
            persisted = cls._decimal(persisted_row[name])
            if getattr(item, name) != persisted or getattr(event, name) != persisted:
                raise ActualEconomicsSemanticError(
                    f"{name} does not match persisted state"
                )

    @staticmethod
    def _str(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        return Decimal(value) if value is not None else None

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None
