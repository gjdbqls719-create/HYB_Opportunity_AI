from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.application.ebay_account_deletion import (
    EbayAccountDeletionAuditReceipt,
    EbayAccountDeletionAuthenticityStatus,
    EbayAccountDeletionPendingSubject,
    EbayAccountDeletionProcessingStatus,
    EbayAccountDeletionReceipt,
    EbayAccountDeletionReceiptConflictError,
    EbayAccountDeletionReceiptPersistenceError,
    EbayAccountDeletionReceiptResult,
    EbayAccountDeletionValidationError,
)
from storage.price_history import DEFAULT_DATABASE_PATH


RECEIPT_TABLE = "ebay_account_deletion_receipts"
PENDING_SUBJECT_TABLE = "ebay_account_deletion_pending_subjects"
_LEGACY_SUBJECT_COLUMNS = {"username", "user_id", "eias_token"}


def _canonical_utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("receipt timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("receipt timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("receipt timestamp must include a timezone")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )
    if canonical != value:
        raise ValueError("receipt timestamp is not canonical UTC")
    return canonical


class SQLiteEbayAccountDeletionReceiptRepository:
    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.database_path = Path(database_path)
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_database()
        except (OSError, sqlite3.DatabaseError) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipt storage is unavailable"
            ) from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._migrate_legacy_subject_columns(connection)
            self._create_schema(connection)
            connection.commit()

    @staticmethod
    def _table_columns(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> set[str]:
        return {
            str(row["name"])
            for row in connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
        }

    def _migrate_legacy_subject_columns(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        columns = self._table_columns(connection, RECEIPT_TABLE)
        if not _LEGACY_SUBJECT_COLUMNS.issubset(columns):
            return

        legacy_table = f"{RECEIPT_TABLE}_legacy_subjects"
        if self._table_columns(connection, legacy_table):
            raise sqlite3.DatabaseError(
                "legacy eBay account deletion migration is incomplete"
            )
        connection.execute(
            "DROP TRIGGER IF EXISTS "
            "trg_ebay_account_deletion_receipts_no_update"
        )
        connection.execute(
            "DROP TRIGGER IF EXISTS "
            "trg_ebay_account_deletion_receipts_no_delete"
        )
        connection.execute(
            "DROP INDEX IF EXISTS idx_ebay_account_deletion_processing"
        )
        connection.execute(
            f"ALTER TABLE {RECEIPT_TABLE} RENAME TO {legacy_table}"
        )
        self._create_receipt_table(connection)
        self._create_pending_subject_table(connection)
        connection.execute(
            f"""
            INSERT INTO {RECEIPT_TABLE} (
                notification_id,
                topic,
                schema_version,
                deprecated,
                event_date,
                first_publish_date,
                first_publish_attempt_count,
                semantic_fingerprint,
                authenticity_status,
                processing_status,
                received_at
            )
            SELECT
                notification_id,
                topic,
                schema_version,
                deprecated,
                event_date,
                first_publish_date,
                first_publish_attempt_count,
                semantic_fingerprint,
                authenticity_status,
                processing_status,
                received_at
            FROM {legacy_table}
            """
        )
        connection.execute(
            f"""
            INSERT INTO {PENDING_SUBJECT_TABLE} (
                notification_id,
                username,
                user_id,
                eias_token
            )
            SELECT notification_id, username, user_id, eias_token
            FROM {legacy_table}
            """
        )
        connection.execute(f"DROP TABLE {legacy_table}")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        self._create_receipt_table(connection)
        self._create_pending_subject_table(connection)
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS
                idx_ebay_account_deletion_processing
            ON {RECEIPT_TABLE} (processing_status, received_at)
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS
                trg_ebay_account_deletion_receipts_no_update
            BEFORE UPDATE ON {RECEIPT_TABLE}
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ebay account deletion receipts are append-only'
                );
            END
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS
                trg_ebay_account_deletion_receipts_no_delete
            BEFORE DELETE ON {RECEIPT_TABLE}
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ebay account deletion receipts are append-only'
                );
            END
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS
                trg_ebay_account_deletion_pending_subjects_no_update
            BEFORE UPDATE ON {PENDING_SUBJECT_TABLE}
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'pending ebay deletion subjects may only be purged'
                );
            END
            """
        )

    @staticmethod
    def _create_receipt_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE} (
                notification_id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                deprecated INTEGER NOT NULL CHECK (deprecated = 0),
                event_date TEXT NOT NULL,
                first_publish_date TEXT NOT NULL,
                first_publish_attempt_count INTEGER NOT NULL
                    CHECK (first_publish_attempt_count >= 1),
                semantic_fingerprint TEXT NOT NULL,
                authenticity_status TEXT NOT NULL
                    CHECK (authenticity_status = 'VERIFIED'),
                processing_status TEXT NOT NULL
                    CHECK (processing_status = 'PENDING_DELETION_REVIEW'),
                received_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _create_pending_subject_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PENDING_SUBJECT_TABLE} (
                notification_id TEXT PRIMARY KEY,
                username TEXT,
                user_id TEXT,
                eias_token TEXT,
                CHECK (
                    username IS NOT NULL
                    OR user_id IS NOT NULL
                    OR eias_token IS NOT NULL
                ),
                FOREIGN KEY (notification_id)
                    REFERENCES {RECEIPT_TABLE} (notification_id)
                    ON DELETE RESTRICT
            )
            """
        )

    def record(
        self,
        receipt: EbayAccountDeletionReceipt,
    ) -> EbayAccountDeletionReceiptResult:
        if not isinstance(receipt, EbayAccountDeletionReceipt):
            raise TypeError("receipt must be an EbayAccountDeletionReceipt")

        try:
            audit_receipt = EbayAccountDeletionAuditReceipt.from_receipt(
                receipt
            )
            pending_subject = EbayAccountDeletionPendingSubject.from_notification(
                receipt.notification
            )
        except (
            AttributeError,
            EbayAccountDeletionValidationError,
            TypeError,
            ValueError,
        ) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipt is invalid"
            ) from error
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"""
                    SELECT *
                    FROM {RECEIPT_TABLE}
                    WHERE notification_id = ?
                    """,
                    (audit_receipt.notification_id,),
                ).fetchone()
                if row is not None:
                    existing_audit = self._row_to_audit_receipt(row)
                    if existing_audit.semantic_fingerprint != (
                        audit_receipt.semantic_fingerprint
                    ):
                        raise EbayAccountDeletionReceiptConflictError(
                            "notification ID already has different semantic data"
                        )
                    subject_row = connection.execute(
                        f"""
                        SELECT *
                        FROM {PENDING_SUBJECT_TABLE}
                        WHERE notification_id = ?
                        """,
                        (receipt.notification.notification_id,),
                    ).fetchone()
                    replay_subject = (
                        pending_subject
                        if subject_row is None
                        else self._row_to_pending_subject(subject_row)
                    )
                    existing = existing_audit.reconstruct(replay_subject)
                    connection.commit()
                    return EbayAccountDeletionReceiptResult(
                        receipt=existing,
                        replayed=True,
                    )

                connection.execute(
                    f"""
                    INSERT INTO {RECEIPT_TABLE} (
                        notification_id,
                        topic,
                        schema_version,
                        deprecated,
                        event_date,
                        first_publish_date,
                        first_publish_attempt_count,
                        semantic_fingerprint,
                        authenticity_status,
                        processing_status,
                        received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audit_receipt.notification_id,
                        audit_receipt.topic,
                        audit_receipt.schema_version,
                        int(audit_receipt.deprecated),
                        audit_receipt.event_date,
                        audit_receipt.first_publish_date,
                        audit_receipt.first_publish_attempt_count,
                        audit_receipt.semantic_fingerprint,
                        audit_receipt.authenticity_status.value,
                        audit_receipt.processing_status.value,
                        audit_receipt.received_at,
                    ),
                )
                connection.execute(
                    f"""
                    INSERT INTO {PENDING_SUBJECT_TABLE} (
                        notification_id,
                        username,
                        user_id,
                        eias_token
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        pending_subject.notification_id,
                        pending_subject.username,
                        pending_subject.user_id,
                        pending_subject.eias_token,
                    ),
                )
                connection.commit()
        except EbayAccountDeletionReceiptConflictError:
            raise
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipt could not be persisted"
            ) from error

        return EbayAccountDeletionReceiptResult(
            receipt=receipt,
            replayed=False,
        )

    def get(
        self,
        notification_id: str,
    ) -> EbayAccountDeletionReceipt | None:
        try:
            with self._connect() as connection:
                receipt_row = connection.execute(
                    f"SELECT * FROM {RECEIPT_TABLE} WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()
                subject_row = connection.execute(
                    f"""
                    SELECT * FROM {PENDING_SUBJECT_TABLE}
                    WHERE notification_id = ?
                    """,
                    (notification_id,),
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipt could not be read"
            ) from error
        if receipt_row is None or subject_row is None:
            return None
        try:
            return self._row_to_audit_receipt(receipt_row).reconstruct(
                self._row_to_pending_subject(subject_row)
            )
        except (EbayAccountDeletionValidationError, TypeError, ValueError) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "stored eBay account deletion receipt is invalid"
            ) from error

    def get_audit_receipt(
        self,
        notification_id: str,
    ) -> EbayAccountDeletionAuditReceipt | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT * FROM {RECEIPT_TABLE} WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion audit receipt could not be read"
            ) from error
        return None if row is None else self._row_to_audit_receipt(row)

    def get_pending_subject(
        self,
        notification_id: str,
    ) -> EbayAccountDeletionPendingSubject | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT * FROM {PENDING_SUBJECT_TABLE}
                    WHERE notification_id = ?
                    """,
                    (notification_id,),
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion pending subject could not be read"
            ) from error
        return None if row is None else self._row_to_pending_subject(row)

    def purge_pending_subject(self, notification_id: str) -> bool:
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification_id must be non-empty text")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    DELETE FROM {PENDING_SUBJECT_TABLE}
                    WHERE notification_id = ?
                    """,
                    (notification_id.strip(),),
                )
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion pending subject could not be purged"
            ) from error
        return cursor.rowcount == 1

    def count(self) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) AS receipt_count FROM {RECEIPT_TABLE}"
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipts could not be counted"
            ) from error
        return 0 if row is None else int(row["receipt_count"])

    def pending_subject_count(self) -> int:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) AS subject_count FROM {PENDING_SUBJECT_TABLE}"
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion pending subjects could not be counted"
            ) from error
        return 0 if row is None else int(row["subject_count"])

    @staticmethod
    def _row_to_audit_receipt(
        row: sqlite3.Row,
    ) -> EbayAccountDeletionAuditReceipt:
        try:
            return EbayAccountDeletionAuditReceipt.create(
                notification_id=str(row["notification_id"]),
                topic=str(row["topic"]),
                schema_version=str(row["schema_version"]),
                deprecated=bool(row["deprecated"]),
                event_date=str(row["event_date"]),
                first_publish_date=str(row["first_publish_date"]),
                first_publish_attempt_count=int(
                    row["first_publish_attempt_count"]
                ),
                semantic_fingerprint=str(row["semantic_fingerprint"]),
                authenticity_status=EbayAccountDeletionAuthenticityStatus(
                    str(row["authenticity_status"])
                ),
                processing_status=EbayAccountDeletionProcessingStatus(
                    str(row["processing_status"])
                ),
                received_at=_canonical_utc_timestamp(row["received_at"]),
            )
        except (
            EbayAccountDeletionValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "stored eBay account deletion audit receipt is invalid"
            ) from error

    @staticmethod
    def _row_to_pending_subject(
        row: sqlite3.Row,
    ) -> EbayAccountDeletionPendingSubject:
        try:
            return EbayAccountDeletionPendingSubject.create(
                notification_id=str(row["notification_id"]),
                username=(
                    None if row["username"] is None else str(row["username"])
                ),
                user_id=(
                    None if row["user_id"] is None else str(row["user_id"])
                ),
                eias_token=(
                    None
                    if row["eias_token"] is None
                    else str(row["eias_token"])
                ),
            )
        except (
            EbayAccountDeletionValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "stored eBay account deletion pending subject is invalid"
            ) from error


__all__ = [
    "PENDING_SUBJECT_TABLE",
    "RECEIPT_TABLE",
    "SQLiteEbayAccountDeletionReceiptRepository",
]
