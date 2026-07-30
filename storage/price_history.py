from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.models import Product


DEFAULT_DATABASE_PATH = Path("data") / "hyb_opportunity.db"


class PriceObservationConflictError(RuntimeError):
    """Raised when one observation identity has different stored data."""


@dataclass(slots=True, frozen=True)
class PriceHistoryRecord:
    """데이터베이스에 저장된 변경 불가능한 가격 관측 기록."""

    id: int
    marketplace: str
    item_id: str
    title: str
    price: float
    currency: str
    condition: str
    url: str
    observed_at: str
    canonical_product_id: str | None = None
    seller_id: str | None = None


class PriceHistoryRepository:
    """
    SQLite를 이용해 Append-only 가격 이력을 저장하고 조회한다.

    기존 Marketplace Listing 단위 조회를 유지하면서,
    Canonical Product 단위의 다중 Marketplace 가격 이력 조회를 지원한다.
    """

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_database(self) -> None:
        """가격 이력 테이블을 생성하고 기존 DB 스키마를 안전하게 확장한다."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_product_id TEXT,
                    marketplace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    seller_id TEXT,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    url TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )

            self._add_column_if_missing(
                connection,
                column_name="canonical_product_id",
                column_definition="TEXT",
            )
            self._add_column_if_missing(
                connection,
                column_name="seller_id",
                column_definition="TEXT",
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_price_history_product
                ON price_history (marketplace, item_id, observed_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_price_history_canonical
                ON price_history (canonical_product_id, observed_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_price_history_observed_at
                ON price_history (observed_at)
                """
            )
            connection.commit()

    @staticmethod
    def _add_column_if_missing(
        connection: sqlite3.Connection,
        *,
        column_name: str,
        column_definition: str,
    ) -> None:
        rows = connection.execute(
            "PRAGMA table_info(price_history)"
        ).fetchall()
        existing_columns = {str(row["name"]) for row in rows}

        if column_name in existing_columns:
            return

        connection.execute(
            f"ALTER TABLE price_history ADD COLUMN "
            f"{column_name} {column_definition}"
        )

    @staticmethod
    def _normalize_optional_identifier(
        value: str | None,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name}는 문자열 또는 None이어야 합니다.")
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize_observed_at(
        observed_at: datetime | None,
    ) -> str:
        observation_time = observed_at or datetime.now(timezone.utc)

        if not isinstance(observation_time, datetime):
            raise TypeError("observed_at은 datetime 또는 None이어야 합니다.")

        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=timezone.utc)

        return observation_time.isoformat()

    @staticmethod
    def _validate_product(product: Product) -> None:
        if not isinstance(product, Product):
            raise TypeError("product는 Product 객체여야 합니다.")
        if product.price < 0:
            raise ValueError("상품 가격은 0 이상이어야 합니다.")

    def save_product_price(
        self,
        product: Product,
        *,
        observed_at: datetime | None = None,
        canonical_product_id: str | None = None,
        seller_id: str | None = None,
    ) -> int:
        """Product의 현재 가격을 새로운 스냅샷으로 추가한다."""
        self._validate_product(product)

        cleaned_canonical_id = self._normalize_optional_identifier(
            canonical_product_id,
            field_name="canonical_product_id",
        )
        resolved_seller_id = self._normalize_optional_identifier(
            seller_id if seller_id is not None else product.seller,
            field_name="seller_id",
        )
        observed_at_text = self._normalize_observed_at(observed_at)
        observation_data = (
            cleaned_canonical_id,
            product.marketplace,
            product.item_id,
            resolved_seller_id,
            product.title,
            float(product.price),
            product.currency,
            product.condition,
            product.url,
            observed_at_text,
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_rows = connection.execute(
                """
                SELECT
                    id,
                    canonical_product_id,
                    marketplace,
                    item_id,
                    seller_id,
                    title,
                    price,
                    currency,
                    condition,
                    url,
                    observed_at
                FROM price_history
                WHERE canonical_product_id IS ?
                  AND marketplace = ?
                  AND item_id = ?
                  AND observed_at = ?
                ORDER BY id
                """,
                (
                    cleaned_canonical_id,
                    product.marketplace,
                    product.item_id,
                    observed_at_text,
                ),
            ).fetchall()

            if existing_rows:
                existing = existing_rows[0]
                if all(
                    self._observation_data_from_row(row)
                    == observation_data
                    for row in existing_rows
                ):
                    connection.commit()
                    return int(existing["id"])

                raise PriceObservationConflictError(
                    "The observation identity already exists with "
                    "different data."
                )

            cursor = connection.execute(
                """
                INSERT INTO price_history (
                    canonical_product_id,
                    marketplace,
                    item_id,
                    seller_id,
                    title,
                    price,
                    currency,
                    condition,
                    url,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                observation_data,
            )
            connection.commit()
            record_id = cursor.lastrowid

        if record_id is None:
            raise RuntimeError("가격 기록 저장에 실패했습니다.")

        return int(record_id)

    @staticmethod
    def _observation_data_from_row(
        row: sqlite3.Row,
    ) -> tuple[object, ...]:
        return (
            row["canonical_product_id"],
            row["marketplace"],
            row["item_id"],
            row["seller_id"],
            row["title"],
            float(row["price"]),
            row["currency"],
            row["condition"],
            row["url"],
            row["observed_at"],
        )

    def save_products(
        self,
        products: Iterable[Product],
        *,
        observed_at: datetime | None = None,
    ) -> int:
        """여러 Product를 Listing 단위 가격 스냅샷으로 추가한다."""
        product_list = list(products)
        if not product_list:
            return 0

        for product in product_list:
            self._validate_product(product)

        observed_at_text = self._normalize_observed_at(observed_at)
        rows = [
            (
                None,
                product.marketplace,
                product.item_id,
                self._normalize_optional_identifier(
                    product.seller,
                    field_name="seller_id",
                ),
                product.title,
                float(product.price),
                product.currency,
                product.condition,
                product.url,
                observed_at_text,
            )
            for product in product_list
        ]

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO price_history (
                    canonical_product_id,
                    marketplace,
                    item_id,
                    seller_id,
                    title,
                    price,
                    currency,
                    condition,
                    url,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

        return len(rows)

    def get_product_history(
        self,
        *,
        marketplace: str,
        item_id: str,
        limit: int | None = None,
    ) -> list[PriceHistoryRecord]:
        """특정 Marketplace Listing의 가격 이력을 최신순으로 반환한다."""
        cleaned_marketplace = marketplace.strip()
        cleaned_item_id = item_id.strip()

        if not cleaned_marketplace:
            raise ValueError("marketplace를 입력해야 합니다.")
        if not cleaned_item_id:
            raise ValueError("item_id를 입력해야 합니다.")

        return self._query_records(
            where_clause="marketplace = ? AND item_id = ?",
            parameters=[cleaned_marketplace, cleaned_item_id],
            limit=limit,
        )

    def get_canonical_history(
        self,
        *,
        canonical_product_id: str,
        limit: int | None = None,
    ) -> list[PriceHistoryRecord]:
        """Canonical Product에 연결된 전체 Marketplace 가격 이력을 반환한다."""
        cleaned_id = self._normalize_optional_identifier(
            canonical_product_id,
            field_name="canonical_product_id",
        )
        if cleaned_id is None:
            raise ValueError("canonical_product_id를 입력해야 합니다.")

        return self._query_records(
            where_clause="canonical_product_id = ?",
            parameters=[cleaned_id],
            limit=limit,
        )

    def get_latest_record(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> PriceHistoryRecord | None:
        records = self.get_product_history(
            marketplace=marketplace,
            item_id=item_id,
            limit=1,
        )
        return records[0] if records else None

    def get_latest_canonical_record(
        self,
        *,
        canonical_product_id: str,
    ) -> PriceHistoryRecord | None:
        records = self.get_canonical_history(
            canonical_product_id=canonical_product_id,
            limit=1,
        )
        return records[0] if records else None

    def get_all_records(
        self,
        *,
        limit: int | None = None,
    ) -> list[PriceHistoryRecord]:
        return self._query_records(
            where_clause=None,
            parameters=[],
            limit=limit,
        )

    def _query_records(
        self,
        *,
        where_clause: str | None,
        parameters: list[object],
        limit: int | None,
    ) -> list[PriceHistoryRecord]:
        if limit is not None and limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")

        query = """
            SELECT
                id,
                canonical_product_id,
                marketplace,
                item_id,
                seller_id,
                title,
                price,
                currency,
                condition,
                url,
                observed_at
            FROM price_history
        """

        if where_clause is not None:
            query += f" WHERE {where_clause}"

        query += " ORDER BY observed_at DESC, id DESC"

        query_parameters = list(parameters)
        if limit is not None:
            query += " LIMIT ?"
            query_parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, query_parameters).fetchall()

        return [self._row_to_record(row) for row in rows]

    def count_records(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS record_count FROM price_history"
            ).fetchone()
        return 0 if row is None else int(row["record_count"])

    def delete_all_records(self) -> int:
        previous_count = self.count_records()
        with self._connect() as connection:
            connection.execute("DELETE FROM price_history")
            connection.commit()
        return previous_count

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> PriceHistoryRecord:
        canonical_product_id = row["canonical_product_id"]
        seller_id = row["seller_id"]

        return PriceHistoryRecord(
            id=int(row["id"]),
            canonical_product_id=(
                str(canonical_product_id)
                if canonical_product_id is not None
                else None
            ),
            marketplace=str(row["marketplace"]),
            item_id=str(row["item_id"]),
            seller_id=str(seller_id) if seller_id is not None else None,
            title=str(row["title"]),
            price=float(row["price"]),
            currency=str(row["currency"]),
            condition=str(row["condition"]),
            url=str(row["url"]),
            observed_at=str(row["observed_at"]),
        )
