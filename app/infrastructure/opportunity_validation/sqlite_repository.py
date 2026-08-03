from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.application.opportunity_validation import (
    DuplicateValidationConflictError,
    ValidationAdmissionSnapshot,
    ValidationQueueItem,
    canonicalize_discovery_reference,
)
from app.application.opportunity_lifecycle import LifecycleVersionConflictError
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus, OpportunityLifecycleTransition
from app.domain.opportunity import EstimatedEconomicsSnapshot
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.application.opportunity_market_identity import (
    DuplicateOpportunityMarketIdentityBindingError,
    MalformedOpportunityMarketIdentityBindingError,
    OpportunityMarketIdentityBinding,
    OpportunityMarketIdentityConflictError,
)
from app.application.verified_economics_snapshot import (
    DuplicateVerifiedEconomicsSnapshotError,
    MalformedVerifiedEconomicsSnapshotError,
    VerifiedEconomicsSnapshot,
    VerifiedEconomicsSnapshotIdentityConflictError,
)
from app.application.production_safety_snapshot import (
    DuplicateProductionSafetySnapshotError,
    MalformedProductionSafetySnapshotError,
    ProductionSafetySnapshot,
    ProductionSafetySnapshotIdentityConflictError,
)
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from app.domain.opportunity import EconomicEvidence, EvidenceStatus, MoneyInput, RateInput, VerifiedEconomicsInput
from app.infrastructure.economics_variance import SQLiteEstimatedEconomicsSnapshotRepository
from app.infrastructure.opportunity_lifecycle import SQLiteOpportunityLifecycleRepository


_SNAPSHOT_TABLE = """
CREATE TABLE IF NOT EXISTS validation_queue_admission_snapshots (
    opportunity_id TEXT PRIMARY KEY,
    discovery_reference TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    title TEXT NOT NULL,
    admission_recommendation TEXT NOT NULL,
    admission_score REAL NOT NULL,
    admission_roi REAL NOT NULL,
    currency TEXT NOT NULL,
    admission_safety_status TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
)
"""

_NON_ARCHIVED_REFERENCE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_validation_discovery_reference
ON opportunity_lifecycles (discovery_reference)
WHERE archived_at IS NULL
"""

_MARKET_IDENTITY_BINDING_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_market_identity_bindings (
    opportunity_id TEXT PRIMARY KEY,
    discovery_reference TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('listing', 'canonical_product')),
    market TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    marketplace_item_id TEXT,
    canonical_product_id TEXT,
    normalized_query TEXT,
    category TEXT,
    variant_identity TEXT,
    condition TEXT,
    observed_from TEXT NOT NULL,
    observed_to TEXT NOT NULL,
    bound_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
    CHECK (
        (scope = 'listing' AND marketplace_item_id IS NOT NULL)
        OR (scope = 'canonical_product' AND canonical_product_id IS NOT NULL)
    )
)
"""

_VERIFIED_ECONOMICS_TABLE = """
CREATE TABLE IF NOT EXISTS verified_economics_snapshots (
    opportunity_id TEXT PRIMARY KEY,
    currency TEXT NOT NULL,
    purchase_cost TEXT,
    shipping_cost TEXT,
    marketplace_fee_rate TEXT,
    payment_fee_rate TEXT,
    fixed_fee TEXT,
    tax_rate TEXT,
    duty_cost TEXT,
    other_cost TEXT,
    expected_sale_price TEXT,
    evidence_metadata TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
)
"""

_PRODUCTION_SAFETY_TABLE = """
CREATE TABLE IF NOT EXISTS production_safety_snapshots (
    opportunity_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    missing_fields TEXT NOT NULL,
    failed_checks TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
)
"""


class SQLiteValidationQueueRepository:
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
            connection = sqlite3.connect(resolved, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._lifecycles = SQLiteOpportunityLifecycleRepository(connection=connection)
        self._economics = SQLiteEstimatedEconomicsSnapshotRepository(connection=connection)
        with self._connection:
            self._connection.execute(_SNAPSHOT_TABLE)
            self._connection.execute(_MARKET_IDENTITY_BINDING_TABLE)
            self._connection.execute(_VERIFIED_ECONOMICS_TABLE)
            self._connection.execute(_PRODUCTION_SAFETY_TABLE)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_opportunity_market_binding_reference "
                "ON opportunity_market_identity_bindings(discovery_reference)"
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_opportunity_market_binding_no_update
                BEFORE UPDATE ON opportunity_market_identity_bindings
                BEGIN SELECT RAISE(ABORT, 'opportunity market identity binding is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_opportunity_market_binding_no_delete
                BEFORE DELETE ON opportunity_market_identity_bindings
                BEGIN SELECT RAISE(ABORT, 'opportunity market identity binding is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_verified_economics_no_update
                BEFORE UPDATE ON verified_economics_snapshots
                BEGIN SELECT RAISE(ABORT, 'verified economics snapshot is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_verified_economics_no_delete
                BEFORE DELETE ON verified_economics_snapshots
                BEGIN SELECT RAISE(ABORT, 'verified economics snapshot is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_production_safety_no_update
                BEFORE UPDATE ON production_safety_snapshots
                BEGIN SELECT RAISE(ABORT, 'production safety snapshot is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_production_safety_no_delete
                BEFORE DELETE ON production_safety_snapshots
                BEGIN SELECT RAISE(ABORT, 'production safety snapshot is immutable'); END"""
            )
            self._migrate_canonical_references()
            self._connection.execute(_NON_ARCHIVED_REFERENCE_INDEX)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_validation_snapshot_reference "
                "ON validation_queue_admission_snapshots(discovery_reference)"
            )

    def admit(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
        except sqlite3.IntegrityError as error:
            if self._non_archived_reference_exists(snapshot.discovery_reference):
                raise DuplicateValidationConflictError(snapshot.discovery_reference) from error
            raise

    def admit_with_economics(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        if economics.opportunity_id != lifecycle.opportunity_id:
            raise ValueError("economics opportunity_id does not match lifecycle")
        if economics.currency != snapshot.currency:
            raise ValueError("economics currency does not match admission snapshot")
        if economics.baseline_kind != "admission":
            raise ValueError("validation admission requires an admission baseline")
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
                self._economics._insert(economics)
        except sqlite3.IntegrityError as error:
            if self._non_archived_reference_exists(snapshot.discovery_reference):
                raise DuplicateValidationConflictError(snapshot.discovery_reference) from error
            raise

    def admit_with_market_identity(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        binding: OpportunityMarketIdentityBinding,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        self._validate_binding(lifecycle, snapshot, binding)
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
                self._insert_market_identity_binding(binding)
        except sqlite3.IntegrityError as error:
            self._raise_admission_integrity(error, snapshot, binding)

    def admit_with_economics_and_market_identity(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
        binding: OpportunityMarketIdentityBinding,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        self._validate_binding(lifecycle, snapshot, binding)
        if economics.opportunity_id != lifecycle.opportunity_id:
            raise ValueError("economics opportunity_id does not match lifecycle")
        if economics.currency != snapshot.currency:
            raise ValueError("economics currency does not match admission snapshot")
        if economics.baseline_kind != "admission":
            raise ValueError("validation admission requires an admission baseline")
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
                self._economics._insert(economics)
                self._insert_market_identity_binding(binding)
        except sqlite3.IntegrityError as error:
            self._raise_admission_integrity(error, snapshot, binding)

    def admit_with_decision_sources(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        binding: OpportunityMarketIdentityBinding,
        verified_economics: VerifiedEconomicsSnapshot,
        production_safety: ProductionSafetySnapshot | None = None,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        self._validate_binding(lifecycle, snapshot, binding)
        self._validate_verified_economics(lifecycle, verified_economics)
        self._validate_production_safety(lifecycle, production_safety)
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
                self._insert_market_identity_binding(binding)
                self._insert_verified_economics_snapshot(verified_economics)
                if production_safety is not None:
                    self._insert_production_safety_snapshot(production_safety)
        except sqlite3.IntegrityError as error:
            self._raise_admission_integrity(
                error, snapshot, binding, verified_economics, production_safety
            )

    def admit_with_economics_and_decision_sources(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
        binding: OpportunityMarketIdentityBinding,
        verified_economics: VerifiedEconomicsSnapshot,
        production_safety: ProductionSafetySnapshot | None = None,
    ) -> None:
        self._validate_admission(lifecycle, transition, snapshot)
        self._validate_binding(lifecycle, snapshot, binding)
        self._validate_verified_economics(lifecycle, verified_economics)
        self._validate_production_safety(lifecycle, production_safety)
        if economics.opportunity_id != lifecycle.opportunity_id:
            raise ValueError("economics opportunity_id does not match lifecycle")
        if economics.currency != snapshot.currency:
            raise ValueError("economics currency does not match admission snapshot")
        if economics.baseline_kind != "admission":
            raise ValueError("validation admission requires an admission baseline")
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._insert_admission_snapshot(snapshot)
                self._economics._insert(economics)
                self._insert_market_identity_binding(binding)
                self._insert_verified_economics_snapshot(verified_economics)
                if production_safety is not None:
                    self._insert_production_safety_snapshot(production_safety)
        except sqlite3.IntegrityError as error:
            self._raise_admission_integrity(
                error, snapshot, binding, verified_economics, production_safety
            )

    def _validate_admission(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
    ) -> None:
        if snapshot.opportunity_id != lifecycle.opportunity_id:
            raise ValueError("snapshot opportunity_id does not match lifecycle")
        if snapshot.discovery_reference != lifecycle.discovery_reference:
            raise ValueError("snapshot discovery_reference does not match lifecycle")
        self._lifecycles._validate_creation(lifecycle, transition)

    def _insert_admission_snapshot(self, snapshot: ValidationAdmissionSnapshot) -> None:
        self._connection.execute(
            """INSERT INTO validation_queue_admission_snapshots (
                opportunity_id, discovery_reference, marketplace, title,
                admission_recommendation, admission_score, admission_roi,
                currency, admission_safety_status, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.opportunity_id,
                snapshot.discovery_reference,
                snapshot.marketplace,
                snapshot.title,
                snapshot.admission_recommendation,
                snapshot.admission_score,
                snapshot.admission_roi,
                snapshot.currency,
                snapshot.admission_safety_status,
                snapshot.captured_at.isoformat(),
            ),
        )

    @staticmethod
    def _validate_binding(lifecycle, snapshot, binding) -> None:
        if not isinstance(binding, OpportunityMarketIdentityBinding):
            raise TypeError("binding must be OpportunityMarketIdentityBinding")
        if binding.opportunity_id != lifecycle.opportunity_id:
            raise OpportunityMarketIdentityConflictError(
                "binding opportunity_id does not match lifecycle"
            )
        if binding.discovery_reference != lifecycle.discovery_reference:
            raise OpportunityMarketIdentityConflictError(
                "binding discovery_reference does not match lifecycle"
            )
        if binding.discovery_reference != snapshot.discovery_reference:
            raise OpportunityMarketIdentityConflictError(
                "binding discovery_reference does not match admission snapshot"
            )

    def _insert_market_identity_binding(
        self, binding: OpportunityMarketIdentityBinding
    ) -> None:
        identity = binding.market_observation_identity
        self._connection.execute(
            """INSERT INTO opportunity_market_identity_bindings (
                opportunity_id, discovery_reference, scope, market, marketplace,
                marketplace_item_id, canonical_product_id, normalized_query,
                category, variant_identity, condition, observed_from, observed_to,
                bound_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                binding.opportunity_id,
                binding.discovery_reference,
                identity.scope.value,
                identity.market,
                identity.marketplace,
                identity.marketplace_item_id,
                identity.canonical_product_id,
                identity.normalized_query,
                identity.category,
                identity.variant_identity,
                identity.condition,
                identity.window_started_at.isoformat(),
                identity.window_ended_at.isoformat(),
                binding.bound_at.isoformat(),
                binding.schema_version,
            ),
        )

    @staticmethod
    def _validate_verified_economics(lifecycle, snapshot) -> None:
        if not isinstance(snapshot, VerifiedEconomicsSnapshot):
            raise TypeError("verified_economics must be VerifiedEconomicsSnapshot")
        if snapshot.opportunity_id != lifecycle.opportunity_id:
            raise VerifiedEconomicsSnapshotIdentityConflictError(
                "verified economics opportunity_id does not match lifecycle"
            )

    def _insert_verified_economics_snapshot(
        self, snapshot: VerifiedEconomicsSnapshot
    ) -> None:
        inputs = snapshot.inputs
        self._connection.execute(
            """INSERT INTO verified_economics_snapshots (
                opportunity_id, currency, purchase_cost, shipping_cost,
                marketplace_fee_rate, payment_fee_rate, fixed_fee, tax_rate,
                duty_cost, other_cost, expected_sale_price, evidence_metadata,
                snapshot_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.opportunity_id,
                inputs.currency,
                self._decimal_text(inputs.purchase_cost.amount),
                self._decimal_text(inputs.shipping_cost.amount),
                self._decimal_text(inputs.marketplace_fee_rate.rate),
                self._decimal_text(inputs.payment_fee_rate.rate),
                self._decimal_text(inputs.fixed_fee.amount),
                self._decimal_text(inputs.tax_rate.rate),
                self._decimal_text(inputs.duty_cost.amount),
                self._decimal_text(inputs.other_cost.amount),
                self._decimal_text(inputs.expected_sale_price.amount),
                self._verified_evidence_json(inputs),
                snapshot.snapshot_at.isoformat(),
                snapshot.schema_version,
            ),
        )

    @staticmethod
    def _validate_production_safety(lifecycle, snapshot) -> None:
        if snapshot is None:
            return
        if not isinstance(snapshot, ProductionSafetySnapshot):
            raise TypeError("production_safety must be ProductionSafetySnapshot or None")
        if snapshot.opportunity_id != lifecycle.opportunity_id:
            raise ProductionSafetySnapshotIdentityConflictError(
                "production safety opportunity_id does not match lifecycle"
            )

    def _insert_production_safety_snapshot(
        self, snapshot: ProductionSafetySnapshot
    ) -> None:
        assessment = snapshot.assessment
        self._connection.execute(
            """INSERT INTO production_safety_snapshots (
                opportunity_id, status, missing_fields, failed_checks,
                snapshot_at, rule_version, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.opportunity_id,
                assessment.status.value,
                json.dumps(assessment.missing_fields),
                json.dumps(assessment.failed_checks),
                snapshot.snapshot_at.isoformat(),
                snapshot.rule_version,
                snapshot.schema_version,
            ),
        )

    @staticmethod
    def _verified_evidence_json(inputs: VerifiedEconomicsInput) -> str:
        names = (
            "purchase_cost", "shipping_cost", "marketplace_fee_rate",
            "payment_fee_rate", "fixed_fee", "tax_rate", "duty_cost",
            "other_cost", "expected_sale_price",
        )
        return json.dumps(
            {
                name: {
                    "status": getattr(inputs, name).evidence.status.value,
                    "source": getattr(inputs, name).evidence.source,
                    "observed_at": (
                        getattr(inputs, name).evidence.observed_at.isoformat()
                        if getattr(inputs, name).evidence.observed_at
                        else None
                    ),
                    "reference": getattr(inputs, name).evidence.reference,
                }
                for name in names
            },
            sort_keys=True,
        )

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    def _raise_admission_integrity(
        self,
        error,
        snapshot,
        binding,
        verified_economics=None,
        production_safety=None,
    ) -> None:
        if self._non_archived_reference_exists(snapshot.discovery_reference):
            raise DuplicateValidationConflictError(snapshot.discovery_reference) from error
        if self.get_market_identity_binding(binding.opportunity_id) is not None:
            raise DuplicateOpportunityMarketIdentityBindingError(
                binding.opportunity_id
            ) from error
        if (
            verified_economics is not None
            and self.get_verified_economics_snapshot(
                verified_economics.opportunity_id
            ) is not None
        ):
            raise DuplicateVerifiedEconomicsSnapshotError(
                verified_economics.opportunity_id
            ) from error
        if (
            production_safety is not None
            and self.get_production_safety_snapshot(
                production_safety.opportunity_id
            ) is not None
        ):
            raise DuplicateProductionSafetySnapshotError(
                production_safety.opportunity_id
            ) from error
        raise error

    def get_market_identity_binding(
        self, opportunity_id: str
    ) -> OpportunityMarketIdentityBinding | None:
        row = self._connection.execute(
            """SELECT b.*, l.discovery_reference AS lifecycle_reference
            FROM opportunity_market_identity_bindings AS b
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = b.opportunity_id
            WHERE b.opportunity_id = ?""",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        if row["discovery_reference"] != row["lifecycle_reference"]:
            raise OpportunityMarketIdentityConflictError(
                "binding discovery_reference does not match persisted lifecycle"
            )
        try:
            identity = MarketObservationIdentity(
                scope=MarketObservationScope(row["scope"]),
                market=row["market"],
                marketplace=row["marketplace"],
                canonical_product_id=row["canonical_product_id"],
                marketplace_item_id=row["marketplace_item_id"],
                normalized_query=row["normalized_query"],
                category=row["category"],
                variant_identity=row["variant_identity"],
                condition=row["condition"],
                window_started_at=datetime.fromisoformat(row["observed_from"]),
                window_ended_at=datetime.fromisoformat(row["observed_to"]),
            )
            return OpportunityMarketIdentityBinding(
                opportunity_id=row["opportunity_id"],
                discovery_reference=row["discovery_reference"],
                market_observation_identity=identity,
                bound_at=datetime.fromisoformat(row["bound_at"]),
                schema_version=row["schema_version"],
            )
        except (TypeError, ValueError) as error:
            raise MalformedOpportunityMarketIdentityBindingError(
                "persisted opportunity market identity binding is malformed"
            ) from error

    def get_verified_economics_snapshot(
        self, opportunity_id: str
    ) -> VerifiedEconomicsSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM verified_economics_snapshots WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            evidence_raw = json.loads(row["evidence_metadata"])

            def evidence(name):
                value = evidence_raw[name]
                return EconomicEvidence(
                    status=EvidenceStatus(value["status"]),
                    source=value["source"],
                    observed_at=(
                        datetime.fromisoformat(value["observed_at"])
                        if value["observed_at"]
                        else None
                    ),
                    reference=value["reference"],
                )

            def amount(name):
                value = row[name]
                return Decimal(value) if value is not None else None

            currency = row["currency"]
            inputs = VerifiedEconomicsInput(
                purchase_cost=MoneyInput(amount("purchase_cost"), currency, evidence("purchase_cost")),
                shipping_cost=MoneyInput(amount("shipping_cost"), currency, evidence("shipping_cost")),
                marketplace_fee_rate=RateInput(amount("marketplace_fee_rate"), evidence("marketplace_fee_rate")),
                payment_fee_rate=RateInput(amount("payment_fee_rate"), evidence("payment_fee_rate")),
                fixed_fee=MoneyInput(amount("fixed_fee"), currency, evidence("fixed_fee")),
                tax_rate=RateInput(amount("tax_rate"), evidence("tax_rate")),
                duty_cost=MoneyInput(amount("duty_cost"), currency, evidence("duty_cost")),
                other_cost=MoneyInput(amount("other_cost"), currency, evidence("other_cost")),
                expected_sale_price=MoneyInput(amount("expected_sale_price"), currency, evidence("expected_sale_price")),
            )
            return VerifiedEconomicsSnapshot(
                opportunity_id=row["opportunity_id"],
                inputs=inputs,
                snapshot_at=datetime.fromisoformat(row["snapshot_at"]),
                schema_version=row["schema_version"],
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            InvalidOperation,
            json.JSONDecodeError,
        ) as error:
            raise MalformedVerifiedEconomicsSnapshotError(
                "persisted verified economics snapshot is malformed"
            ) from error

    def get_production_safety_snapshot(
        self, opportunity_id: str
    ) -> ProductionSafetySnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM production_safety_snapshots WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            missing_fields = tuple(json.loads(row["missing_fields"]))
            failed_checks = tuple(json.loads(row["failed_checks"]))
            assessment = ProductionSafetyAssessment(
                status=ProductionSafetyStatus(row["status"]),
                missing_fields=missing_fields,
                failed_checks=failed_checks,
            )
            return ProductionSafetySnapshot(
                opportunity_id=row["opportunity_id"],
                assessment=assessment,
                snapshot_at=datetime.fromisoformat(row["snapshot_at"]),
                rule_version=row["rule_version"],
                schema_version=row["schema_version"],
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise MalformedProductionSafetySnapshotError(
                "persisted production safety snapshot is malformed"
            ) from error

    def list_queue(
        self,
        *,
        statuses: tuple[OpportunityLifecycleStatus, ...],
        limit: int,
    ) -> tuple[ValidationQueueItem, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        rows = self._connection.execute(
            f"""SELECT s.*, l.status, l.version, l.created_at, l.updated_at
            FROM validation_queue_admission_snapshots AS s
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = s.opportunity_id
            WHERE l.archived_at IS NULL AND l.status IN ({placeholders})
            ORDER BY l.created_at ASC, l.opportunity_id ASC
            LIMIT ?""",
            tuple(status.value for status in statuses) + (limit,),
        ).fetchall()
        return tuple(self._to_item(row) for row in rows)

    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None:
        row = self._connection.execute(
            """SELECT s.*, l.status, l.version, l.created_at, l.updated_at
            FROM validation_queue_admission_snapshots AS s
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = s.opportunity_id
            WHERE l.opportunity_id = ? AND l.archived_at IS NULL""",
            (opportunity_id,),
        ).fetchone()
        return self._to_item(row) if row is not None else None

    def create(self, lifecycle, transition) -> None:
        self._lifecycles.create(lifecycle, transition)

    def get(self, opportunity_id: str):
        return self._lifecycles.get(opportunity_id)

    def save_transition(self, lifecycle, transition, *, expected_version: int) -> None:
        if (
            not lifecycle.is_archived
            and self._non_archived_reference_exists(
                lifecycle.discovery_reference,
                excluding_opportunity_id=lifecycle.opportunity_id,
            )
        ):
            raise DuplicateValidationConflictError(lifecycle.discovery_reference)
        try:
            self._lifecycles.save_transition(
                lifecycle,
                transition,
                expected_version=expected_version,
            )
        except LifecycleVersionConflictError as error:
            if (
                not lifecycle.is_archived
                and self._non_archived_reference_exists(
                    lifecycle.discovery_reference,
                    excluding_opportunity_id=lifecycle.opportunity_id,
                )
            ):
                raise DuplicateValidationConflictError(lifecycle.discovery_reference) from error
            raise

    def list_transitions(self, opportunity_id: str):
        return self._lifecycles.list_transitions(opportunity_id)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _non_archived_reference_exists(
        self,
        discovery_reference: str,
        *,
        excluding_opportunity_id: str | None = None,
    ) -> bool:
        parameters: list[str] = [canonicalize_discovery_reference(discovery_reference)]
        exclusion = ""
        if excluding_opportunity_id is not None:
            exclusion = " AND opportunity_id <> ?"
            parameters.append(excluding_opportunity_id)
        row = self._connection.execute(
            """SELECT 1 FROM opportunity_lifecycles
            WHERE discovery_reference = ? AND archived_at IS NULL"""
            + exclusion
            + " LIMIT 1",
            tuple(parameters),
        ).fetchone()
        return row is not None

    def _migrate_canonical_references(self) -> None:
        self._connection.execute("DROP INDEX IF EXISTS uq_active_validation_discovery_reference")
        rows = self._connection.execute(
            "SELECT opportunity_id, discovery_reference FROM opportunity_lifecycles"
        ).fetchall()
        for row in rows:
            canonical = canonicalize_discovery_reference(row["discovery_reference"])
            self._connection.execute(
                "UPDATE opportunity_lifecycles SET discovery_reference = ? WHERE opportunity_id = ?",
                (canonical, row["opportunity_id"]),
            )
            self._connection.execute(
                "UPDATE validation_queue_admission_snapshots SET discovery_reference = ? "
                "WHERE opportunity_id = ?",
                (canonical, row["opportunity_id"]),
            )

    @staticmethod
    def _to_item(row: sqlite3.Row) -> ValidationQueueItem:
        return ValidationQueueItem(
            opportunity_id=row["opportunity_id"],
            discovery_reference=row["discovery_reference"],
            marketplace=row["marketplace"],
            title=row["title"],
            recommendation=row["admission_recommendation"],
            score=float(row["admission_score"]),
            roi=float(row["admission_roi"]),
            currency=row["currency"],
            safety_status=row["admission_safety_status"],
            lifecycle_status=OpportunityLifecycleStatus(row["status"]),
            lifecycle_version=int(row["version"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
