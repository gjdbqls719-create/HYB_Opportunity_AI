from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.application.economics_variance import (
    DuplicateEstimatedBaselineError,
    EstimatedEconomicsSnapshotRepository,
)
from app.domain.opportunity import (
    EconomicEvidence,
    EstimatedEconomicsSnapshot,
    EvidenceStatus,
)


SNAPSHOT_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_estimated_economics_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    baseline_kind TEXT NOT NULL,
    currency TEXT NOT NULL,
    purchase_price TEXT NOT NULL,
    shipping_cost TEXT NOT NULL,
    expected_sale_price TEXT NOT NULL,
    marketplace_fee TEXT NOT NULL,
    payment_fee TEXT NOT NULL,
    fixed_fee TEXT NOT NULL,
    expected_profit TEXT NOT NULL,
    expected_roi TEXT NOT NULL,
    tax_cost TEXT,
    other_cost TEXT,
    duty_cost TEXT,
    evidence_metadata TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    variance_formula_version TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    UNIQUE (opportunity_id, baseline_kind)
)
"""


class SQLiteEstimatedEconomicsSnapshotRepository(EstimatedEconomicsSnapshotRepository):
    def __init__(
        self,
        database_path: str | Path = "data/hyb_opportunity.db",
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._owns_connection = connection is None
        if connection is None:
            resolved = str(database_path)
            if resolved != ":memory:":
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(resolved)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute(SNAPSHOT_TABLE)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_estimated_economics_opportunity "
                "ON opportunity_estimated_economics_snapshots(opportunity_id, baseline_kind)"
            )

    def create(self, snapshot: EstimatedEconomicsSnapshot) -> None:
        try:
            with self._connection:
                self._insert(snapshot)
        except sqlite3.IntegrityError as error:
            raise DuplicateEstimatedBaselineError(
                f"{snapshot.opportunity_id}:{snapshot.baseline_kind}"
            ) from error

    def get_admission_baseline(self, opportunity_id: str) -> EstimatedEconomicsSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM opportunity_estimated_economics_snapshots "
            "WHERE opportunity_id = ? AND baseline_kind = 'admission'",
            (opportunity_id,),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _insert(self, item: EstimatedEconomicsSnapshot) -> None:
        self._connection.execute(
            """INSERT INTO opportunity_estimated_economics_snapshots (
            snapshot_id, opportunity_id, baseline_kind, currency,
            purchase_price, shipping_cost, expected_sale_price,
            marketplace_fee, payment_fee, fixed_fee, expected_profit, expected_roi,
            tax_cost, other_cost, duty_cost, evidence_metadata,
            calculation_version, variance_formula_version, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.snapshot_id, item.opportunity_id, item.baseline_kind, item.currency,
                str(item.purchase_price), str(item.shipping_cost), str(item.expected_sale_price),
                str(item.marketplace_fee), str(item.payment_fee), str(item.fixed_fee),
                str(item.expected_profit), str(item.expected_roi), self._decimal_text(item.tax_cost),
                self._decimal_text(item.other_cost), self._decimal_text(item.duty_cost),
                self._evidence_json(item.evidence_metadata), item.calculation_version,
                item.variance_formula_version, item.captured_at.isoformat(),
            ),
        )

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> EstimatedEconomicsSnapshot:
        evidence_raw = json.loads(row["evidence_metadata"])
        evidence = {
            name: EconomicEvidence(
                status=EvidenceStatus(value["status"]),
                source=value["source"],
                observed_at=datetime.fromisoformat(value["observed_at"]) if value["observed_at"] else None,
                reference=value["reference"],
            )
            for name, value in evidence_raw.items()
        }
        return EstimatedEconomicsSnapshot(
            snapshot_id=row["snapshot_id"], opportunity_id=row["opportunity_id"],
            baseline_kind=row["baseline_kind"], currency=row["currency"],
            purchase_price=Decimal(row["purchase_price"]),
            shipping_cost=Decimal(row["shipping_cost"]),
            expected_sale_price=Decimal(row["expected_sale_price"]),
            marketplace_fee=Decimal(row["marketplace_fee"]),
            payment_fee=Decimal(row["payment_fee"]), fixed_fee=Decimal(row["fixed_fee"]),
            expected_profit=Decimal(row["expected_profit"]), expected_roi=Decimal(row["expected_roi"]),
            tax_cost=cls._optional_decimal(row["tax_cost"]),
            other_cost=cls._optional_decimal(row["other_cost"]),
            duty_cost=cls._optional_decimal(row["duty_cost"]),
            evidence_metadata=evidence, calculation_version=row["calculation_version"],
            variance_formula_version=row["variance_formula_version"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )

    @staticmethod
    def _evidence_json(evidence) -> str:
        return json.dumps({
            name: {
                "status": value.status.value,
                "source": value.source,
                "observed_at": value.observed_at.isoformat() if value.observed_at else None,
                "reference": value.reference,
            }
            for name, value in evidence.items()
        }, sort_keys=True)

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _optional_decimal(value: str | None) -> Decimal | None:
        return Decimal(value) if value is not None else None
