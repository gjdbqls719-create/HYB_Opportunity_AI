from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from app.application.market_observation import (
    DuplicateMarketObservationError,
    MarketObservation,
    MarketObservationRepository,
    MarketObservationType,
)
from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)


_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS market_observation_history (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL UNIQUE,
    observation_type TEXT NOT NULL,
    identity_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    CHECK (observation_type IN ('competition', 'demand', 'external_signal'))
)
"""

_CURRENT_TABLE = """
CREATE TABLE IF NOT EXISTS market_observation_current (
    observation_type TEXT NOT NULL,
    identity_key TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    projected_at TEXT NOT NULL,
    PRIMARY KEY (observation_type, identity_key),
    FOREIGN KEY (fingerprint) REFERENCES market_observation_history(fingerprint)
)
"""


class SQLiteMarketObservationRepository(MarketObservationRepository):
    """Append-only observation history with a replaceable latest projection."""

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
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._connection:
            self._connection.execute(_HISTORY_TABLE)
            self._connection.execute(_CURRENT_TABLE)
            self._migrate_external_current_series()
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_observation_history_lookup "
                "ON market_observation_history(observation_type, identity_key, observed_at DESC, sequence_id DESC)"
            )
            self._connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_external_signal_candidate
                ON market_observation_history(json_extract(payload_json, '$.candidate_id'))
                WHERE observation_type = 'external_signal'
                  AND json_extract(payload_json, '$.candidate_id') IS NOT NULL"""
            )
            self._connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_external_signal_verification
                ON market_observation_history(json_extract(payload_json, '$.verification_id'))
                WHERE observation_type = 'external_signal'
                  AND json_extract(payload_json, '$.verification_id') IS NOT NULL"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_market_observation_history_no_update
                BEFORE UPDATE ON market_observation_history
                BEGIN SELECT RAISE(ABORT, 'market observation history is append-only'); END"""
            )
            self._connection.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_market_observation_history_no_delete
                BEFORE DELETE ON market_observation_history
                BEGIN SELECT RAISE(ABORT, 'market observation history is append-only'); END"""
            )

    def save(
        self,
        observation: MarketObservation,
        *,
        _manage_transaction: bool = True,
    ) -> None:
        observation_type = MarketObservationType.from_observation(observation)
        identity_key = self._identity_key(observation.identity)
        current_identity_key = self._current_identity_key(observation, observation_type)
        fingerprint = self._fingerprint(observation, observation_type)
        observed_at = self._observation_time(observation)
        payload = self._payload_json(observation, observation_type)
        observation_id = self._observation_id(observation)
        now = datetime.now(timezone.utc).isoformat()

        try:
            if _manage_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """INSERT INTO market_observation_history (
                observation_id, observation_type, identity_key, fingerprint,
                observed_at, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    observation_id,
                    observation_type.value,
                    identity_key,
                    fingerprint,
                    self._iso(observed_at),
                    payload,
                    now,
                ),
            )
            self._connection.execute(
                """INSERT INTO market_observation_current (
                observation_type, identity_key, observation_id, fingerprint,
                observed_at, payload_json, projected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_type, identity_key) DO UPDATE SET
                    observation_id=excluded.observation_id,
                    fingerprint=excluded.fingerprint,
                    observed_at=excluded.observed_at,
                    payload_json=excluded.payload_json,
                    projected_at=excluded.projected_at
                WHERE excluded.observed_at >= market_observation_current.observed_at""",
                (
                    observation_type.value,
                    current_identity_key,
                    observation_id,
                    fingerprint,
                    self._iso(observed_at),
                    payload,
                    now,
                ),
            )
            if _manage_transaction:
                self._connection.commit()
        except sqlite3.IntegrityError as error:
            if _manage_transaction:
                self._connection.rollback()
            if (
                self._fingerprint_exists(fingerprint)
                or self._observation_id_exists(observation_id)
                or self._external_provenance_exists(observation)
            ):
                raise DuplicateMarketObservationError(fingerprint) from error
            raise
        except Exception:
            if _manage_transaction:
                self._connection.rollback()
            raise

    def get_latest(
        self,
        observation_type: MarketObservationType,
        identity: MarketObservationIdentity,
        *,
        signal_name: str | None = None,
    ) -> MarketObservation | None:
        resolved_type = MarketObservationType(observation_type)
        if signal_name is not None and resolved_type is not MarketObservationType.EXTERNAL_SIGNAL:
            raise ValueError("signal_name is only valid for external signals")
        if resolved_type is MarketObservationType.EXTERNAL_SIGNAL and signal_name is None:
            rows = self._connection.execute(
                "SELECT payload_json FROM market_observation_current "
                "WHERE observation_type = ? ORDER BY observed_at DESC, rowid DESC",
                (resolved_type.value,),
            ).fetchall()
            for row in rows:
                observation = self._from_payload(row["payload_json"])
                if self._identity_key(observation.identity) == self._identity_key(identity):
                    return observation
            return None
        identity_key = (
            self._external_series_key(identity, signal_name)
            if signal_name is not None
            else self._identity_key(identity)
        )
        row = self._connection.execute(
            "SELECT payload_json FROM market_observation_current "
            "WHERE observation_type = ? AND identity_key = ?",
            (resolved_type.value, identity_key),
        ).fetchone()
        return self._from_payload(row["payload_json"]) if row is not None else None

    def get_history(
        self,
        observation_type: MarketObservationType,
        identity: MarketObservationIdentity,
        *,
        limit: int | None = None,
    ) -> tuple[MarketObservation, ...]:
        resolved_type = MarketObservationType(observation_type)
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError("limit must be a positive integer or None")
        query = (
            "SELECT payload_json FROM market_observation_history "
            "WHERE observation_type = ? AND identity_key = ? "
            "ORDER BY observed_at DESC, sequence_id DESC"
        )
        parameters: list[object] = [resolved_type.value, self._identity_key(identity)]
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        rows = self._connection.execute(query, tuple(parameters)).fetchall()
        return tuple(self._from_payload(row["payload_json"]) for row in rows)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _fingerprint_exists(self, fingerprint: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM market_observation_history WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone() is not None

    def _observation_id_exists(self, observation_id: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM market_observation_history WHERE observation_id = ?",
            (observation_id,),
        ).fetchone() is not None

    def _external_provenance_exists(self, observation: MarketObservation) -> bool:
        if not isinstance(observation, ExternalMarketSignal):
            return False
        for field_name, value in (
            ("candidate_id", observation.candidate_id),
            ("verification_id", observation.verification_id),
        ):
            if value is not None and self._connection.execute(
                "SELECT 1 FROM market_observation_history "
                "WHERE observation_type = 'external_signal' "
                f"AND json_extract(payload_json, '$.{field_name}') = ?",
                (value,),
            ).fetchone() is not None:
                return True
        return False

    def _migrate_external_current_series(self) -> None:
        rows = self._connection.execute(
            "SELECT rowid, identity_key, payload_json "
            "FROM market_observation_current WHERE observation_type = 'external_signal'"
        ).fetchall()
        for row in rows:
            observation = self._from_payload(row["payload_json"])
            assert isinstance(observation, ExternalMarketSignal)
            series_key = self._external_series_key(
                observation.identity, observation.signal_name
            )
            if series_key != row["identity_key"]:
                self._connection.execute(
                    "UPDATE market_observation_current SET identity_key = ? WHERE rowid = ?",
                    (series_key, row["rowid"]),
                )

    @classmethod
    def _fingerprint(
        cls,
        observation: MarketObservation,
        observation_type: MarketObservationType,
    ) -> str:
        if isinstance(observation, ExternalMarketSignal):
            provenance = {
                "candidate_id": observation.candidate_id,
                "verification_id": observation.verification_id,
                "signal_name": observation.signal_name,
                "artifact_reference": observation.artifact_reference,
                "evidence": (
                    observation.evidence.source,
                    observation.evidence.reference,
                ),
            }
        else:
            provenance = [
                (name, item.source, item.reference)
                for name, item in sorted(observation.evidence.items())
            ]
        value = {
            "observation_type": observation_type.value,
            "identity": cls._identity_data(observation.identity, include_window=True),
            "provenance": provenance,
            "observed_at": cls._iso(cls._observation_time(observation)),
        }
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()

    @classmethod
    def _identity_key(cls, identity: MarketObservationIdentity) -> str:
        value = cls._canonical_json(cls._identity_data(identity, include_window=False))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _external_series_key(
        cls,
        identity: MarketObservationIdentity,
        signal_name: str,
    ) -> str:
        value = {
            "identity": cls._identity_data(identity, include_window=False),
            "signal_name": signal_name,
        }
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()

    @classmethod
    def _current_identity_key(
        cls,
        observation: MarketObservation,
        observation_type: MarketObservationType,
    ) -> str:
        if observation_type is MarketObservationType.EXTERNAL_SIGNAL:
            assert isinstance(observation, ExternalMarketSignal)
            return cls._external_series_key(observation.identity, observation.signal_name)
        return cls._identity_key(observation.identity)

    @staticmethod
    def _observation_id(observation: MarketObservation) -> str:
        return observation.signal_id if isinstance(observation, ExternalMarketSignal) else observation.observation_id

    @staticmethod
    def _observation_time(observation: MarketObservation) -> datetime:
        return observation.captured_at if isinstance(observation, ExternalMarketSignal) else observation.observed_at

    @classmethod
    def _payload_json(
        cls,
        observation: MarketObservation,
        observation_type: MarketObservationType,
    ) -> str:
        common = {
            "observation_type": observation_type.value,
            "identity": cls._identity_data(observation.identity, include_window=True),
            "schema_version": observation.schema_version,
        }
        if isinstance(observation, ExternalMarketSignal):
            common.update({
                "signal_id": observation.signal_id,
                "source_type": observation.source_type.value,
                "signal_name": observation.signal_name,
                "signal_direction": observation.signal_direction.value,
                "evidence": cls._evidence_data(observation.evidence),
                "captured_at": cls._iso(observation.captured_at),
                "verified_at": cls._iso(observation.verified_at),
                "operator_id": observation.operator_id,
                "artifact_reference": observation.artifact_reference,
                "candidate_id": observation.candidate_id,
                "verification_id": observation.verification_id,
            })
        else:
            common.update({
                "observation_id": observation.observation_id,
                "observed_at": cls._iso(observation.observed_at),
                "evidence": {
                    name: cls._evidence_data(item)
                    for name, item in observation.evidence.items()
                },
            })
        return cls._canonical_json(common)

    @classmethod
    def _from_payload(cls, payload_json: str) -> MarketObservation:
        data = json.loads(payload_json)
        observation_type = MarketObservationType(data["observation_type"])
        identity = cls._identity_from_data(data["identity"])
        if observation_type is MarketObservationType.EXTERNAL_SIGNAL:
            return ExternalMarketSignal(
                signal_id=data["signal_id"],
                identity=identity,
                source_type=ExternalSignalSourceType(data["source_type"]),
                signal_name=data["signal_name"],
                signal_direction=ExternalSignalDirection(data["signal_direction"]),
                evidence=cls._evidence_from_data(data["evidence"]),
                captured_at=cls._datetime(data["captured_at"]),
                verified_at=cls._datetime(data["verified_at"]),
                operator_id=data["operator_id"],
                artifact_reference=data["artifact_reference"],
                candidate_id=data.get("candidate_id"),
                verification_id=data.get("verification_id"),
                schema_version=data["schema_version"],
            )
        observation_class = (
            CompetitionObservation
            if observation_type is MarketObservationType.COMPETITION
            else DemandObservation
        )
        return observation_class(
            observation_id=data["observation_id"],
            identity=identity,
            observed_at=cls._datetime(data["observed_at"]),
            schema_version=data["schema_version"],
            evidence={
                name: cls._evidence_from_data(item)
                for name, item in data["evidence"].items()
            },
        )

    @classmethod
    def _evidence_data(cls, evidence: MarketEvidence) -> dict[str, Any]:
        return {
            "value": cls._encode_value(evidence.value),
            "source": evidence.source,
            "reference": evidence.reference,
            "observed_at": cls._iso(evidence.observed_at),
            "status": evidence.status.value,
            "confidence": str(evidence.confidence),
            "market": evidence.market,
            "marketplace": evidence.marketplace,
            "collection_method": evidence.collection_method,
            "schema_version": evidence.schema_version,
            "keyword": evidence.keyword,
            "category": evidence.category,
            "marketplace_item_id": evidence.marketplace_item_id,
            "canonical_product_id": evidence.canonical_product_id,
            "unit": evidence.unit,
        }

    @classmethod
    def _evidence_from_data(cls, data: Mapping[str, Any]) -> MarketEvidence:
        return MarketEvidence(
            value=cls._decode_value(data["value"]),
            source=data["source"],
            reference=data["reference"],
            observed_at=cls._datetime(data["observed_at"]),
            status=MarketEvidenceStatus(data["status"]),
            confidence=Decimal(data["confidence"]),
            market=data["market"],
            marketplace=data["marketplace"],
            collection_method=data["collection_method"],
            schema_version=data["schema_version"],
            keyword=data["keyword"],
            category=data["category"],
            marketplace_item_id=data["marketplace_item_id"],
            canonical_product_id=data["canonical_product_id"],
            unit=data["unit"],
        )

    @classmethod
    def _identity_data(
        cls,
        identity: MarketObservationIdentity,
        *,
        include_window: bool,
    ) -> dict[str, Any]:
        value = {
            "scope": identity.scope.value,
            "market": identity.market,
            "marketplace": identity.marketplace,
            "canonical_product_id": identity.canonical_product_id,
            "marketplace_item_id": identity.marketplace_item_id,
            "normalized_query": identity.normalized_query,
            "category": identity.category,
            "variant_identity": identity.variant_identity,
            "condition": identity.condition,
        }
        if include_window:
            value["window_started_at"] = cls._iso(identity.window_started_at)
            value["window_ended_at"] = cls._iso(identity.window_ended_at)
        return value

    @classmethod
    def _identity_from_data(cls, data: Mapping[str, Any]) -> MarketObservationIdentity:
        return MarketObservationIdentity(
            scope=MarketObservationScope(data["scope"]),
            market=data["market"],
            marketplace=data["marketplace"],
            canonical_product_id=data["canonical_product_id"],
            marketplace_item_id=data["marketplace_item_id"],
            normalized_query=data["normalized_query"],
            category=data["category"],
            variant_identity=data["variant_identity"],
            condition=data["condition"],
            window_started_at=cls._datetime(data["window_started_at"]),
            window_ended_at=cls._datetime(data["window_ended_at"]),
        )

    @classmethod
    def _encode_value(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return {"kind": "decimal", "value": str(value)}
        if isinstance(value, tuple):
            return {"kind": "tuple", "value": [cls._encode_value(item) for item in value]}
        if isinstance(value, list):
            return {"kind": "list", "value": [cls._encode_value(item) for item in value]}
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("market evidence mapping keys must be text")
            return {
                "kind": "mapping",
                "value": {key: cls._encode_value(item) for key, item in value.items()},
            }
        if value is None or isinstance(value, (str, int, float, bool)):
            return {"kind": "scalar", "value": value}
        raise TypeError("market evidence value is not JSON serializable")

    @classmethod
    def _decode_value(cls, data: Mapping[str, Any]) -> Any:
        kind = data["kind"]
        value = data["value"]
        if kind == "decimal":
            return Decimal(value)
        if kind == "tuple":
            return tuple(cls._decode_value(item) for item in value)
        if kind == "list":
            return [cls._decode_value(item) for item in value]
        if kind == "mapping":
            return {key: cls._decode_value(item) for key, item in value.items()}
        if kind == "scalar":
            return value
        raise ValueError("unsupported market evidence value encoding")

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.astimezone(timezone.utc).isoformat() if value is not None else None

    @staticmethod
    def _datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None
