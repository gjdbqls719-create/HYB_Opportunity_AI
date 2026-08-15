"""Atomic append-only SQLite persistence for Founder-assisted sourcing facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing import (
    AdmitFounderSourcingCommand,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionReceipt,
    SourcingAdmissionReplayConflictError,
    SourcingAdmissionResult,
    SourcingQuoteRevisionConflictError,
)
from app.application.sourcing.models import (
    SOURCING_ADMISSION_RECEIPT_SCHEMA_VERSION,
    SourcingEconomicsSourceReference,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.opportunity import (
    NewToMarketDomesticSellingTargetIdentity,
    NewToMarketDomesticSellingTargetKind,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION,
    DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    NEW_TO_MARKET_DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION,
    NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    DomesticSellingProductLineage,
    FounderSourcingAdmission,
    MatchVerificationStatus,
    NewToMarketDomesticSellingProductLineage,
    ProductMatchVerification,
    SellingProductLineage,
    ShippingScope,
    ShippingTerm,
    SourcingEvidenceKind,
    SourcingEvidenceReference,
    SourcingMoneyFact,
    SourcingProductIdentity,
    SourcingQuantityFact,
    SupplierIdentity,
    SupplierQuoteRevision,
    PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION,
    SOURCING_AUTHORITY_SCHEMA_VERSION,
    SOURCING_EVIDENCE_SCHEMA_VERSION,
    SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION,
    SUPPLIER_IDENTITY_SCHEMA_VERSION,
    SUPPLIER_QUOTE_SCHEMA_VERSION,
)
from app.infrastructure.domestic_selling_opportunity import (
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.new_to_market_domestic_selling import (
    NewToMarketDomesticSellingPersistenceError,
    SQLiteNewToMarketDomesticSellingAdmissionRepository,
)


class SourcingAuthorityPersistenceError(RuntimeError):
    pass


class SourcingSupplierHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingProductHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingMatchHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingQuoteHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingAdmissionHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingReceiptHistoryError(SourcingAuthorityPersistenceError):
    pass


class SourcingAuthorityCommitError(SourcingAuthorityPersistenceError):
    pass


class MalformedSourcingAuthorityPersistenceError(SourcingAuthorityPersistenceError):
    pass


class UnsupportedSourcingAuthorityVersionError(
    MalformedSourcingAuthorityPersistenceError
):
    pass


def _dump(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dt(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _artifact(value: ArtifactReference | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "artifact_id": value.artifact_id,
        "artifact_type": value.artifact_type.value,
        "artifact_origin": value.artifact_origin.value,
        "source_type": value.source_type.value,
        "sha256": value.sha256,
        "captured_at": value.captured_at.isoformat(),
        "width": value.width,
        "height": value.height,
        "mime_type": value.mime_type,
        "file_size": value.file_size,
        "schema_version": value.schema_version,
    }


def _load_artifact(value: object) -> ArtifactReference | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("artifact must be an object")
    return ArtifactReference(
        artifact_id=value["artifact_id"],
        artifact_type=ArtifactType(value["artifact_type"]),
        artifact_origin=ArtifactOrigin(value["artifact_origin"]),
        source_type=ExternalSignalSourceType(value["source_type"]),
        sha256=value["sha256"],
        captured_at=_dt(value["captured_at"], "artifact captured_at"),
        width=value["width"],
        height=value["height"],
        mime_type=value["mime_type"],
        file_size=value["file_size"],
        schema_version=value["schema_version"],
    )


def _market(value: MarketObservationIdentity) -> dict[str, object]:
    return {
        "scope": value.scope.value,
        "market": value.market,
        "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id,
        "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query,
        "category": value.category,
        "variant_identity": value.variant_identity,
        "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(),
    }


def _load_market(value: object) -> MarketObservationIdentity:
    if not isinstance(value, dict):
        raise ValueError("market identity must be an object")
    return MarketObservationIdentity(
        scope=MarketObservationScope(value["scope"]),
        market=value["market"], marketplace=value["marketplace"],
        canonical_product_id=value["canonical_product_id"],
        marketplace_item_id=value["marketplace_item_id"],
        normalized_query=value["normalized_query"], category=value["category"],
        variant_identity=value["variant_identity"], condition=value["condition"],
        window_started_at=_dt(value["window_started_at"], "window_started_at"),
        window_ended_at=_dt(value["window_ended_at"], "window_ended_at"),
    )


def _lineage(value) -> dict[str, object]:
    if isinstance(value, NewToMarketDomesticSellingProductLineage):
        target = value.target_identity
        return {
            "lineage_kind": "new_to_market_domestic_selling_admission",
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "new_to_market_domestic_selling_admission_id": (
                value.new_to_market_domestic_selling_admission_id
            ),
            "target_identity": {
                "domestic_selling_target_id": target.domestic_selling_target_id,
                "market": target.market,
                "kind": target.kind.value,
                "schema_version": target.schema_version,
            },
            "schema_version": value.schema_version,
        }
    if isinstance(value, DomesticSellingProductLineage):
        return {
            "lineage_kind": "domestic_selling_admission",
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "domestic_selling_admission_id": value.domestic_selling_admission_id,
            "source_opportunity_identity": {
                "opportunity_id": value.source_opportunity_identity.opportunity_id,
                "discovery_reference": value.source_opportunity_identity.discovery_reference,
            },
            "source_product_observation_snapshot_id": value.source_product_observation_snapshot_id,
            "market_observation_identity": _market(value.market_observation_identity),
            "product_equivalence_evidence_reference": value.product_equivalence_evidence_reference,
            "schema_version": value.schema_version,
        }
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "candidate_id": value.candidate_id,
        "candidate_opportunity_binding_id": value.candidate_opportunity_binding_id,
        "product_observation_snapshot_id": value.product_observation_snapshot_id,
        "market_observation_identity": _market(value.market_observation_identity),
    }


def _load_lineage(value: object):
    if not isinstance(value, dict) or not isinstance(value.get("opportunity_identity"), dict):
        raise ValueError("selling lineage must be an object")
    opportunity = value["opportunity_identity"]
    if value.get("lineage_kind") == "new_to_market_domestic_selling_admission":
        if value.get("schema_version") != (
            NEW_TO_MARKET_DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION
        ):
            raise UnsupportedSourcingAuthorityVersionError(
                "unsupported new-to-market domestic selling lineage version"
            )
        target = value.get("target_identity")
        if not isinstance(target, dict):
            raise ValueError("new-to-market target identity is malformed")
        return NewToMarketDomesticSellingProductLineage(
            opportunity_identity=OpportunityIdentity(
                opportunity["opportunity_id"], opportunity["discovery_reference"]
            ),
            new_to_market_domestic_selling_admission_id=value[
                "new_to_market_domestic_selling_admission_id"
            ],
            target_identity=NewToMarketDomesticSellingTargetIdentity(
                domestic_selling_target_id=target["domestic_selling_target_id"],
                market=target["market"],
                kind=NewToMarketDomesticSellingTargetKind(target["kind"]),
                schema_version=target["schema_version"],
            ),
            schema_version=value["schema_version"],
        )
    if value.get("lineage_kind") == "domestic_selling_admission":
        if value.get("schema_version") != DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION:
            raise UnsupportedSourcingAuthorityVersionError(
                "unsupported domestic selling lineage version"
            )
        source = value.get("source_opportunity_identity")
        if not isinstance(source, dict):
            raise ValueError("source Opportunity identity is malformed")
        return DomesticSellingProductLineage(
            opportunity_identity=OpportunityIdentity(
                opportunity["opportunity_id"], opportunity["discovery_reference"]
            ),
            domestic_selling_admission_id=value["domestic_selling_admission_id"],
            source_opportunity_identity=OpportunityIdentity(
                source["opportunity_id"], source["discovery_reference"]
            ),
            source_product_observation_snapshot_id=value[
                "source_product_observation_snapshot_id"
            ],
            market_observation_identity=_load_market(value["market_observation_identity"]),
            product_equivalence_evidence_reference=value[
                "product_equivalence_evidence_reference"
            ],
            schema_version=value["schema_version"],
        )
    return SellingProductLineage(
        opportunity_identity=OpportunityIdentity(
            opportunity["opportunity_id"], opportunity["discovery_reference"]
        ),
        candidate_id=value["candidate_id"],
        candidate_opportunity_binding_id=value["candidate_opportunity_binding_id"],
        product_observation_snapshot_id=value["product_observation_snapshot_id"],
        market_observation_identity=_load_market(value["market_observation_identity"]),
    )


def _evidence(value: SourcingEvidenceReference) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "source_reference": value.source_reference,
        "observed_at": value.observed_at.isoformat(),
        "artifact_reference": _artifact(value.artifact_reference),
        "schema_version": value.schema_version,
    }


def _load_evidence(value: object) -> SourcingEvidenceReference:
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    if value.get("schema_version") != SOURCING_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedSourcingAuthorityVersionError(
            "unsupported sourcing evidence version"
        )
    return SourcingEvidenceReference(
        kind=SourcingEvidenceKind(value["kind"]),
        source_reference=value["source_reference"],
        observed_at=_dt(value["observed_at"], "evidence observed_at"),
        artifact_reference=_load_artifact(value["artifact_reference"]),
        schema_version=value["schema_version"],
    )


def _money(value: SourcingMoneyFact) -> dict[str, object]:
    return {
        "availability": value.availability.value,
        "amount": None if value.amount is None else str(value.amount),
        "currency": value.currency,
    }


def _load_money(value: object) -> SourcingMoneyFact:
    if not isinstance(value, dict):
        raise ValueError("money must be an object")
    return SourcingMoneyFact(
        CommercialFactAvailability(value["availability"]),
        None if value["amount"] is None else Decimal(value["amount"]),
        value["currency"],
    )


def _quantity(value: SourcingQuantityFact) -> dict[str, object]:
    return {"availability": value.availability.value, "quantity": value.quantity}


def _load_quantity(value: object) -> SourcingQuantityFact:
    if not isinstance(value, dict):
        raise ValueError("quantity must be an object")
    return SourcingQuantityFact(
        CommercialFactAvailability(value["availability"]), value["quantity"]
    )


def _supplier(value: SupplierIdentity) -> dict[str, object]:
    return {
        "supplier_id": value.supplier_id,
        "source_platform": value.source_platform,
        "external_supplier_reference": value.external_supplier_reference,
        "display_name": value.display_name,
        "schema_version": value.schema_version,
    }


def _load_supplier(value: object) -> SupplierIdentity:
    if not isinstance(value, dict):
        raise ValueError("supplier must be an object")
    if value.get("schema_version") != SUPPLIER_IDENTITY_SCHEMA_VERSION:
        raise UnsupportedSourcingAuthorityVersionError("unsupported Supplier version")
    return SupplierIdentity(**value)


def _product(value: SourcingProductIdentity) -> dict[str, object]:
    return {
        "sourcing_product_id": value.sourcing_product_id,
        "supplier_id": value.supplier_id,
        "external_product_reference": value.external_product_reference,
        "option_reference": value.option_reference,
        "sku_reference": value.sku_reference,
        "source_url": value.source_url,
        "observed_at": value.observed_at.isoformat(),
        "schema_version": value.schema_version,
    }


def _load_product(value: object) -> SourcingProductIdentity:
    if not isinstance(value, dict):
        raise ValueError("Sourcing Product must be an object")
    if value.get("schema_version") != SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION:
        raise UnsupportedSourcingAuthorityVersionError(
            "unsupported Sourcing Product version"
        )
    return SourcingProductIdentity(
        value["sourcing_product_id"], value["supplier_id"],
        value["external_product_reference"], value["option_reference"],
        value["sku_reference"], value["source_url"],
        _dt(value["observed_at"], "product observed_at"), value["schema_version"],
    )


def _quote(value: SupplierQuoteRevision) -> dict[str, object]:
    return {
        "quote_id": value.quote_id, "revision": value.revision,
        "sourcing_product_id": value.sourcing_product_id,
        "unit_price": _money(value.unit_price),
        "minimum_order_quantity": _quantity(value.minimum_order_quantity),
        "quoted_quantity": _quantity(value.quoted_quantity),
        "shipping_terms": [
            {"scope": term.scope.value, "cost": _money(term.cost)}
            for term in value.shipping_terms
        ],
        "lead_time_availability": value.lead_time_availability.value,
        "lead_time_days": value.lead_time_days,
        "observed_at": value.observed_at.isoformat(),
        "valid_until": None if value.valid_until is None else value.valid_until.isoformat(),
        "evidence": _evidence(value.evidence),
        "schema_version": value.schema_version,
    }


def _load_quote(value: object) -> SupplierQuoteRevision:
    if not isinstance(value, dict):
        raise ValueError("Quote must be an object")
    if value.get("schema_version") != SUPPLIER_QUOTE_SCHEMA_VERSION:
        raise UnsupportedSourcingAuthorityVersionError("unsupported Quote version")
    terms = value["shipping_terms"]
    if not isinstance(terms, list):
        raise ValueError("shipping terms must be a list")
    return SupplierQuoteRevision(
        value["quote_id"], value["revision"], value["sourcing_product_id"],
        _load_money(value["unit_price"]),
        _load_quantity(value["minimum_order_quantity"]),
        _load_quantity(value["quoted_quantity"]),
        tuple(ShippingTerm(ShippingScope(term["scope"]), _load_money(term["cost"])) for term in terms),
        CommercialFactAvailability(value["lead_time_availability"]),
        value["lead_time_days"], _dt(value["observed_at"], "quote observed_at"),
        None if value["valid_until"] is None else _dt(value["valid_until"], "valid_until"),
        _load_evidence(value["evidence"]), value["schema_version"],
    )


def _match(value: ProductMatchVerification) -> dict[str, object]:
    return {
        "verification_id": value.verification_id,
        "selling_product_lineage": _lineage(value.selling_product_lineage),
        "sourcing_product_id": value.sourcing_product_id,
        "status": value.status.value,
        "verifier_id": value.verifier_id,
        "verified_at": value.verified_at.isoformat(),
        "evidence": _evidence(value.evidence),
        "proposal_score": None if value.proposal_score is None else str(value.proposal_score),
        "proposal_version": value.proposal_version,
        "schema_version": value.schema_version,
    }


def _load_match(value: object) -> ProductMatchVerification:
    if not isinstance(value, dict):
        raise ValueError("Match Verification must be an object")
    if value.get("schema_version") != PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION:
        raise UnsupportedSourcingAuthorityVersionError(
            "unsupported Match Verification version"
        )
    return ProductMatchVerification(
        value["verification_id"], _load_lineage(value["selling_product_lineage"]),
        value["sourcing_product_id"], MatchVerificationStatus(value["status"]),
        value["verifier_id"], _dt(value["verified_at"], "verified_at"),
        _load_evidence(value["evidence"]),
        None if value["proposal_score"] is None else Decimal(value["proposal_score"]),
        value["proposal_version"], value["schema_version"],
    )


def _admission(value: FounderSourcingAdmission) -> dict[str, object]:
    return {
        "admission_id": value.admission_id, "revision": value.revision,
        "selling_product_lineage": _lineage(value.selling_product_lineage),
        "supplier_identity": _supplier(value.supplier_identity),
        "sourcing_product_identity": _product(value.sourcing_product_identity),
        "quote_revision": _quote(value.quote_revision),
        "match_verification": _match(value.match_verification),
        "admitted_by": value.admitted_by,
        "requested_at": value.requested_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "schema_version": value.schema_version,
    }


def _load_admission(value: object) -> FounderSourcingAdmission:
    if not isinstance(value, dict):
        raise ValueError("Admission must be an object")
    if value.get("schema_version") not in {
        SOURCING_AUTHORITY_SCHEMA_VERSION,
        DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
        NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    }:
        raise UnsupportedSourcingAuthorityVersionError("unsupported Admission version")
    return FounderSourcingAdmission(
        value["admission_id"], value["revision"],
        _load_lineage(value["selling_product_lineage"]),
        _load_supplier(value["supplier_identity"]),
        _load_product(value["sourcing_product_identity"]),
        _load_quote(value["quote_revision"]),
        _load_match(value["match_verification"]), value["admitted_by"],
        _dt(value["requested_at"], "requested_at"),
        _dt(value["admitted_at"], "admitted_at"), value["schema_version"],
    )


class SQLiteSourcingAuthorityRepository:
    """Stores exact Application-issued facts; it issues no identity or revision."""

    def __init__(self, database_path: str | Path | None = None, *, connection=None):
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def get_domestic_selling_admission(self, admission_id):
        reader = SQLiteDomesticSellingOpportunityAdmissionRepository(
            connection=self._connection
        )
        publication = reader.get_admission(admission_id)
        return None if publication is None else publication.admission

    def get_new_to_market_domestic_selling_admission(self, admission_id):
        try:
            reader = SQLiteNewToMarketDomesticSellingAdmissionRepository(
                connection=self._connection
            )
            publication = reader.get_admission(admission_id)
            return None if publication is None else publication.admission
        except NewToMarketDomesticSellingPersistenceError as error:
            raise SourcingAuthorityPersistenceError(
                "new-to-market domestic selling source is unavailable"
            ) from error

    def _initialize_schema(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS sourcing_supplier_history(
                supplier_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL, schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS sourcing_product_history(
                sourcing_product_id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, payload_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(supplier_id) REFERENCES sourcing_supplier_history(supplier_id))""",
            """CREATE TABLE IF NOT EXISTS sourcing_match_verification_history(
                verification_id TEXT PRIMARY KEY, sourcing_product_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, payload_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(sourcing_product_id) REFERENCES sourcing_product_history(sourcing_product_id))""",
            """CREATE TABLE IF NOT EXISTS sourcing_quote_revision_history(
                quote_id TEXT NOT NULL, revision INTEGER NOT NULL,
                sourcing_product_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL, schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL, PRIMARY KEY(quote_id,revision),
                FOREIGN KEY(sourcing_product_id) REFERENCES sourcing_product_history(sourcing_product_id))""",
            """CREATE TABLE IF NOT EXISTS founder_sourcing_admission_history(
                admission_id TEXT NOT NULL, revision INTEGER NOT NULL,
                source_command_id TEXT NOT NULL UNIQUE, supplier_id TEXT NOT NULL,
                sourcing_product_id TEXT NOT NULL, quote_id TEXT NOT NULL,
                verification_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL, command_fingerprint TEXT NOT NULL,
                economics_source_json TEXT NOT NULL, schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL, PRIMARY KEY(admission_id,revision),
                FOREIGN KEY(supplier_id) REFERENCES sourcing_supplier_history(supplier_id),
                FOREIGN KEY(sourcing_product_id) REFERENCES sourcing_product_history(sourcing_product_id),
                FOREIGN KEY(quote_id,revision) REFERENCES sourcing_quote_revision_history(quote_id,revision),
                FOREIGN KEY(verification_id) REFERENCES sourcing_match_verification_history(verification_id))""",
            """CREATE TABLE IF NOT EXISTS sourcing_admission_receipts(
                command_id TEXT PRIMARY KEY, admission_id TEXT NOT NULL,
                resulting_revision INTEGER NOT NULL, command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL, schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(admission_id,resulting_revision)
                  REFERENCES founder_sourcing_admission_history(admission_id,revision))""",
        )
        with self._connection:
            for statement in statements:
                self._connection.execute(statement)
            for table in (
                "sourcing_supplier_history", "sourcing_product_history",
                "sourcing_match_verification_history", "sourcing_quote_revision_history",
                "founder_sourcing_admission_history", "sourcing_admission_receipts",
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def _begin(self) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise SourcingAuthorityCommitError(
                "Sourcing authority transaction could not start"
            ) from error

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    @staticmethod
    def _record(value: dict[str, object]) -> tuple[str, str]:
        payload = _dump(value)
        return payload, _fingerprint(payload)

    def _insert_supplier(self, value: SupplierIdentity, inserted_at: datetime) -> None:
        payload, fingerprint = self._record(_supplier(value))
        self._connection.execute(
            "INSERT INTO sourcing_supplier_history VALUES(?,?,?,?,?)",
            (value.supplier_id, payload, fingerprint, value.schema_version, inserted_at.isoformat()),
        )

    def _insert_product(self, value: SourcingProductIdentity, inserted_at: datetime) -> None:
        payload, fingerprint = self._record(_product(value))
        self._connection.execute(
            "INSERT INTO sourcing_product_history VALUES(?,?,?,?,?,?)",
            (value.sourcing_product_id, value.supplier_id, payload, fingerprint,
             value.schema_version, inserted_at.isoformat()),
        )

    def _insert_match(self, value: ProductMatchVerification, inserted_at: datetime) -> None:
        payload, fingerprint = self._record(_match(value))
        self._connection.execute(
            "INSERT INTO sourcing_match_verification_history VALUES(?,?,?,?,?,?)",
            (value.verification_id, value.sourcing_product_id, payload, fingerprint,
             value.schema_version, inserted_at.isoformat()),
        )

    def _insert_quote(self, value: SupplierQuoteRevision, inserted_at: datetime) -> None:
        payload, fingerprint = self._record(_quote(value))
        self._connection.execute(
            "INSERT INTO sourcing_quote_revision_history VALUES(?,?,?,?,?,?,?)",
            (value.quote_id, value.revision, value.sourcing_product_id, payload,
             fingerprint, value.schema_version, inserted_at.isoformat()),
        )

    def _insert_admission(
        self, command_id: str, command_fingerprint: str,
        value: FounderSourcingAdmission, inserted_at: datetime,
    ) -> None:
        payload, fingerprint = self._record(_admission(value))
        economics = SourcingEconomicsSourceReference(
            value.admission_id, value.revision,
            value.quote_revision.quote_id, value.quote_revision.revision,
        )
        economics_payload = _dump({
            "admission_id": economics.admission_id,
            "admission_revision": economics.admission_revision,
            "quote_id": economics.quote_id,
            "quote_revision": economics.quote_revision,
        })
        self._connection.execute(
            """INSERT INTO founder_sourcing_admission_history
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value.admission_id, value.revision, command_id,
             value.supplier_identity.supplier_id,
             value.sourcing_product_identity.sourcing_product_id,
             value.quote_revision.quote_id, value.match_verification.verification_id,
             payload, fingerprint, command_fingerprint, economics_payload,
             value.schema_version, inserted_at.isoformat()),
        )

    def _insert_receipt(self, value: SourcingAdmissionReceipt) -> None:
        self._connection.execute(
            "INSERT INTO sourcing_admission_receipts VALUES(?,?,?,?,?,?,?)",
            (value.command_id, value.admission_id, value.resulting_revision,
             value.command_fingerprint, value.committed_at.isoformat(),
             value.schema_version, value.committed_at.isoformat()),
        )

    def save_admission(self, command, admission, receipt):
        if not isinstance(command, AdmitFounderSourcingCommand):
            raise TypeError("command must be AdmitFounderSourcingCommand")
        self._validate_write(command.command_id, command.fingerprint, admission, receipt)
        if admission.revision != 1 or receipt.resulting_revision != 1:
            raise SourcingQuoteRevisionConflictError("initial admission must be revision 1")
        self._begin()
        try:
            replay = self._validate_replay_locked(command.command_id, command.fingerprint)
            if replay is not None:
                self._rollback()
                return replay
            if self._latest_row(admission.admission_id) is not None:
                raise SourcingQuoteRevisionConflictError("Sourcing admission already exists")
            self._phase(self._insert_supplier, SourcingSupplierHistoryError,
                        "Supplier history insert failed", admission.supplier_identity, receipt.committed_at)
            self._phase(self._insert_product, SourcingProductHistoryError,
                        "Sourcing Product history insert failed", admission.sourcing_product_identity, receipt.committed_at)
            self._phase(self._insert_match, SourcingMatchHistoryError,
                        "Match history insert failed", admission.match_verification, receipt.committed_at)
            self._phase(self._insert_quote, SourcingQuoteHistoryError,
                        "Quote history insert failed", admission.quote_revision, receipt.committed_at)
            self._phase(self._insert_admission, SourcingAdmissionHistoryError,
                        "Admission history insert failed", command.command_id,
                        command.fingerprint, admission, receipt.committed_at)
            self._phase(self._insert_receipt, SourcingReceiptHistoryError,
                        "Receipt history insert failed", receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise SourcingAuthorityCommitError("Sourcing admission commit failed") from error
            return SourcingAdmissionResult(admission, receipt, False)
        except Exception:
            self._rollback()
            raise

    def save_quote_revision(self, command, admission, receipt):
        if not isinstance(command, ReviseFounderSourcingQuoteCommand):
            raise TypeError("command must be ReviseFounderSourcingQuoteCommand")
        self._validate_write(command.command_id, command.fingerprint, admission, receipt)
        self._begin()
        try:
            replay = self._validate_replay_locked(command.command_id, command.fingerprint)
            if replay is not None:
                self._rollback()
                return replay
            current_row = self._latest_row(admission.admission_id)
            if current_row is None:
                raise SourcingQuoteRevisionConflictError("Sourcing admission is missing")
            current = self._from_admission_row(current_row)
            if current.revision != command.expected_revision:
                raise SourcingQuoteRevisionConflictError(
                    "Sourcing admission revision conflicts with expected revision"
                )
            if admission.revision != current.revision + 1:
                raise SourcingQuoteRevisionConflictError("Quote revision must be contiguous")
            if (
                admission.admission_id != current.admission_id
                or admission.supplier_identity != current.supplier_identity
                or admission.sourcing_product_identity != current.sourcing_product_identity
                or admission.match_verification != current.match_verification
                or admission.selling_product_lineage != current.selling_product_lineage
                or admission.quote_revision.quote_id != current.quote_revision.quote_id
            ):
                raise SourcingQuoteRevisionConflictError(
                    "Quote revision cannot change authoritative source identity"
                )
            self._phase(self._insert_quote, SourcingQuoteHistoryError,
                        "Quote revision insert failed", admission.quote_revision, receipt.committed_at)
            self._phase(self._insert_admission, SourcingAdmissionHistoryError,
                        "Admission revision insert failed", command.command_id,
                        command.fingerprint, admission, receipt.committed_at)
            self._phase(self._insert_receipt, SourcingReceiptHistoryError,
                        "Revision receipt insert failed", receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise SourcingAuthorityCommitError("Quote revision commit failed") from error
            return SourcingAdmissionResult(admission, receipt, False)
        except Exception:
            self._rollback()
            raise

    @staticmethod
    def _phase(function, error_type, message, *args):
        try:
            function(*args)
        except sqlite3.Error as error:
            raise error_type(message) from error

    @staticmethod
    def _validate_write(command_id, fingerprint, admission, receipt):
        if not isinstance(admission, FounderSourcingAdmission):
            raise TypeError("admission must be FounderSourcingAdmission")
        if not isinstance(receipt, SourcingAdmissionReceipt):
            raise TypeError("receipt must be SourcingAdmissionReceipt")
        if (
            receipt.command_id != command_id
            or receipt.command_fingerprint != fingerprint
            or receipt.admission_id != admission.admission_id
            or receipt.resulting_revision != admission.revision
        ):
            raise SourcingAdmissionReplayConflictError(
                "Sourcing command, Admission, and Receipt do not match"
            )

    def _receipt_row(self, command_id):
        try:
            return self._connection.execute(
                "SELECT * FROM sourcing_admission_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise SourcingReceiptHistoryError("Receipt query failed") from error

    def _receipt(self, row) -> SourcingAdmissionReceipt:
        try:
            if row["schema_version"] != SOURCING_ADMISSION_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedSourcingAuthorityVersionError(
                    "unsupported Sourcing Receipt version"
                )
            return SourcingAdmissionReceipt(
                row["command_id"], row["admission_id"], row["resulting_revision"],
                row["command_fingerprint"], _dt(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
        except UnsupportedSourcingAuthorityVersionError:
            raise
        except Exception as error:
            raise MalformedSourcingAuthorityPersistenceError(
                "persisted Sourcing Receipt is malformed"
            ) from error

    def validate_replay(self, command_id, fingerprint):
        return self._validate_replay_locked(command_id, fingerprint)

    def _validate_replay_locked(self, command_id, fingerprint):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise SourcingAdmissionReplayConflictError(
                "Sourcing command payload conflicts with committed Receipt"
            )
        admission = self.get_admission_revision(
            receipt.admission_id, receipt.resulting_revision
        )
        if admission is None:
            raise MalformedSourcingAuthorityPersistenceError(
                "Sourcing Receipt references missing Admission"
            )
        return SourcingAdmissionResult(admission, receipt, True)

    def _latest_row(self, admission_id):
        try:
            return self._connection.execute(
                """SELECT * FROM founder_sourcing_admission_history
                WHERE admission_id=? ORDER BY revision DESC LIMIT 1""",
                (admission_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise SourcingAdmissionHistoryError("Admission query failed") from error

    def get_admission(self, admission_id):
        row = self._latest_row(admission_id)
        return None if row is None else self._from_admission_row(row)

    def get_admission_revision(self, admission_id, revision):
        try:
            row = self._connection.execute(
                """SELECT * FROM founder_sourcing_admission_history
                WHERE admission_id=? AND revision=?""", (admission_id, revision)
            ).fetchone()
        except sqlite3.Error as error:
            raise SourcingAdmissionHistoryError("Admission revision query failed") from error
        return None if row is None else self._from_admission_row(row)

    def get_receipt(self, command_id):
        row = self._receipt_row(command_id)
        return None if row is None else self._receipt(row)

    def _fact_row(self, table, key_sql, values):
        try:
            row = self._connection.execute(
                f"SELECT * FROM {table} WHERE {key_sql}", values
            ).fetchone()
        except sqlite3.Error as error:
            raise MalformedSourcingAuthorityPersistenceError(
                "Sourcing source fact query failed"
            ) from error
        if row is None:
            raise MalformedSourcingAuthorityPersistenceError(
                "Sourcing Admission references a missing source fact"
            )
        return row

    @staticmethod
    def _payload(row, expected_version, loader):
        try:
            if row["schema_version"] != expected_version:
                raise UnsupportedSourcingAuthorityVersionError(
                    f"unsupported persisted Sourcing version: {row['schema_version']}"
                )
            payload = row["payload_json"]
            if _fingerprint(payload) != row["payload_fingerprint"]:
                raise ValueError("payload fingerprint mismatch")
            return loader(json.loads(payload))
        except UnsupportedSourcingAuthorityVersionError:
            raise
        except Exception as error:
            raise MalformedSourcingAuthorityPersistenceError(
                "persisted Sourcing fact is malformed"
            ) from error

    def _from_admission_row(self, row):
        admission = self._payload(row, row["schema_version"], _load_admission)
        supplier_row = self._fact_row(
            "sourcing_supplier_history", "supplier_id=?", (row["supplier_id"],)
        )
        product_row = self._fact_row(
            "sourcing_product_history", "sourcing_product_id=?",
            (row["sourcing_product_id"],),
        )
        match_row = self._fact_row(
            "sourcing_match_verification_history", "verification_id=?",
            (row["verification_id"],),
        )
        quote_row = self._fact_row(
            "sourcing_quote_revision_history", "quote_id=? AND revision=?",
            (row["quote_id"], row["revision"]),
        )
        supplier = self._payload(supplier_row, SUPPLIER_IDENTITY_SCHEMA_VERSION, _load_supplier)
        product = self._payload(product_row, SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION, _load_product)
        match = self._payload(match_row, PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION, _load_match)
        quote = self._payload(quote_row, SUPPLIER_QUOTE_SCHEMA_VERSION, _load_quote)
        try:
            economics = json.loads(row["economics_source_json"])
            source = SourcingEconomicsSourceReference(**economics)
        except Exception as error:
            raise MalformedSourcingAuthorityPersistenceError(
                "persisted Sourcing Economics reference is malformed"
            ) from error
        if (
            admission.admission_id != row["admission_id"]
            or admission.revision != row["revision"]
            or admission.supplier_identity != supplier
            or admission.sourcing_product_identity != product
            or admission.match_verification != match
            or admission.quote_revision != quote
            or source.admission_id != admission.admission_id
            or source.admission_revision != admission.revision
            or source.quote_id != quote.quote_id
        ):
            raise MalformedSourcingAuthorityPersistenceError(
                "persisted Sourcing lineage is inconsistent"
            )
        return admission

    def close(self):
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


__all__ = (
    "MalformedSourcingAuthorityPersistenceError",
    "SQLiteSourcingAuthorityRepository",
    "SourcingAdmissionHistoryError",
    "SourcingAuthorityCommitError",
    "SourcingAuthorityPersistenceError",
    "SourcingMatchHistoryError",
    "SourcingProductHistoryError",
    "SourcingQuoteHistoryError",
    "SourcingReceiptHistoryError",
    "SourcingSupplierHistoryError",
    "UnsupportedSourcingAuthorityVersionError",
)
