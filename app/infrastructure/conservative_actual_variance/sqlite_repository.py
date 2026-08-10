"""Append-only SQLite persistence for Conservative-to-Actual variance v2."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.conservative_actual_variance import (
    CONSERVATIVE_ACTUAL_VARIANCE_RECEIPT_SCHEMA_VERSION,
    CalculateConservativeActualVarianceCommand,
    ConservativeActualVariancePublication,
    ConservativeActualVarianceReceipt,
    ConservativeActualVarianceReplayConflictError,
    ConservativeActualVarianceSourceConflictError,
    _canonical,
    _snapshot,
    conservative_actual_variance_scope_fingerprint,
)
from app.domain.capital import ActualOutcomeInventoryResolution, ActualOutcomeSaleWindow, OwnedInventoryProductKey
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity.conservative_actual_variance import (
    CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
    CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
    CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION,
    CONSERVATIVE_ACTUAL_VARIANCE_SOURCE_MANIFEST_SCHEMA_VERSION,
    ConservativeActualExposureContext,
    ConservativeActualPredictedContext,
    ConservativeActualScenarioContext,
    ConservativeActualScopeContext,
    ConservativeActualVariance,
    ConservativeActualVarianceContributor,
    ConservativeActualVarianceMetric,
    ConservativeActualVarianceSourceManifest,
    VarianceCalibrationEligibility,
    VarianceCalibrationReason,
    VarianceComparisonState,
    VarianceFavorability,
    VarianceMetricComparability,
    VarianceMetricDirection,
)
from app.infrastructure.actual_outcome import SQLiteActualOutcomeRepository
from app.infrastructure.capital_requirement import SQLitePlannedAcquisitionCapitalRequirementRepository
from app.infrastructure.conservative_economics import SQLiteConservativeEconomicsRepository
from app.infrastructure.economics_source_composition import SQLiteEconomicsSourceCompositionRepository
from app.infrastructure.sourcing import (
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteLandedCostCompositionRepository,
    SQLiteSourcingAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
)


HISTORY_TABLE = "conservative_actual_variance_history"
RECEIPT_TABLE = "conservative_actual_variance_receipts"


class ConservativeActualVariancePersistenceError(RuntimeError): pass
class ConservativeActualVarianceHistoryError(ConservativeActualVariancePersistenceError): pass
class ConservativeActualVarianceReceiptError(ConservativeActualVariancePersistenceError): pass
class ConservativeActualVarianceCommitError(ConservativeActualVariancePersistenceError): pass
class MalformedConservativeActualVariancePersistenceError(ConservativeActualVariancePersistenceError): pass
class UnsupportedConservativeActualVarianceVersionError(MalformedConservativeActualVariancePersistenceError): pass


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be Decimal text")
    return Decimal(value)


def _optional_decimal(value: object, name: str) -> Decimal | None:
    return None if value is None else _decimal(value, name)


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has unsupported fields")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be list")
    return value


def _load_identity(value: object) -> OpportunityIdentity:
    data = _exact(value, {"opportunity_id", "discovery_reference"}, "Opportunity identity")
    return OpportunityIdentity(data["opportunity_id"], data["discovery_reference"])


_KEY_FIELDS = {
    "opportunity_identity", "source_platform", "supplier_id", "sourcing_product_id",
    "external_product_reference", "option_reference", "sku_reference", "quantity_unit",
}


def _load_key(value: object) -> OwnedInventoryProductKey:
    data = _exact(value, _KEY_FIELDS, "product key")
    return OwnedInventoryProductKey(
        _load_identity(data["opportunity_identity"]),
        data["source_platform"], data["supplier_id"], data["sourcing_product_id"],
        data["external_product_reference"], data["option_reference"],
        data["sku_reference"], data["quantity_unit"],
    )


_MANIFEST_FIELDS = {
    "opportunity_identity", "product_key", "conservative_result_id",
    "source_composition_id", "acquisition_normalization_id",
    "landed_cost_composition_id", "sourcing_binding_id", "sourcing_admission_id",
    "sourcing_admission_revision", "quote_id", "quote_revision", "actual_outcome_id",
    "purchase_execution_record_id", "actual_acquisition_settlement_id",
    "actual_sale_settlement_ids", "currency", "conservative_policy_name",
    "conservative_policy_version", "conservative_schema_version", "actual_policy_name",
    "actual_policy_version", "actual_schema_version", "conservative_calculated_at",
    "purchase_executed_at", "conservative_source_snapshot", "actual_source_snapshot",
    "conservative_source_fingerprint", "actual_source_fingerprint",
    "source_pair_fingerprint", "schema_version",
}


def _load_manifest(value: object) -> ConservativeActualVarianceSourceManifest:
    data = _exact(value, _MANIFEST_FIELDS, "Variance v2 source manifest")
    if data["schema_version"] != CONSERVATIVE_ACTUAL_VARIANCE_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedConservativeActualVarianceVersionError(
            "unsupported Variance v2 source manifest version"
        )
    return ConservativeActualVarianceSourceManifest(
        opportunity_identity=_load_identity(data["opportunity_identity"]),
        product_key=_load_key(data["product_key"]),
        conservative_result_id=data["conservative_result_id"],
        source_composition_id=data["source_composition_id"],
        acquisition_normalization_id=data["acquisition_normalization_id"],
        landed_cost_composition_id=data["landed_cost_composition_id"],
        sourcing_binding_id=data["sourcing_binding_id"],
        sourcing_admission_id=data["sourcing_admission_id"],
        sourcing_admission_revision=data["sourcing_admission_revision"],
        quote_id=data["quote_id"],
        quote_revision=data["quote_revision"],
        actual_outcome_id=data["actual_outcome_id"],
        purchase_execution_record_id=data["purchase_execution_record_id"],
        actual_acquisition_settlement_id=data["actual_acquisition_settlement_id"],
        actual_sale_settlement_ids=tuple(_list(data["actual_sale_settlement_ids"], "sale IDs")),
        currency=data["currency"],
        conservative_policy_name=data["conservative_policy_name"],
        conservative_policy_version=data["conservative_policy_version"],
        conservative_schema_version=data["conservative_schema_version"],
        actual_policy_name=data["actual_policy_name"],
        actual_policy_version=data["actual_policy_version"],
        actual_schema_version=data["actual_schema_version"],
        conservative_calculated_at=_datetime(data["conservative_calculated_at"], "conservative_calculated_at"),
        purchase_executed_at=_datetime(data["purchase_executed_at"], "purchase_executed_at"),
        conservative_source_snapshot=data["conservative_source_snapshot"],
        actual_source_snapshot=data["actual_source_snapshot"],
        conservative_source_fingerprint=data["conservative_source_fingerprint"],
        actual_source_fingerprint=data["actual_source_fingerprint"],
        source_pair_fingerprint=data["source_pair_fingerprint"],
        schema_version=data["schema_version"],
    )


_METRIC_FIELDS = {
    "metric_name", "direction", "comparability", "predicted_value", "actual_value",
    "variance", "relative_variance_percent", "variance_percentage_points",
    "favorability", "unit", "currency", "reason_codes", "predicted_scope_total",
    "actual_scope_total", "scope_total_variance",
}


def _load_metric(value: object) -> ConservativeActualVarianceMetric:
    data = _exact(value, _METRIC_FIELDS, "Variance v2 metric")
    return ConservativeActualVarianceMetric(
        metric_name=data["metric_name"],
        direction=VarianceMetricDirection(data["direction"]),
        comparability=VarianceMetricComparability(data["comparability"]),
        predicted_value=_optional_decimal(data["predicted_value"], "predicted_value"),
        actual_value=_optional_decimal(data["actual_value"], "actual_value"),
        variance=_optional_decimal(data["variance"], "variance"),
        relative_variance_percent=_optional_decimal(data["relative_variance_percent"], "relative_variance_percent"),
        variance_percentage_points=_optional_decimal(data["variance_percentage_points"], "variance_percentage_points"),
        favorability=VarianceFavorability(data["favorability"]),
        unit=data["unit"],
        currency=data["currency"],
        reason_codes=tuple(_list(data["reason_codes"], "metric reasons")),
        predicted_scope_total=_optional_decimal(data["predicted_scope_total"], "predicted_scope_total"),
        actual_scope_total=_optional_decimal(data["actual_scope_total"], "actual_scope_total"),
        scope_total_variance=_optional_decimal(data["scope_total_variance"], "scope_total_variance"),
    )


def _load_contributor(value: object) -> ConservativeActualVarianceContributor:
    data = _exact(
        value,
        {"category", "amount", "currency", "classification", "source_references"},
        "actual-only contributor",
    )
    return ConservativeActualVarianceContributor(
        data["category"],
        _decimal(data["amount"], "contributor amount"),
        data["currency"],
        VarianceMetricComparability(data["classification"]),
        tuple(_list(data["source_references"], "source references")),
    )


def _load_predicted(value: object) -> ConservativeActualPredictedContext:
    data = _exact(
        value,
        {"category", "predicted_value", "currency", "classification", "source_reference"},
        "predicted-only context",
    )
    return ConservativeActualPredictedContext(
        data["category"],
        _decimal(data["predicted_value"], "predicted context value"),
        data["currency"],
        VarianceMetricComparability(data["classification"]),
        data["source_reference"],
    )


def _load_exposure(value: object) -> ConservativeActualExposureContext:
    fields = {
        "remaining_sellable_quantity", "remaining_inventory_cost_basis",
        "unreceived_quantity", "unreceived_acquisition_basis", "damaged_quantity",
        "damaged_acquisition_loss", "returned_quantity", "inventory_resolution",
        "quantity_unit", "currency",
    }
    data = _exact(value, fields, "exposure context")
    return ConservativeActualExposureContext(
        data["remaining_sellable_quantity"],
        _decimal(data["remaining_inventory_cost_basis"], "remaining basis"),
        data["unreceived_quantity"],
        _decimal(data["unreceived_acquisition_basis"], "unreceived basis"),
        data["damaged_quantity"],
        _decimal(data["damaged_acquisition_loss"], "damaged loss"),
        data["returned_quantity"],
        ActualOutcomeInventoryResolution(data["inventory_resolution"]),
        data["quantity_unit"],
        data["currency"],
    )


def _load_scenario(value: object) -> ConservativeActualScenarioContext:
    data = _exact(
        value,
        {"scenario_name", "scenario_version", "sale_price_factor", "assumption_owner", "conservative_policy_name", "conservative_policy_version"},
        "scenario context",
    )
    return ConservativeActualScenarioContext(
        data["scenario_name"], data["scenario_version"],
        _decimal(data["sale_price_factor"], "sale price factor"),
        data["assumption_owner"], data["conservative_policy_name"],
        data["conservative_policy_version"],
    )


def _load_scope(value: object) -> ConservativeActualScopeContext:
    fields = {
        "sold_quantity", "executed_quantity", "inventory_resolution", "sale_windows",
        "remaining_sellable_quantity", "damaged_quantity", "returned_quantity",
        "unreceived_quantity", "quantity_unit",
    }
    data = _exact(value, fields, "actual scope context")
    windows = []
    for raw in _list(data["sale_windows"], "sale windows"):
        item = _exact(raw, {"settlement_id", "period_start", "period_end"}, "sale window")
        windows.append(ActualOutcomeSaleWindow(
            item["settlement_id"],
            _datetime(item["period_start"], "period_start"),
            _datetime(item["period_end"], "period_end"),
        ))
    return ConservativeActualScopeContext(
        data["sold_quantity"], data["executed_quantity"],
        ActualOutcomeInventoryResolution(data["inventory_resolution"]), tuple(windows),
        data["remaining_sellable_quantity"], data["damaged_quantity"],
        data["returned_quantity"], data["unreceived_quantity"], data["quantity_unit"],
    )


_PAYLOAD_FIELDS = {
    "variance_id", "source_manifest", "comparison_state", "calibration_eligibility",
    "calibration_reasons", "core_metrics", "acquisition_component_metrics",
    "actual_only_contributors", "predicted_only_context", "exposure_context",
    "scenario_context", "actual_scope_context", "requested_at", "calculated_at",
    "committed_at", "policy_name", "policy_version", "policy_precision",
    "policy_rounding", "schema_version",
}


def _payload(value: ConservativeActualVariance) -> str:
    return _dump(_canonical(value))


class SQLiteConservativeActualVarianceRepository:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._conservative = SQLiteConservativeEconomicsRepository(connection=self._connection)
        self._actual = SQLiteActualOutcomeRepository(connection=self._connection)
        self._economics_sources = SQLiteEconomicsSourceCompositionRepository(connection=self._connection)
        self._normalizations = SQLiteAcquisitionCostNormalizationRepository(connection=self._connection)
        self._landed = SQLiteLandedCostCompositionRepository(connection=self._connection)
        self._bindings = SQLiteSourcingEconomicsBindingRepository(connection=self._connection)
        self._sourcing = SQLiteSourcingAuthorityRepository(connection=self._connection)
        self._requirements = SQLitePlannedAcquisitionCapitalRequirementRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                variance_id TEXT PRIMARY KEY,
                scope_fingerprint TEXT NOT NULL UNIQUE,
                opportunity_id TEXT NOT NULL,
                conservative_result_id TEXT NOT NULL,
                actual_outcome_id TEXT NOT NULL,
                comparison_state TEXT NOT NULL,
                calibration_eligibility TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(conservative_result_id) REFERENCES conservative_economics_history(result_id),
                FOREIGN KEY(actual_outcome_id) REFERENCES actual_outcome_history(outcome_id)
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                variance_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(variance_id) REFERENCES {HISTORY_TABLE}(variance_id)
            )""")
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()} "
                        f"BEFORE {operation} ON {table} BEGIN "
                        f"SELECT RAISE(ABORT,'{table} is append-only'); END"
                    )

    def get_conservative_result(self, result_id: str):
        return self._conservative.get_result(result_id)

    def get_actual_outcome(self, outcome_id: str):
        return self._actual.get_outcome(outcome_id)

    def get_source_composition(self, composition_id: str):
        return self._economics_sources.get_composition(composition_id)

    def get_acquisition_normalization(self, normalization_id: str):
        return self._normalizations.get_normalization(normalization_id)

    def get_landed_cost_composition(self, composition_id: str):
        return self._landed.get_composition(composition_id)

    def get_sourcing_binding(self, binding_id: str):
        return self._bindings.get_binding(binding_id)

    def get_sourcing_admission(self, admission_id: str, revision: int):
        return self._sourcing.get_admission_revision(admission_id, revision)

    def get_capital_requirement(self, requirement_id: str):
        return self._requirements.get_requirement(requirement_id)

    def _row(self, variance_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE variance_id=?", (variance_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ConservativeActualVarianceHistoryError("Variance v2 query failed") from error

    def _load_row(self, row) -> ConservativeActualVariance:
        try:
            if row["schema_version"] != CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION:
                raise UnsupportedConservativeActualVarianceVersionError(
                    "unsupported Variance v2 version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Variance v2 integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_FIELDS, "Variance v2 payload")
            for name in (
                "calibration_reasons", "core_metrics", "acquisition_component_metrics",
                "actual_only_contributors", "predicted_only_context",
            ):
                _list(data[name], name)
            value = ConservativeActualVariance(
                variance_id=data["variance_id"],
                source_manifest=_load_manifest(data["source_manifest"]),
                comparison_state=VarianceComparisonState(data["comparison_state"]),
                calibration_eligibility=VarianceCalibrationEligibility(data["calibration_eligibility"]),
                calibration_reasons=tuple(VarianceCalibrationReason(item) for item in data["calibration_reasons"]),
                core_metrics=tuple(_load_metric(item) for item in data["core_metrics"]),
                acquisition_component_metrics=tuple(_load_metric(item) for item in data["acquisition_component_metrics"]),
                actual_only_contributors=tuple(_load_contributor(item) for item in data["actual_only_contributors"]),
                predicted_only_context=tuple(_load_predicted(item) for item in data["predicted_only_context"]),
                exposure_context=_load_exposure(data["exposure_context"]),
                scenario_context=_load_scenario(data["scenario_context"]),
                actual_scope_context=_load_scope(data["actual_scope_context"]),
                requested_at=_datetime(data["requested_at"], "requested_at"),
                calculated_at=_datetime(data["calculated_at"], "calculated_at"),
                committed_at=_datetime(data["committed_at"], "committed_at"),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                policy_precision=data["policy_precision"],
                policy_rounding=data["policy_rounding"],
                schema_version=data["schema_version"],
            )
            manifest = value.source_manifest
            expected_scope = conservative_actual_variance_scope_fingerprint(
                manifest.conservative_result_id, manifest.actual_outcome_id
            )
            if any((
                value.variance_id != row["variance_id"],
                manifest.source_pair_fingerprint != row["scope_fingerprint"],
                expected_scope != row["scope_fingerprint"],
                manifest.opportunity_identity.opportunity_id != row["opportunity_id"],
                manifest.conservative_result_id != row["conservative_result_id"],
                manifest.actual_outcome_id != row["actual_outcome_id"],
                value.comparison_state.value != row["comparison_state"],
                value.calibration_eligibility.value != row["calibration_eligibility"],
                value.policy_name != row["policy_name"],
                value.policy_version != row["policy_version"],
            )):
                raise ValueError("Variance v2 columns differ from payload")
            if _integrity(manifest.conservative_source_snapshot) != manifest.conservative_source_fingerprint:
                raise ValueError("Conservative snapshot fingerprint differs")
            if _integrity(manifest.actual_source_snapshot) != manifest.actual_source_fingerprint:
                raise ValueError("Actual snapshot fingerprint differs")
            return value
        except UnsupportedConservativeActualVarianceVersionError:
            raise
        except Exception as error:
            raise MalformedConservativeActualVariancePersistenceError(
                "persisted Variance v2 is malformed"
            ) from error

    def get_variance(self, variance_id: str):
        row = self._row(variance_id)
        return None if row is None else self._load_row(row)

    def find_by_scope(self, scope_fingerprint: str):
        try:
            row = self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE scope_fingerprint=?",
                (scope_fingerprint,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ConservativeActualVarianceHistoryError(
                "Variance v2 scope query failed"
            ) from error
        return None if row is None else self._load_row(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ConservativeActualVarianceReceiptError(
                "Variance v2 receipt query failed"
            ) from error

    def _load_receipt(self, row):
        try:
            if row["schema_version"] != CONSERVATIVE_ACTUAL_VARIANCE_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedConservativeActualVarianceVersionError(
                    "unsupported Variance v2 receipt version"
                )
            receipt = ConservativeActualVarianceReceipt(
                row["command_id"], row["variance_id"], row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"), row["schema_version"],
            )
            if self.get_variance(receipt.variance_id) is None:
                raise ValueError("Variance v2 receipt is orphaned")
            return receipt
        except UnsupportedConservativeActualVarianceVersionError:
            raise
        except Exception as error:
            raise MalformedConservativeActualVariancePersistenceError(
                "persisted Variance v2 receipt is malformed"
            ) from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ConservativeActualVarianceReplayConflictError(
                "Variance v2 command payload conflicts"
            )
        return ConservativeActualVariancePublication(
            self.get_variance(receipt.variance_id), receipt, True
        )

    @staticmethod
    def _validate_write(
        command,
        variance,
        receipt,
        scope_fingerprint: str,
        *,
        existing_scope: bool,
    ) -> None:
        if not isinstance(command, CalculateConservativeActualVarianceCommand):
            raise TypeError("Variance v2 command has unsupported type")
        if not isinstance(variance, ConservativeActualVariance):
            raise TypeError("Variance v2 result has unsupported type")
        if not isinstance(receipt, ConservativeActualVarianceReceipt):
            raise TypeError("Variance v2 receipt has unsupported type")
        manifest = variance.source_manifest
        if any((
            receipt.command_id != command.command_id,
            receipt.command_fingerprint != command.fingerprint,
            receipt.variance_id != variance.variance_id,
            manifest.opportunity_identity.opportunity_id != command.opportunity_id,
            manifest.conservative_result_id != command.conservative_economics_result_id,
            manifest.actual_outcome_id != command.actual_outcome_id,
            not existing_scope and variance.requested_at != command.requested_at,
            scope_fingerprint != manifest.source_pair_fingerprint,
            scope_fingerprint != conservative_actual_variance_scope_fingerprint(
                manifest.conservative_result_id, manifest.actual_outcome_id
            ),
        )):
            raise ConservativeActualVarianceReplayConflictError(
                "command, Variance v2, and receipt differ"
            )

    def _validate_sources(self, variance: ConservativeActualVariance) -> None:
        manifest = variance.source_manifest
        conservative = self.get_conservative_result(manifest.conservative_result_id)
        actual = self.get_actual_outcome(manifest.actual_outcome_id)
        if conservative is None or actual is None:
            raise ConservativeActualVarianceSourceConflictError(
                "Variance v2 exact source is missing"
            )
        if _snapshot(conservative) != manifest.conservative_source_snapshot:
            raise ConservativeActualVarianceSourceConflictError(
                "Variance v2 Conservative snapshot differs"
            )
        if _snapshot(actual) != manifest.actual_source_snapshot:
            raise ConservativeActualVarianceSourceConflictError(
                "Variance v2 Actual snapshot differs"
            )

    def _insert_history(self, variance, scope_fingerprint: str) -> None:
        encoded = _payload(variance)
        manifest = variance.source_manifest
        try:
            self._connection.execute(
                f"INSERT INTO {HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    variance.variance_id, scope_fingerprint,
                    manifest.opportunity_identity.opportunity_id,
                    manifest.conservative_result_id, manifest.actual_outcome_id,
                    variance.comparison_state.value,
                    variance.calibration_eligibility.value,
                    encoded, _integrity(encoded), variance.policy_name,
                    variance.policy_version, variance.schema_version,
                    variance.committed_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ConservativeActualVarianceSourceConflictError(
                "Variance v2 scope or identity already exists"
            ) from error
        except sqlite3.Error as error:
            raise ConservativeActualVarianceHistoryError(
                "Variance v2 history insert failed"
            ) from error

    def _insert_receipt(self, receipt) -> None:
        try:
            self._connection.execute(
                f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?)",
                (
                    receipt.command_id, receipt.variance_id,
                    receipt.command_fingerprint, receipt.committed_at.isoformat(),
                    receipt.schema_version, receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise ConservativeActualVarianceReceiptError(
                "Variance v2 receipt insert failed"
            ) from error

    def _commit(self) -> None:
        self._connection.commit()

    def save(self, command, variance, receipt, scope_fingerprint: str):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.commit()
                return replay
            self._validate_sources(variance)
            existing = self.find_by_scope(scope_fingerprint)
            self._validate_write(
                command,
                variance,
                receipt,
                scope_fingerprint,
                existing_scope=existing is not None,
            )
            aliased = existing is not None
            if existing is None:
                self._insert_history(variance, scope_fingerprint)
                persisted = variance
                persisted_receipt = receipt
            else:
                persisted = existing
                persisted_receipt = ConservativeActualVarianceReceipt(
                    receipt.command_id, existing.variance_id,
                    receipt.command_fingerprint, receipt.committed_at,
                )
            self._insert_receipt(persisted_receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ConservativeActualVarianceCommitError(
                    "Variance v2 commit failed"
                ) from error
            return ConservativeActualVariancePublication(
                persisted, persisted_receipt, False, aliased
            )
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def close(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, traceback): self.close(); return False


__all__ = [
    name
    for name in globals()
    if name.startswith((
        "SQLiteConservativeActual", "ConservativeActualVariance",
        "MalformedConservativeActual", "UnsupportedConservativeActual",
    ))
]
