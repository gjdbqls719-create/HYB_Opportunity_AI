"""Append-only SQLite persistence for collected observations and finalized groups."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.application.discovery_persistence import (
    DiscoveryExecutionIdentityConflictError,
    DiscoveryExecutionNotFoundError,
    DiscoveryGroupCommitError,
    DiscoveryGroupConflictError,
    DiscoveryGroupHistoryError,
    DiscoveryGroupMembershipError,
    DiscoveryGroupMembershipPersistenceError,
    DiscoveryObservationCommitError,
    DiscoveryObservationConflictError,
    DiscoveryObservationHistoryError,
    MalformedDiscoveryGroupPersistenceError,
    MalformedDiscoveryObservationPersistenceError,
    UnsupportedDiscoveryGroupVersionError,
    UnsupportedDiscoveryObservationVersionError,
)
from app.domain.discovery_identity import (
    COLLECTOR_OBSERVATION_SCHEMA_VERSION,
    FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION,
    CollectedProductObservation,
    FinalizedProductGroup,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.product_observation import CollectorProvenance, ObservedProductSnapshot
from app.models import ProductDataSource


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _product_payload(product: ObservedProductSnapshot) -> dict[str, object]:
    return {
        "marketplace": product.marketplace,
        "item_id": product.item_id,
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "condition": product.condition,
        "url": product.url,
        "brand": product.brand,
        "model_number": product.model_number,
        "category": product.category,
        "shipping_cost": product.shipping_cost,
        "seller": product.seller,
        "image_url": product.image_url,
        "rating": product.rating,
        "review_count": product.review_count,
        "in_stock": product.in_stock,
        "data_source": product.data_source.value,
        "shipping_cost_known": product.shipping_cost_known,
    }


def _identity_payload(identity: MarketObservationIdentity | None) -> dict[str, object] | None:
    if identity is None:
        return None
    return {
        "scope": identity.scope.value,
        "market": identity.market,
        "marketplace": identity.marketplace,
        "canonical_product_id": identity.canonical_product_id,
        "marketplace_item_id": identity.marketplace_item_id,
        "normalized_query": identity.normalized_query,
        "category": identity.category,
        "variant_identity": identity.variant_identity,
        "condition": identity.condition,
        "window_started_at": identity.window_started_at.isoformat(),
        "window_ended_at": identity.window_ended_at.isoformat(),
    }


def _observation_payload(observation: CollectedProductObservation) -> str:
    return _json(
        {
            "observation_id": observation.observation_id,
            "discovery_execution_id": observation.discovery_execution_id,
            "source_marketplace": observation.source_marketplace,
            "source_item_id": observation.source_item_id,
            "product": _product_payload(observation.product),
            "collector_provenance": {
                "collector_name": observation.collector_provenance.collector_name,
                "collector_version": observation.collector_provenance.collector_version,
                "source_reference": observation.collector_provenance.source_reference,
            },
            "observed_at": observation.observed_at.isoformat(),
            "candidate_market_identity": _identity_payload(
                observation.candidate_market_identity
            ),
            "schema_version": observation.schema_version,
        }
    )


def _market_identity(value: object) -> MarketObservationIdentity | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("candidate market identity must be an object")
    return MarketObservationIdentity(
        scope=MarketObservationScope(value["scope"]),
        market=value["market"],
        marketplace=value["marketplace"],
        canonical_product_id=value["canonical_product_id"],
        marketplace_item_id=value["marketplace_item_id"],
        normalized_query=value["normalized_query"],
        category=value["category"],
        variant_identity=value["variant_identity"],
        condition=value["condition"],
        window_started_at=_aware(value["window_started_at"], "window_started_at"),
        window_ended_at=_aware(value["window_ended_at"], "window_ended_at"),
    )


class _SQLiteDiscoveryFacts:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if database_path is None and connection is None:
            raise ValueError("database_path or connection is required")
        if database_path is not None and connection is not None:
            raise ValueError("database_path and connection are mutually exclusive")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS discovery_collected_observation_history (
                    observation_id TEXT PRIMARY KEY,
                    discovery_execution_id TEXT NOT NULL,
                    source_marketplace TEXT NOT NULL,
                    source_item_id TEXT NOT NULL,
                    observation_payload_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    observation_schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(discovery_execution_id)
                        REFERENCES discovery_command_history(execution_id)
                )"""
            )
            self._connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_discovery_observation_execution
                ON discovery_collected_observation_history(
                    discovery_execution_id, observed_at, observation_id
                )"""
            )
            self._connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_discovery_observation_source
                ON discovery_collected_observation_history(
                    source_marketplace, source_item_id, observed_at, observation_id
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS discovery_finalized_group_history (
                    finalized_group_id TEXT PRIMARY KEY,
                    discovery_execution_id TEXT NOT NULL,
                    ordered_observation_ids_json TEXT NOT NULL,
                    grouping_policy_version TEXT NOT NULL,
                    representative_observation_id TEXT NOT NULL,
                    finalized_at TEXT NOT NULL,
                    membership_fingerprint TEXT NOT NULL,
                    group_schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(discovery_execution_id)
                        REFERENCES discovery_command_history(execution_id)
                )"""
            )
            self._connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_discovery_group_execution
                ON discovery_finalized_group_history(
                    discovery_execution_id, finalized_at, finalized_group_id
                )"""
            )
            self._connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_discovery_group_membership
                ON discovery_finalized_group_history(
                    membership_fingerprint, finalized_at, finalized_group_id
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS discovery_finalized_group_members (
                    finalized_group_id TEXT NOT NULL,
                    position INTEGER NOT NULL CHECK(position >= 0),
                    observation_id TEXT NOT NULL,
                    PRIMARY KEY(finalized_group_id, position),
                    UNIQUE(finalized_group_id, observation_id),
                    FOREIGN KEY(finalized_group_id)
                        REFERENCES discovery_finalized_group_history(finalized_group_id),
                    FOREIGN KEY(observation_id)
                        REFERENCES discovery_collected_observation_history(observation_id)
                )"""
            )
            for table in (
                "discovery_collected_observation_history",
                "discovery_finalized_group_history",
                "discovery_finalized_group_members",
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"""
                    )

    def _execution_exists(self, execution_id: str) -> bool:
        try:
            return self._connection.execute(
                "SELECT 1 FROM discovery_command_history WHERE execution_id = ?",
                (execution_id,),
            ).fetchone() is not None
        except sqlite3.Error as error:
            raise DiscoveryExecutionNotFoundError(
                "discovery command execution is unavailable"
            ) from error

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class SQLiteDiscoveryObservationRepository(_SQLiteDiscoveryFacts):
    def save_observation(
        self, observation: CollectedProductObservation
    ) -> CollectedProductObservation:
        if not isinstance(observation, CollectedProductObservation):
            raise TypeError("observation must be CollectedProductObservation")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise DiscoveryObservationCommitError(
                "observation transaction could not start"
            ) from error
        try:
            existing = self._get_observation(observation.observation_id)
            if existing is not None:
                if existing != observation:
                    raise DiscoveryObservationConflictError(
                        "observation ID conflicts with persisted payload"
                    )
                self._rollback()
                return existing
            if not self._execution_exists(observation.discovery_execution_id):
                raise DiscoveryExecutionNotFoundError(
                    "observation execution has no committed command"
                )
            try:
                self._insert_observation(observation)
            except sqlite3.Error as error:
                raise DiscoveryObservationHistoryError(
                    "observation history insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DiscoveryObservationCommitError(
                    "observation transaction commit failed"
                ) from error
            return observation
        except Exception:
            self._rollback()
            raise

    def _insert_observation(self, observation: CollectedProductObservation) -> None:
        self._connection.execute(
            """INSERT INTO discovery_collected_observation_history (
                observation_id, discovery_execution_id, source_marketplace,
                source_item_id, observation_payload_json, observed_at,
                observation_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                observation.observation_id,
                observation.discovery_execution_id,
                observation.source_marketplace,
                observation.source_item_id,
                _observation_payload(observation),
                observation.observed_at.isoformat(),
                observation.schema_version,
                observation.observed_at.astimezone(timezone.utc).isoformat(),
            ),
        )

    def _commit(self) -> None:
        self._connection.commit()

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> CollectedProductObservation:
        if row["observation_schema_version"] != COLLECTOR_OBSERVATION_SCHEMA_VERSION:
            raise UnsupportedDiscoveryObservationVersionError(
                f"unsupported observation version: {row['observation_schema_version']}"
            )
        try:
            value = json.loads(row["observation_payload_json"])
            product = value["product"]
            provenance = value["collector_provenance"]
            observation = CollectedProductObservation(
                observation_id=value["observation_id"],
                discovery_execution_id=value["discovery_execution_id"],
                source_marketplace=value["source_marketplace"],
                source_item_id=value["source_item_id"],
                product=ObservedProductSnapshot(
                    marketplace=product["marketplace"], item_id=product["item_id"],
                    title=product["title"], price=product["price"],
                    currency=product["currency"], condition=product["condition"],
                    url=product["url"], brand=product["brand"],
                    model_number=product["model_number"], category=product["category"],
                    shipping_cost=product["shipping_cost"], seller=product["seller"],
                    image_url=product["image_url"], rating=product["rating"],
                    review_count=product["review_count"], in_stock=product["in_stock"],
                    data_source=ProductDataSource(product["data_source"]),
                    shipping_cost_known=product["shipping_cost_known"],
                ),
                collector_provenance=CollectorProvenance(
                    collector_name=provenance["collector_name"],
                    collector_version=provenance["collector_version"],
                    source_reference=provenance["source_reference"],
                ),
                observed_at=_aware(value["observed_at"], "observed_at"),
                candidate_market_identity=_market_identity(
                    value["candidate_market_identity"]
                ),
                schema_version=value["schema_version"],
            )
            if (
                observation.observation_id != row["observation_id"]
                or observation.discovery_execution_id != row["discovery_execution_id"]
                or observation.source_marketplace != row["source_marketplace"]
                or observation.source_item_id != row["source_item_id"]
                or observation.observed_at.isoformat() != row["observed_at"]
                or observation.schema_version != row["observation_schema_version"]
                or _observation_payload(observation) != row["observation_payload_json"]
            ):
                raise ValueError("observation columns and payload disagree")
            return observation
        except UnsupportedDiscoveryObservationVersionError:
            raise
        except Exception as error:
            raise MalformedDiscoveryObservationPersistenceError(
                "malformed persisted collected observation"
            ) from error

    def _get_observation(self, observation_id: str) -> CollectedProductObservation | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM discovery_collected_observation_history WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryObservationHistoryError("observation query failed") from error
        return None if row is None else self._from_row(row)

    def get_observation(self, observation_id: str) -> CollectedProductObservation | None:
        return self._get_observation(_required(observation_id, "observation_id"))

    def get_by_execution(
        self, discovery_execution_id: str
    ) -> tuple[CollectedProductObservation, ...]:
        try:
            rows = self._connection.execute(
                """SELECT * FROM discovery_collected_observation_history
                WHERE discovery_execution_id = ? ORDER BY observed_at, observation_id""",
                (_required(discovery_execution_id, "discovery_execution_id"),),
            ).fetchall()
        except sqlite3.Error as error:
            raise DiscoveryObservationHistoryError("observation query failed") from error
        return tuple(self._from_row(row) for row in rows)

    def get_by_source_listing(
        self, source_marketplace: str, source_item_id: str
    ) -> tuple[CollectedProductObservation, ...]:
        try:
            rows = self._connection.execute(
                """SELECT * FROM discovery_collected_observation_history
                WHERE source_marketplace = ? AND source_item_id = ?
                ORDER BY observed_at, observation_id""",
                (
                    _required(source_marketplace, "source_marketplace"),
                    _required(source_item_id, "source_item_id"),
                ),
            ).fetchall()
        except sqlite3.Error as error:
            raise DiscoveryObservationHistoryError("observation query failed") from error
        return tuple(self._from_row(row) for row in rows)


class SQLiteDiscoveryGroupRepository(_SQLiteDiscoveryFacts):
    def save_group(self, group: FinalizedProductGroup) -> FinalizedProductGroup:
        if not isinstance(group, FinalizedProductGroup):
            raise TypeError("group must be FinalizedProductGroup")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise DiscoveryGroupCommitError("group transaction could not start") from error
        try:
            existing = self._get_group(group.finalized_group_id)
            if existing is not None:
                if existing != group:
                    raise DiscoveryGroupConflictError(
                        "finalized group ID conflicts with persisted payload"
                    )
                self._rollback()
                return existing
            if not self._execution_exists(group.discovery_execution_id):
                raise DiscoveryExecutionNotFoundError(
                    "group execution has no committed command"
                )
            observations = self._load_member_observations(group.observation_ids)
            if len(observations) != len(group.observation_ids):
                raise DiscoveryGroupMembershipError(
                    "all finalized group observations must be persisted"
                )
            if any(
                observation.discovery_execution_id != group.discovery_execution_id
                for observation in observations
            ):
                raise DiscoveryExecutionIdentityConflictError(
                    "group and member observations must share one execution"
                )
            try:
                self._insert_group(group)
            except sqlite3.Error as error:
                raise DiscoveryGroupHistoryError("group history insert failed") from error
            try:
                self._insert_members(group)
            except sqlite3.Error as error:
                raise DiscoveryGroupMembershipPersistenceError(
                    "group membership insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DiscoveryGroupCommitError("group transaction commit failed") from error
            return group
        except Exception:
            self._rollback()
            raise

    def _load_member_observations(
        self, observation_ids: tuple[str, ...]
    ) -> tuple[CollectedProductObservation, ...]:
        result = []
        for observation_id in observation_ids:
            try:
                row = self._connection.execute(
                    "SELECT * FROM discovery_collected_observation_history WHERE observation_id = ?",
                    (observation_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise DiscoveryGroupMembershipPersistenceError(
                    "group membership query failed"
                ) from error
            if row is not None:
                result.append(SQLiteDiscoveryObservationRepository._from_row(row))
        return tuple(result)

    def _insert_group(self, group: FinalizedProductGroup) -> None:
        self._connection.execute(
            """INSERT INTO discovery_finalized_group_history (
                finalized_group_id, discovery_execution_id,
                ordered_observation_ids_json, grouping_policy_version,
                representative_observation_id, finalized_at,
                membership_fingerprint, group_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                group.finalized_group_id, group.discovery_execution_id,
                _json(list(group.observation_ids)), group.grouping_policy_version,
                group.representative_observation_id, group.finalized_at.isoformat(),
                group.membership_fingerprint, group.schema_version,
                group.finalized_at.astimezone(timezone.utc).isoformat(),
            ),
        )

    def _insert_members(self, group: FinalizedProductGroup) -> None:
        self._connection.executemany(
            """INSERT INTO discovery_finalized_group_members (
                finalized_group_id, position, observation_id
            ) VALUES (?, ?, ?)""",
            tuple(
                (group.finalized_group_id, position, observation_id)
                for position, observation_id in enumerate(group.observation_ids)
            ),
        )

    def _commit(self) -> None:
        self._connection.commit()

    def _from_row(self, row: sqlite3.Row) -> FinalizedProductGroup:
        if row["group_schema_version"] != FINALIZED_PRODUCT_GROUP_SCHEMA_VERSION:
            raise UnsupportedDiscoveryGroupVersionError(
                f"unsupported group version: {row['group_schema_version']}"
            )
        try:
            member_rows = self._connection.execute(
                """SELECT position, observation_id FROM discovery_finalized_group_members
                WHERE finalized_group_id = ? ORDER BY position""",
                (row["finalized_group_id"],),
            ).fetchall()
            positions = tuple(member["position"] for member in member_rows)
            if positions != tuple(range(len(member_rows))):
                raise ValueError("group membership positions must be contiguous")
            observation_ids = tuple(member["observation_id"] for member in member_rows)
            stored_ids = json.loads(row["ordered_observation_ids_json"])
            if not isinstance(stored_ids, list) or tuple(stored_ids) != observation_ids:
                raise ValueError("group membership representations disagree")
            group = FinalizedProductGroup(
                finalized_group_id=row["finalized_group_id"],
                discovery_execution_id=row["discovery_execution_id"],
                observation_ids=observation_ids,
                grouping_policy_version=row["grouping_policy_version"],
                representative_observation_id=row["representative_observation_id"],
                finalized_at=_aware(row["finalized_at"], "finalized_at"),
                schema_version=row["group_schema_version"],
            )
            if group.membership_fingerprint != row["membership_fingerprint"]:
                raise ValueError("group membership fingerprint mismatch")
            member_observations = self._load_member_observations(group.observation_ids)
            if len(member_observations) != len(group.observation_ids):
                raise ValueError("group references missing observations")
            if any(
                value.discovery_execution_id != group.discovery_execution_id
                for value in member_observations
            ):
                raise ValueError("group member execution mismatch")
            return group
        except UnsupportedDiscoveryGroupVersionError:
            raise
        except sqlite3.Error as error:
            raise DiscoveryGroupMembershipPersistenceError(
                "group membership query failed"
            ) from error
        except Exception as error:
            raise MalformedDiscoveryGroupPersistenceError(
                "malformed persisted finalized group"
            ) from error

    def _get_group(self, finalized_group_id: str) -> FinalizedProductGroup | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM discovery_finalized_group_history WHERE finalized_group_id = ?",
                (finalized_group_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryGroupHistoryError("finalized group query failed") from error
        return None if row is None else self._from_row(row)

    def get_group(self, finalized_group_id: str) -> FinalizedProductGroup | None:
        return self._get_group(_required(finalized_group_id, "finalized_group_id"))

    def _query(self, where: str, value: str) -> tuple[FinalizedProductGroup, ...]:
        try:
            rows = self._connection.execute(
                f"""SELECT * FROM discovery_finalized_group_history WHERE {where} = ?
                ORDER BY finalized_at, finalized_group_id""",
                (value,),
            ).fetchall()
        except sqlite3.Error as error:
            raise DiscoveryGroupHistoryError("finalized group query failed") from error
        return tuple(self._from_row(row) for row in rows)

    def get_by_execution(
        self, discovery_execution_id: str
    ) -> tuple[FinalizedProductGroup, ...]:
        return self._query(
            "discovery_execution_id",
            _required(discovery_execution_id, "discovery_execution_id"),
        )

    def get_by_membership_fingerprint(
        self, membership_fingerprint: str
    ) -> tuple[FinalizedProductGroup, ...]:
        return self._query(
            "membership_fingerprint",
            _required(membership_fingerprint, "membership_fingerprint"),
        )
