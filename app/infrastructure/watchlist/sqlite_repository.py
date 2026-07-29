from __future__ import annotations

import sqlite3
from pathlib import Path

from app.application.watchlist import (
    WatchListRepository,
)
from app.domain.watchlist import (
    DuplicateWatchItemError,
    WatchItem,
    WatchItemStatus,
)
from app.infrastructure.watchlist.mapper import (
    watch_item_from_row,
    watch_item_to_record,
)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS watch_items (
    watch_id TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,

    marketplace TEXT NOT NULL,
    item_id TEXT NOT NULL,
    canonical_product_id TEXT,

    title TEXT NOT NULL,
    current_price REAL NOT NULL,
    currency TEXT NOT NULL,

    url TEXT NOT NULL DEFAULT '',
    brand TEXT,
    model_number TEXT,

    target_roi REAL,
    target_net_profit REAL,
    note TEXT NOT NULL DEFAULT '',

    status TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_analyzed_at TEXT,

    CHECK (current_price >= 0),
    CHECK (
        target_roi IS NULL
        OR target_roi >= 0
    ),
    CHECK (
        target_net_profit IS NULL
        OR target_net_profit >= 0
    ),
    CHECK (
        status IN ('watching', 'archived')
    )
)
"""


_CREATE_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
    idx_watch_items_status_created_at
ON watch_items (
    status,
    created_at,
    watch_id
)
"""


_CREATE_MARKETPLACE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
    idx_watch_items_marketplace_item
ON watch_items (
    marketplace,
    item_id
)
"""


_CREATE_UPDATED_AT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS
    idx_watch_items_updated_at
ON watch_items (
    updated_at
)
"""


_SAVE_SQL = """
INSERT INTO watch_items (
    watch_id,
    identity_key,
    marketplace,
    item_id,
    canonical_product_id,
    title,
    current_price,
    currency,
    url,
    brand,
    model_number,
    target_roi,
    target_net_profit,
    note,
    status,
    created_at,
    updated_at,
    last_analyzed_at
)
VALUES (
    :watch_id,
    :identity_key,
    :marketplace,
    :item_id,
    :canonical_product_id,
    :title,
    :current_price,
    :currency,
    :url,
    :brand,
    :model_number,
    :target_roi,
    :target_net_profit,
    :note,
    :status,
    :created_at,
    :updated_at,
    :last_analyzed_at
)
ON CONFLICT(watch_id)
DO UPDATE SET
    identity_key = excluded.identity_key,
    marketplace = excluded.marketplace,
    item_id = excluded.item_id,
    canonical_product_id = excluded.canonical_product_id,
    title = excluded.title,
    current_price = excluded.current_price,
    currency = excluded.currency,
    url = excluded.url,
    brand = excluded.brand,
    model_number = excluded.model_number,
    target_roi = excluded.target_roi,
    target_net_profit = excluded.target_net_profit,
    note = excluded.note,
    status = excluded.status,
    created_at = excluded.created_at,
    updated_at = excluded.updated_at,
    last_analyzed_at = excluded.last_analyzed_at
"""


class SQLiteWatchListRepository(
    WatchListRepository
):
    """
    SQLite 기반 WatchListRepository 구현체.

    Repository는 WatchItem을 저장하고 복원하는 책임만 가진다.
    archive, restore, 목표 변경 같은 비즈니스 상태 전환은
    WatchItem Domain Model에서 수행한다.
    """

    def __init__(
        self,
        database_path: str | Path = (
            "data/hyb_opportunity.db"
        ),
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._owns_connection = connection is None
        self._closed = False

        if connection is not None:
            self._connection = connection
        else:
            resolved_path = str(database_path)

            if resolved_path != ":memory:":
                path = Path(resolved_path)
                path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            self._connection = sqlite3.connect(
                resolved_path,
            )

        self._connection.row_factory = sqlite3.Row

        self._connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        self._initialize_schema()

    def save(
        self,
        item: WatchItem,
    ) -> None:
        """
        Watch Item을 신규 저장하거나 watch_id 기준으로 갱신한다.

        다른 watch_id가 동일한 identity_key를 이미 사용한다면
        DuplicateWatchItemError를 발생시킨다.
        """
        self._ensure_open()

        if not isinstance(item, WatchItem):
            raise TypeError(
                "item은 WatchItem이어야 합니다."
            )

        record = watch_item_to_record(item)

        try:
            with self._connection:
                self._connection.execute(
                    _SAVE_SQL,
                    record,
                )
        except sqlite3.IntegrityError as error:
            if self._is_identity_conflict(error):
                raise DuplicateWatchItemError(
                    "동일한 상품 Identity가 이미 "
                    "Watch List에 저장되어 있습니다: "
                    f"{item.identity_key}"
                ) from error

            raise

    def get(
        self,
        watch_id: str,
    ) -> WatchItem | None:
        self._ensure_open()
        cleaned_watch_id = self._clean_required_text(
            watch_id,
            field_name="watch_id",
        )

        row = self._connection.execute(
            """
            SELECT *
            FROM watch_items
            WHERE watch_id = ?
            """,
            (cleaned_watch_id,),
        ).fetchone()

        if row is None:
            return None

        return watch_item_from_row(row)

    def find_by_identity(
        self,
        identity_key: str,
    ) -> WatchItem | None:
        self._ensure_open()
        cleaned_identity_key = (
            self._clean_required_text(
                identity_key,
                field_name="identity_key",
            )
        )

        row = self._connection.execute(
            """
            SELECT *
            FROM watch_items
            WHERE identity_key = ?
            """,
            (cleaned_identity_key,),
        ).fetchone()

        if row is None:
            return None

        return watch_item_from_row(row)

    def list_all(
        self,
    ) -> tuple[WatchItem, ...]:
        self._ensure_open()

        rows = self._connection.execute(
            """
            SELECT *
            FROM watch_items
            ORDER BY
                created_at ASC,
                watch_id ASC
            """
        ).fetchall()

        return tuple(
            watch_item_from_row(row)
            for row in rows
        )

    def list_watching(
        self,
    ) -> tuple[WatchItem, ...]:
        return self._list_by_status(
            WatchItemStatus.WATCHING
        )

    def list_archived(
        self,
    ) -> tuple[WatchItem, ...]:
        return self._list_by_status(
            WatchItemStatus.ARCHIVED
        )

    def exists(
        self,
        watch_id: str,
    ) -> bool:
        self._ensure_open()
        cleaned_watch_id = self._clean_required_text(
            watch_id,
            field_name="watch_id",
        )

        row = self._connection.execute(
            """
            SELECT 1
            FROM watch_items
            WHERE watch_id = ?
            LIMIT 1
            """,
            (cleaned_watch_id,),
        ).fetchone()

        return row is not None

    def exists_identity(
        self,
        identity_key: str,
    ) -> bool:
        self._ensure_open()
        cleaned_identity_key = (
            self._clean_required_text(
                identity_key,
                field_name="identity_key",
            )
        )

        row = self._connection.execute(
            """
            SELECT 1
            FROM watch_items
            WHERE identity_key = ?
            LIMIT 1
            """,
            (cleaned_identity_key,),
        ).fetchone()

        return row is not None

    def delete(
        self,
        watch_id: str,
    ) -> bool:
        self._ensure_open()
        cleaned_watch_id = self._clean_required_text(
            watch_id,
            field_name="watch_id",
        )

        with self._connection:
            cursor = self._connection.execute(
                """
                DELETE FROM watch_items
                WHERE watch_id = ?
                """,
                (cleaned_watch_id,),
            )

        return cursor.rowcount > 0

    def count(self) -> int:
        self._ensure_open()

        row = self._connection.execute(
            """
            SELECT COUNT(*) AS item_count
            FROM watch_items
            """
        ).fetchone()

        if row is None:
            return 0

        return int(row["item_count"])

    def close(self) -> None:
        """
        Repository가 직접 생성한 Connection을 종료한다.

        외부에서 주입받은 Connection은 소유하지 않으므로
        종료하지 않는다.
        """
        if self._closed:
            return

        if self._owns_connection:
            self._connection.close()

        self._closed = True

    def __enter__(
        self,
    ) -> SQLiteWatchListRepository:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()

    def _list_by_status(
        self,
        status: WatchItemStatus,
    ) -> tuple[WatchItem, ...]:
        self._ensure_open()

        if not isinstance(status, WatchItemStatus):
            raise TypeError(
                "status는 WatchItemStatus여야 합니다."
            )

        rows = self._connection.execute(
            """
            SELECT *
            FROM watch_items
            WHERE status = ?
            ORDER BY
                created_at ASC,
                watch_id ASC
            """,
            (status.value,),
        ).fetchall()

        return tuple(
            watch_item_from_row(row)
            for row in rows
        )

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                _CREATE_TABLE_SQL
            )
            self._connection.execute(
                _CREATE_STATUS_INDEX_SQL
            )
            self._connection.execute(
                _CREATE_MARKETPLACE_INDEX_SQL
            )
            self._connection.execute(
                _CREATE_UPDATED_AT_INDEX_SQL
            )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(
                "종료된 Watch List Repository는 "
                "사용할 수 없습니다."
            )

    @staticmethod
    def _clean_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name}은 문자열이어야 합니다."
            )

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                f"{field_name}은 비어 있을 수 없습니다."
            )

        return cleaned_value

    @staticmethod
    def _is_identity_conflict(
        error: sqlite3.IntegrityError,
    ) -> bool:
        message = str(error).casefold()

        return (
            "watch_items.identity_key" in message
            or "unique constraint failed: "
            "watch_items.identity_key" in message
        )