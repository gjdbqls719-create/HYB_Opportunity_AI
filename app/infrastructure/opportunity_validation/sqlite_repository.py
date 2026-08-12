from __future__ import annotations

import sqlite3
import json
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.application.opportunity_validation import (
    DuplicateValidationConflictError,
    ValidationAdmissionSnapshot,
    ValidationQueueItem,
    FounderSelectedAdmissionBasis,
    ValidationQueueItemV2,
    canonicalize_discovery_reference,
)
from app.application.opportunity_lifecycle import LifecycleVersionConflictError
from app.application.operational_opportunity_eligibility import (
    OperationalOpportunityBindingUnavailableError,
)
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus, OpportunityLifecycleTransition
from app.domain.opportunity import (
    NewToMarketDomesticSellingTargetIdentity,
    NewToMarketDomesticSellingTargetKind,
    OpportunityDomesticSellingTargetBinding,
)
from app.domain.opportunity import EstimatedEconomicsSnapshot
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionEvidenceMetadata,
    DecisionFreshness,
    OpportunityIdentity,
)
from app.application.decision_composition import (
    DecisionCompositionSnapshot,
    COMPOSITION_SCHEMA_VERSION,
    METADATA_POLICY_VERSION,
    DecisionCompositionCommitError,
    DecisionCompositionIdentityConflictError,
    DecisionCompositionPersistenceError,
    DecisionCompositionProjectionError,
    DecisionCompositionProvenanceError,
    DecisionCompositionVersionConflictError,
    DuplicateDecisionCompositionError,
    MalformedDecisionCompositionError,
    MissingDecisionCompositionSourceError,
    UnsupportedDecisionCompositionVersionError,
)
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
from app.application.verified_economics_admission import (
    VerifiedEconomicsAdmissionConflictError,
    VerifiedEconomicsAdmissionPersistenceError,
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

_DECISION_COMPOSITION_HISTORY = """
CREATE TABLE IF NOT EXISTS decision_composition_history (
    composition_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    composition_version INTEGER NOT NULL,
    provenance_fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (opportunity_id, composition_version),
    UNIQUE (opportunity_id, provenance_fingerprint)
)
"""

_DECISION_COMPOSITION_CURRENT = """
CREATE TABLE IF NOT EXISTS decision_composition_current (
    opportunity_id TEXT PRIMARY KEY,
    composition_id TEXT NOT NULL,
    composition_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL
)
"""
_VERIFIED_ECONOMICS_RECEIPTS = """
CREATE TABLE IF NOT EXISTS verified_economics_admission_receipts (
 command_id TEXT PRIMARY KEY, command_fingerprint TEXT NOT NULL,
 opportunity_id TEXT NOT NULL UNIQUE, operator_id TEXT NOT NULL,
 snapshot_at TEXT NOT NULL, schema_version TEXT NOT NULL,
 FOREIGN KEY(opportunity_id) REFERENCES verified_economics_snapshots(opportunity_id))
"""
_OPPORTUNITY_REVIEW_BINDING_CURRENT = """
CREATE TABLE IF NOT EXISTS opportunity_review_binding_current (
 session_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, binding_id TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL, projected_at TEXT NOT NULL)
"""
_CANDIDATE_PROMOTION_HISTORY = """
CREATE TABLE IF NOT EXISTS opportunity_candidate_promotion_history (
 binding_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE,
 opportunity_id TEXT NOT NULL UNIQUE, discovery_reference TEXT NOT NULL,
 market_identity_payload_json TEXT NOT NULL, discovery_command_id TEXT NOT NULL,
 discovery_execution_id TEXT NOT NULL, finalized_group_id TEXT NOT NULL,
 initial_promotion_command_id TEXT NOT NULL UNIQUE, subject_fingerprint TEXT NOT NULL,
 promoted_at TEXT NOT NULL, schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id),
 FOREIGN KEY(opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id))
"""
_CANDIDATE_PROMOTION_RECEIPTS = """
CREATE TABLE IF NOT EXISTS opportunity_candidate_promotion_receipts (
 promotion_command_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
 opportunity_id TEXT NOT NULL, command_fingerprint TEXT NOT NULL,
 subject_fingerprint TEXT NOT NULL, committed_at TEXT NOT NULL,
 schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_promotion_history(candidate_id),
 FOREIGN KEY(opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id))
"""
_CANDIDATE_PROMOTION_V2_SOURCE_HISTORY = """
CREATE TABLE IF NOT EXISTS opportunity_candidate_promotion_v2_source_history (
 binding_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
 finalized_group_id TEXT NOT NULL, capture_command_id TEXT NOT NULL,
 ordered_product_snapshot_ids_json TEXT NOT NULL,
 representative_product_snapshot_id TEXT NOT NULL,
 schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(binding_id) REFERENCES opportunity_candidate_promotion_history(binding_id))
"""
_CANDIDATE_PROMOTION_V2_ADMISSION_HISTORY = """
CREATE TABLE IF NOT EXISTS candidate_promotion_v2_admission_history (
 admission_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL UNIQUE,
 candidate_id TEXT NOT NULL, binding_id TEXT NOT NULL UNIQUE,
 discovery_command_id TEXT NOT NULL, discovery_execution_id TEXT NOT NULL,
 finalized_group_id TEXT NOT NULL, capture_command_id TEXT NOT NULL,
 ordered_product_snapshot_ids_json TEXT NOT NULL,
 representative_product_snapshot_id TEXT NOT NULL,
 operator_id TEXT NOT NULL, reason TEXT NOT NULL, note TEXT,
 requested_at TEXT NOT NULL, promoted_at TEXT NOT NULL, committed_at TEXT NOT NULL,
 admission_kind TEXT NOT NULL, policy_name TEXT NOT NULL,
 policy_version TEXT NOT NULL, schema_version TEXT NOT NULL,
 command_fingerprint TEXT NOT NULL, subject_fingerprint TEXT NOT NULL,
 inserted_at TEXT NOT NULL,
 FOREIGN KEY(binding_id) REFERENCES opportunity_candidate_promotion_history(binding_id),
 FOREIGN KEY(opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id))
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
            self._connection.execute(_VERIFIED_ECONOMICS_RECEIPTS)
            self._connection.execute(_PRODUCTION_SAFETY_TABLE)
            self._connection.execute(_DECISION_COMPOSITION_HISTORY)
            self._connection.execute(_DECISION_COMPOSITION_CURRENT)
            self._connection.execute(_OPPORTUNITY_REVIEW_BINDING_CURRENT)
            self._connection.execute(_CANDIDATE_PROMOTION_HISTORY)
            self._connection.execute(_CANDIDATE_PROMOTION_RECEIPTS)
            self._connection.execute(_CANDIDATE_PROMOTION_V2_SOURCE_HISTORY)
            self._connection.execute(_CANDIDATE_PROMOTION_V2_ADMISSION_HISTORY)
            for table in (
                "opportunity_candidate_promotion_history",
                "opportunity_candidate_promotion_receipts",
                "opportunity_candidate_promotion_v2_source_history",
                "candidate_promotion_v2_admission_history",
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END""")
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
            for operation in ("UPDATE","DELETE"):
                self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_verified_economics_receipts_no_{operation.lower()}
                BEFORE {operation} ON verified_economics_admission_receipts
                BEGIN SELECT RAISE(ABORT, 'verified economics admission receipt is immutable'); END""")
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
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_decision_composition_no_update
                BEFORE UPDATE ON decision_composition_history
                BEGIN SELECT RAISE(ABORT, 'decision composition history is immutable'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_decision_composition_no_delete
                BEFORE DELETE ON decision_composition_history
                BEGIN SELECT RAISE(ABORT, 'decision composition history is immutable'); END"""
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

    def get_target_binding(
        self, opportunity_id: str
    ) -> OpportunityDomesticSellingTargetBinding | None:
        table_names = {
            row["name"]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
                (
                    "opportunity_domestic_selling_target_bindings",
                    "new_to_market_domestic_selling_target_history",
                ),
            ).fetchall()
        }
        if not table_names:
            return None
        if table_names != {
            "opportunity_domestic_selling_target_bindings",
            "new_to_market_domestic_selling_target_history",
        }:
            raise OperationalOpportunityBindingUnavailableError(
                "target binding persistence is incomplete"
            )
        row = self._connection.execute(
            """SELECT b.*, l.discovery_reference AS lifecycle_reference,
            t.domestic_selling_target_id AS persisted_target_id,
            t.market AS target_market, t.kind AS target_kind,
            t.schema_version AS target_schema_version
            FROM opportunity_domestic_selling_target_bindings AS b
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = b.opportunity_id
            LEFT JOIN new_to_market_domestic_selling_target_history AS t
              ON t.domestic_selling_target_id = b.domestic_selling_target_id
            WHERE b.opportunity_id = ?""",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["discovery_reference"] != row["lifecycle_reference"]:
                raise ValueError("target binding discovery reference differs from lifecycle")
            if row["persisted_target_id"] is None:
                raise ValueError("target binding references missing target identity")
            target = NewToMarketDomesticSellingTargetIdentity(
                domestic_selling_target_id=row["persisted_target_id"],
                market=row["target_market"],
                kind=NewToMarketDomesticSellingTargetKind(row["target_kind"]),
                schema_version=row["target_schema_version"],
            )
            return OpportunityDomesticSellingTargetBinding(
                opportunity_id=row["opportunity_id"],
                discovery_reference=row["discovery_reference"],
                target_identity=target,
                bound_at=datetime.fromisoformat(row["bound_at"]),
                schema_version=row["schema_version"],
            )
        except Exception as error:
            raise OperationalOpportunityBindingUnavailableError(
                "target binding persistence is malformed"
            ) from error

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

    def get_bound_review_external_signal_ids(self, opportunity_id: str) -> tuple[str, ...] | None:
        count = self._connection.execute(
            "SELECT COUNT(*) FROM opportunity_review_binding_current WHERE opportunity_id = ?", (opportunity_id,)
        ).fetchone()[0]
        if count == 0:
            return None
        rows = self._connection.execute(
            """SELECT receipts.payload_json FROM opportunity_review_binding_current AS bindings
            JOIN review_command_receipts AS receipts ON receipts.session_id = bindings.session_id
            WHERE bindings.opportunity_id = ? ORDER BY receipts.inserted_at, receipts.command_id""",
            (opportunity_id,),
        ).fetchall()
        return tuple(
            signal_id for row in rows
            if (signal_id := json.loads(row["payload_json"]).get("external_signal_id")) is not None
        )

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

    def get_verified_economics_admission_receipt(self, command_id: str):
        try:
            row = self._connection.execute(
                """SELECT command_fingerprint, opportunity_id, operator_id,
                snapshot_at, schema_version FROM verified_economics_admission_receipts
                WHERE command_id = ?""",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise VerifiedEconomicsAdmissionPersistenceError(
                "verified economics receipt is unavailable"
            ) from error
        if row is None:
            return None
        if row["schema_version"] != "verified-economics-admission-receipt-v1":
            raise VerifiedEconomicsAdmissionPersistenceError(
                "unsupported verified economics receipt version"
            )
        return {"fingerprint": row["command_fingerprint"], "opportunity_id": row["opportunity_id"],
                "operator_id": row["operator_id"], "snapshot_at": row["snapshot_at"]}

    def finalize_verified_economics_admission(self, snapshot, command_id, fingerprint, operator_id):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._insert_verified_economics_snapshot(snapshot)
            self._connection.execute("INSERT INTO verified_economics_admission_receipts (command_id,command_fingerprint,opportunity_id,operator_id,snapshot_at,schema_version) VALUES (?,?,?,?,?,?)",(command_id,fingerprint,snapshot.opportunity_id,operator_id,snapshot.snapshot_at.isoformat(),"verified-economics-admission-receipt-v1"))
            self._connection.commit()
            return snapshot
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            receipt=self.get_verified_economics_admission_receipt(command_id)
            if receipt is not None and receipt["fingerprint"]==fingerprint:
                existing=self.get_verified_economics_snapshot(snapshot.opportunity_id)
                if existing is not None:
                    return existing
            if receipt is not None:
                raise VerifiedEconomicsAdmissionConflictError("verified economics command conflict") from error
            if self.get_verified_economics_snapshot(snapshot.opportunity_id) is not None:
                raise VerifiedEconomicsAdmissionConflictError("verified economics snapshot already exists") from error
            raise VerifiedEconomicsAdmissionPersistenceError("verified economics admission failed") from error
        except Exception as error:
            self._connection.rollback()
            raise VerifiedEconomicsAdmissionPersistenceError(
                "verified economics admission transaction failed"
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

    def finalize_decision_composition(self, snapshot):
        if not isinstance(snapshot, DecisionCompositionSnapshot):
            raise TypeError("snapshot must be DecisionCompositionSnapshot")
        if snapshot.composition_schema_version != COMPOSITION_SCHEMA_VERSION:
            raise UnsupportedDecisionCompositionVersionError(
                "unsupported decision composition schema version"
            )
        if snapshot.metadata_policy_version != METADATA_POLICY_VERSION:
            raise UnsupportedDecisionCompositionVersionError(
                "unsupported decision composition metadata policy version"
            )
        payload = self._composition_payload(snapshot)
        fingerprint_data = {
            "market_identity": self._composition_identity(snapshot.market_observation_identity),
            "verified": snapshot.verified_economics_snapshot_id,
            "safety": snapshot.production_safety_snapshot_id,
            "competition": snapshot.competition_assessment_snapshot_id,
            "demand": snapshot.demand_assessment_snapshot_id,
            "external": snapshot.external_signal_ids,
            "metadata": json.loads(payload)["evidence_metadata"],
            "schema_version": snapshot.schema_version,
            "policy_version": snapshot.policy_version,
            "composition_schema_version": snapshot.composition_schema_version,
            "metadata_policy_version": snapshot.metadata_policy_version,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            latest = self._connection.execute(
                "SELECT composition_version FROM decision_composition_current WHERE opportunity_id=?",
                (snapshot.opportunity_identity.opportunity_id,),
            ).fetchone()
            expected = 1 if latest is None else latest["composition_version"] + 1
            if snapshot.composition_version != expected:
                raise DecisionCompositionVersionConflictError(
                    f"expected composition version {expected}"
                )
            if self._connection.execute(
                "SELECT 1 FROM decision_composition_history "
                "WHERE opportunity_id=? AND provenance_fingerprint=?",
                (snapshot.opportunity_identity.opportunity_id, fingerprint),
            ).fetchone() is not None:
                raise DuplicateDecisionCompositionError(
                    "identical decision composition provenance already finalized"
                )
            self._validate_composition_sources(snapshot)
            try:
                self._connection.execute(
                    """INSERT INTO decision_composition_history
                    (composition_id, opportunity_id, composition_version, provenance_fingerprint, payload_json)
                    VALUES (?, ?, ?, ?, ?)""",
                    (snapshot.composition_id, snapshot.opportunity_identity.opportunity_id,
                     snapshot.composition_version, fingerprint, payload),
                )
            except sqlite3.Error as error:
                raise DecisionCompositionPersistenceError(
                    "decision composition history insert failed"
                ) from error
            try:
                self._connection.execute(
                    """INSERT INTO decision_composition_current
                    (opportunity_id, composition_id, composition_version, payload_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(opportunity_id) DO UPDATE SET
                        composition_id=excluded.composition_id,
                        composition_version=excluded.composition_version,
                        payload_json=excluded.payload_json
                    WHERE excluded.composition_version > decision_composition_current.composition_version""",
                    (snapshot.opportunity_identity.opportunity_id, snapshot.composition_id,
                     snapshot.composition_version, payload),
                )
            except sqlite3.Error as error:
                raise DecisionCompositionProjectionError(
                    "decision composition current projection failed"
                ) from error
            try:
                self._connection.commit()
            except sqlite3.Error as error:
                raise DecisionCompositionCommitError(
                    "decision composition commit failed"
                ) from error
            return snapshot
        except (DecisionCompositionVersionConflictError, DuplicateDecisionCompositionError):
            self._connection.rollback()
            raise
        except Exception:
            self._connection.rollback()
            raise

    def _validate_composition_sources(self, snapshot):
        opportunity_id = snapshot.opportunity_identity.opportunity_id
        item = self.get_queue_item(opportunity_id)
        if item is None or item.discovery_reference != snapshot.opportunity_identity.discovery_reference:
            raise DecisionCompositionIdentityConflictError("opportunity identity mismatch")
        binding = self.get_market_identity_binding(opportunity_id)
        if binding is None or binding.market_observation_identity != snapshot.market_observation_identity:
            raise DecisionCompositionIdentityConflictError("market identity mismatch")
        economics = self.get_verified_economics_snapshot(
            snapshot.verified_economics_snapshot_id
        )
        if economics is None or economics.opportunity_id != opportunity_id:
            raise MissingDecisionCompositionSourceError("verified economics provenance missing")
        safety = self.get_production_safety_snapshot(
            snapshot.production_safety_snapshot_id
        )
        if safety is None:
            tables = self._connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='production_safety_evaluation_current'"
            ).fetchone()[0]
            if not tables:
                raise MissingDecisionCompositionSourceError("production safety provenance missing")
            row = self._connection.execute(
                """SELECT c.evaluation_id AS current_id,c.evaluation_version AS current_version,
                h.opportunity_id,h.evaluation_version,h.rule_version,h.evaluation_schema_version,
                p.opportunity_id AS provenance_opportunity,p.rule_version AS provenance_rule,
                p.provenance_schema_version
                FROM production_safety_evaluation_current c
                JOIN production_safety_evaluation_history h ON h.evaluation_id=c.evaluation_id
                JOIN production_safety_evaluation_provenance p ON p.evaluation_id=c.evaluation_id
                WHERE c.opportunity_id=?""",
                (opportunity_id,),
            ).fetchone()
            if row is None:
                raise MissingDecisionCompositionSourceError("operational production safety current missing")
            if row["current_id"] != snapshot.production_safety_snapshot_id:
                raise DecisionCompositionVersionConflictError("operational production safety source is stale")
            if (
                row["opportunity_id"] != opportunity_id
                or row["provenance_opportunity"] != opportunity_id
                or row["current_version"] != row["evaluation_version"]
            ):
                raise DecisionCompositionIdentityConflictError("operational production safety identity mismatch")
            if (
                row["rule_version"] != "production-safety-v1"
                or row["provenance_rule"] != row["rule_version"]
                or row["evaluation_schema_version"] != "production-safety-evaluation-v1"
                or row["provenance_schema_version"] != "production-safety-provenance-v1"
            ):
                raise UnsupportedDecisionCompositionVersionError("unsupported operational production safety source")
        elif safety.opportunity_id != opportunity_id:
            raise MissingDecisionCompositionSourceError("production safety provenance missing")
        for snapshot_id, assessment_type in (
            (snapshot.competition_assessment_snapshot_id, "competition"),
            (snapshot.demand_assessment_snapshot_id, "demand"),
        ):
            row = self._connection.execute(
                "SELECT payload_json FROM market_assessment_snapshot_history "
                "WHERE snapshot_id=? AND assessment_type=?",
                (snapshot_id, assessment_type),
            ).fetchone()
            if row is None:
                raise MissingDecisionCompositionSourceError(
                    f"{assessment_type} assessment provenance missing"
                )
            if json.loads(row["payload_json"])["identity"] != self._composition_identity(
                snapshot.market_observation_identity
            ):
                raise DecisionCompositionIdentityConflictError(
                    f"{assessment_type} assessment identity mismatch"
                )
        for signal_id in snapshot.external_signal_ids:
            row = self._connection.execute(
                "SELECT payload_json FROM market_observation_history "
                "WHERE observation_id=? AND observation_type='external_signal'",
                (signal_id,),
            ).fetchone()
            if row is None or json.loads(row["payload_json"])["evidence"]["status"] != "human_verified":
                raise MissingDecisionCompositionSourceError(
                    "external signal provenance missing or not human verified"
                )
            if json.loads(row["payload_json"])["identity"] != self._composition_identity(
                snapshot.market_observation_identity
            ):
                raise DecisionCompositionIdentityConflictError(
                    "external signal identity mismatch"
                )

    def get_latest_decision_composition(self, opportunity_id):
        row = self._connection.execute(
            "SELECT payload_json FROM decision_composition_current WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        return self._safe_composition_from_payload(row["payload_json"]) if row else None

    def get_decision_composition(self, composition_id):
        row = self._connection.execute(
            "SELECT payload_json FROM decision_composition_history WHERE composition_id=?",
            (composition_id,),
        ).fetchone()
        return self._safe_composition_from_payload(row["payload_json"]) if row else None

    def get_decision_composition_history(self, opportunity_id):
        rows = self._connection.execute(
            "SELECT payload_json FROM decision_composition_history WHERE opportunity_id=? "
            "ORDER BY composition_version DESC",
            (opportunity_id,),
        ).fetchall()
        return tuple(self._safe_composition_from_payload(row["payload_json"]) for row in rows)

    @classmethod
    def _safe_composition_from_payload(cls, payload):
        try:
            value = cls._composition_from_payload(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise MalformedDecisionCompositionError(
                "persisted decision composition is malformed"
            ) from error
        if value.composition_schema_version != COMPOSITION_SCHEMA_VERSION:
            raise UnsupportedDecisionCompositionVersionError(
                "unsupported decision composition schema version"
            )
        if value.metadata_policy_version != METADATA_POLICY_VERSION:
            raise UnsupportedDecisionCompositionVersionError(
                "unsupported decision composition metadata policy version"
            )
        return value

    @staticmethod
    def _composition_identity(identity):
        return {
            "scope": identity.scope.value, "market": identity.market,
            "marketplace": identity.marketplace,
            "canonical_product_id": identity.canonical_product_id,
            "marketplace_item_id": identity.marketplace_item_id,
            "normalized_query": identity.normalized_query, "category": identity.category,
            "variant_identity": identity.variant_identity, "condition": identity.condition,
            "window_started_at": identity.window_started_at.isoformat(),
            "window_ended_at": identity.window_ended_at.isoformat(),
        }

    @classmethod
    def _composition_payload(cls, value):
        return json.dumps({
            "composition_id": value.composition_id,
            "composition_version": value.composition_version,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "market_observation_identity": cls._composition_identity(value.market_observation_identity),
            "verified_economics_snapshot_id": value.verified_economics_snapshot_id,
            "production_safety_snapshot_id": value.production_safety_snapshot_id,
            "competition_assessment_snapshot_id": value.competition_assessment_snapshot_id,
            "demand_assessment_snapshot_id": value.demand_assessment_snapshot_id,
            "external_signal_ids": list(value.external_signal_ids),
            "evidence_metadata": [
                {"dimension": item.dimension.value, "availability": item.availability.value,
                 "confidence": str(item.confidence) if item.confidence is not None else None,
                 "freshness": item.freshness.value}
                for item in value.evidence_metadata
            ],
            "generated_at": value.generated_at.isoformat(),
            "schema_version": value.schema_version,
            "policy_version": value.policy_version,
            "composition_schema_version": value.composition_schema_version,
            "metadata_policy_version": value.metadata_policy_version,
        }, sort_keys=True)

    @classmethod
    def _composition_from_payload(cls, payload):
        data = json.loads(payload)
        identity = data["market_observation_identity"]
        return DecisionCompositionSnapshot(
            composition_id=data["composition_id"], composition_version=data["composition_version"],
            opportunity_identity=OpportunityIdentity(**data["opportunity_identity"]),
            market_observation_identity=MarketObservationIdentity(
                scope=MarketObservationScope(identity["scope"]), market=identity["market"],
                marketplace=identity["marketplace"], canonical_product_id=identity["canonical_product_id"],
                marketplace_item_id=identity["marketplace_item_id"], normalized_query=identity["normalized_query"],
                category=identity["category"], variant_identity=identity["variant_identity"],
                condition=identity["condition"], window_started_at=datetime.fromisoformat(identity["window_started_at"]),
                window_ended_at=datetime.fromisoformat(identity["window_ended_at"])),
            verified_economics_snapshot_id=data["verified_economics_snapshot_id"],
            production_safety_snapshot_id=data["production_safety_snapshot_id"],
            competition_assessment_snapshot_id=data["competition_assessment_snapshot_id"],
            demand_assessment_snapshot_id=data["demand_assessment_snapshot_id"],
            external_signal_ids=tuple(data["external_signal_ids"]),
            evidence_metadata=tuple(DecisionEvidenceMetadata(
                DecisionDimension(item["dimension"]), DecisionEvidenceAvailability(item["availability"]),
                Decimal(item["confidence"]) if item["confidence"] is not None else None,
                DecisionFreshness(item["freshness"])) for item in data["evidence_metadata"]),
            generated_at=datetime.fromisoformat(data["generated_at"]),
            schema_version=data["schema_version"], policy_version=data["policy_version"],
            composition_schema_version=data["composition_schema_version"],
            metadata_policy_version=data["metadata_policy_version"])

    def list_queue(
        self,
        *,
        statuses: tuple[OpportunityLifecycleStatus, ...],
        limit: int,
    ) -> tuple[ValidationQueueItem | ValidationQueueItemV2, ...]:
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
        v1 = [self._to_item(row) for row in rows]
        if not self._table_exists("product_observation_snapshot_history"):
            return tuple(v1[:limit])
        v2_rows = self._connection.execute(
            f"""SELECT a.*, l.discovery_reference, l.status, l.version,
            l.created_at, l.updated_at, p.observed_product_payload_json
            FROM candidate_promotion_v2_admission_history AS a
            JOIN opportunity_lifecycles AS l ON l.opportunity_id=a.opportunity_id
            JOIN product_observation_snapshot_history AS p
              ON p.snapshot_id=a.representative_product_snapshot_id
            WHERE l.archived_at IS NULL AND l.status IN ({placeholders})""",
            tuple(status.value for status in statuses),
        ).fetchall()
        combined = v1 + [self._to_v2_item(row) for row in v2_rows]
        combined.sort(key=lambda value: (value.created_at, value.opportunity_id))
        return tuple(combined[:limit])

    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None:
        row = self._connection.execute(
            """SELECT s.*, l.status, l.version, l.created_at, l.updated_at
            FROM validation_queue_admission_snapshots AS s
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = s.opportunity_id
            WHERE l.opportunity_id = ? AND l.archived_at IS NULL""",
            (opportunity_id,),
        ).fetchone()
        if row is not None:
            return self._to_item(row)
        if not self._table_exists("product_observation_snapshot_history"):
            return None
        v2 = self._connection.execute(
            """SELECT a.*, l.discovery_reference, l.status, l.version,
            l.created_at, l.updated_at, p.observed_product_payload_json
            FROM candidate_promotion_v2_admission_history AS a
            JOIN opportunity_lifecycles AS l ON l.opportunity_id=a.opportunity_id
            JOIN product_observation_snapshot_history AS p
              ON p.snapshot_id=a.representative_product_snapshot_id
            WHERE l.opportunity_id=? AND l.archived_at IS NULL""",
            (opportunity_id,),
        ).fetchone()
        return self._to_v2_item(v2) if v2 is not None else None

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

    def _table_exists(self, table_name: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone() is not None

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

    @staticmethod
    def _to_v2_item(row: sqlite3.Row) -> ValidationQueueItemV2:
        try:
            product = json.loads(row["observed_product_payload_json"])
            ids = json.loads(row["ordered_product_snapshot_ids_json"])
            if not isinstance(ids, list):
                raise ValueError("ordered Product Snapshot IDs must be a list")
            basis = FounderSelectedAdmissionBasis(
                admission_id=row["admission_id"], candidate_id=row["candidate_id"],
                candidate_opportunity_binding_id=row["binding_id"],
                discovery_command_id=row["discovery_command_id"],
                discovery_execution_id=row["discovery_execution_id"],
                finalized_group_id=row["finalized_group_id"],
                product_snapshot_capture_command_id=row["capture_command_id"],
                product_snapshot_ids=tuple(ids),
                representative_product_snapshot_id=row["representative_product_snapshot_id"],
                operator_id=row["operator_id"], reason=row["reason"],
                requested_at=datetime.fromisoformat(row["requested_at"]),
                promoted_at=datetime.fromisoformat(row["promoted_at"]),
                committed_at=datetime.fromisoformat(row["committed_at"]),
                admission_kind=row["admission_kind"], policy_name=row["policy_name"],
                policy_version=row["policy_version"], schema_version=row["schema_version"],
            )
            return ValidationQueueItemV2(
                opportunity_id=row["opportunity_id"],
                discovery_reference=row["discovery_reference"],
                marketplace=product["marketplace"], title=product["title"],
                currency=product["currency"], admission_basis=basis,
                lifecycle_status=OpportunityLifecycleStatus(row["status"]),
                lifecycle_version=int(row["version"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        except Exception as error:
            raise ValueError("malformed Candidate Promotion v2 admission") from error
