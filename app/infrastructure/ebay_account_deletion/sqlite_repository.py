from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.application.ebay_account_deletion import (
    EbayAccountDeletionAuthenticityStatus,
    EbayAccountDeletionNotification,
    EbayAccountDeletionProcessingStatus,
    EbayAccountDeletionReceipt,
    EbayAccountDeletionReceiptConflictError,
    EbayAccountDeletionReceiptPersistenceError,
    EbayAccountDeletionReceiptResult,
)
from storage.price_history import DEFAULT_DATABASE_PATH


RECEIPT_TABLE = "ebay_account_deletion_receipts"


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
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
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
                    username TEXT,
                    user_id TEXT,
                    eias_token TEXT,
                    semantic_fingerprint TEXT NOT NULL,
                    authenticity_status TEXT NOT NULL
                        CHECK (authenticity_status = 'VERIFIED'),
                    processing_status TEXT NOT NULL
                        CHECK (
                            processing_status = 'PENDING_DELETION_REVIEW'
                        ),
                    received_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS
                    idx_ebay_account_deletion_processing
                ON {RECEIPT_TABLE} (processing_status, received_at);

                CREATE TRIGGER IF NOT EXISTS
                    trg_ebay_account_deletion_receipts_no_update
                BEFORE UPDATE ON {RECEIPT_TABLE}
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'ebay account deletion receipts are append-only'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                    trg_ebay_account_deletion_receipts_no_delete
                BEFORE DELETE ON {RECEIPT_TABLE}
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'ebay account deletion receipts are append-only'
                    );
                END;
                """
            )
            connection.commit()

    def record(
        self,
        receipt: EbayAccountDeletionReceipt,
    ) -> EbayAccountDeletionReceiptResult:
        if not isinstance(receipt, EbayAccountDeletionReceipt):
            raise TypeError("receipt must be an EbayAccountDeletionReceipt")

        notification = receipt.notification
        try:
            if (
                receipt.semantic_fingerprint
                != notification.semantic_fingerprint
            ):
                raise ValueError("receipt fingerprint mismatch")
            if receipt.authenticity_status != (
                EbayAccountDeletionAuthenticityStatus.VERIFIED
            ):
                raise ValueError("receipt authenticity status is invalid")
            if receipt.processing_status != (
                EbayAccountDeletionProcessingStatus.PENDING_DELETION_REVIEW
            ):
                raise ValueError("receipt processing status is invalid")
            received_at = _canonical_utc_timestamp(receipt.received_at)
        except (AttributeError, ValueError) as error:
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
                    (notification.notification_id,),
                ).fetchone()
                if row is not None:
                    existing = self._row_to_receipt(row)
                    if (
                        existing.semantic_fingerprint
                        != receipt.semantic_fingerprint
                    ):
                        raise EbayAccountDeletionReceiptConflictError(
                            "notification ID already has different semantic data"
                        )
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
                        username,
                        user_id,
                        eias_token,
                        semantic_fingerprint,
                        authenticity_status,
                        processing_status,
                        received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notification.notification_id,
                        notification.topic,
                        notification.schema_version,
                        int(notification.deprecated),
                        notification.event_date,
                        notification.publish_date,
                        notification.publish_attempt_count,
                        notification.username,
                        notification.user_id,
                        notification.eias_token,
                        receipt.semantic_fingerprint,
                        receipt.authenticity_status.value,
                        receipt.processing_status.value,
                        received_at,
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
                row = connection.execute(
                    f"SELECT * FROM {RECEIPT_TABLE} WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "eBay account deletion receipt could not be read"
            ) from error
        return None if row is None else self._row_to_receipt(row)

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

    @staticmethod
    def _row_to_receipt(row: sqlite3.Row) -> EbayAccountDeletionReceipt:
        try:
            notification = EbayAccountDeletionNotification.create(
                notification_id=str(row["notification_id"]),
                topic=str(row["topic"]),
                schema_version=str(row["schema_version"]),
                deprecated=bool(row["deprecated"]),
                event_date=str(row["event_date"]),
                publish_date=str(row["first_publish_date"]),
                publish_attempt_count=int(row["first_publish_attempt_count"]),
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
            fingerprint = str(row["semantic_fingerprint"])
            if fingerprint != notification.semantic_fingerprint:
                raise ValueError("receipt fingerprint mismatch")
            return EbayAccountDeletionReceipt(
                notification=notification,
                semantic_fingerprint=fingerprint,
                authenticity_status=EbayAccountDeletionAuthenticityStatus(
                    str(row["authenticity_status"])
                ),
                processing_status=EbayAccountDeletionProcessingStatus(
                    str(row["processing_status"])
                ),
                received_at=_canonical_utc_timestamp(row["received_at"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EbayAccountDeletionReceiptPersistenceError(
                "stored eBay account deletion receipt is invalid"
            ) from error


__all__ = [
    "RECEIPT_TABLE",
    "SQLiteEbayAccountDeletionReceiptRepository",
]
