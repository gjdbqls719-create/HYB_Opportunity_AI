from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.models import Product


DEFAULT_DATABASE_PATH = Path("data") / "hyb_opportunity.db"


@dataclass(slots=True, frozen=True)
class PriceHistoryRecord:
    """
    데이터베이스에 저장된 상품 가격 기록.
    """

    id: int
    marketplace: str
    item_id: str
    title: str
    price: float
    currency: str
    condition: str
    url: str
    observed_at: str


class PriceHistoryRepository:
    """
    SQLite를 이용해 상품 가격 이력을 저장하고 조회한다.
    """

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.database_path = Path(database_path)

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
        )

        connection.row_factory = sqlite3.Row

        return connection

    def initialize_database(self) -> None:
        """
        가격 이력 테이블과 조회용 인덱스를 생성한다.
        """
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marketplace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    url TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_price_history_product
                ON price_history (
                    marketplace,
                    item_id,
                    observed_at
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_price_history_observed_at
                ON price_history (
                    observed_at
                )
                """
            )

            connection.commit()

    def save_product_price(
        self,
        product: Product,
        *,
        observed_at: datetime | None = None,
    ) -> int:
        """
        Product의 현재 가격을 데이터베이스에 저장한다.

        반환값:
            새로 생성된 가격 기록의 ID
        """
        if product.price < 0:
            raise ValueError(
                "상품 가격은 0 이상이어야 합니다."
            )

        observation_time = (
            observed_at
            if observed_at is not None
            else datetime.now(timezone.utc)
        )

        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(
                tzinfo=timezone.utc,
            )

        observed_at_text = observation_time.isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO price_history (
                    marketplace,
                    item_id,
                    title,
                    price,
                    currency,
                    condition,
                    url,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product.marketplace,
                    product.item_id,
                    product.title,
                    float(product.price),
                    product.currency,
                    product.condition,
                    product.url,
                    observed_at_text,
                ),
            )

            connection.commit()

            record_id = cursor.lastrowid

        if record_id is None:
            raise RuntimeError(
                "가격 기록 저장에 실패했습니다."
            )

        return int(record_id)

    def save_products(
        self,
        products: Iterable[Product],
        *,
        observed_at: datetime | None = None,
    ) -> int:
        """
        여러 상품의 가격을 한 번에 저장한다.

        반환값:
            저장된 상품 개수
        """
        product_list = list(products)

        if not product_list:
            return 0

        observation_time = (
            observed_at
            if observed_at is not None
            else datetime.now(timezone.utc)
        )

        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(
                tzinfo=timezone.utc,
            )

        observed_at_text = observation_time.isoformat()

        rows = [
            (
                product.marketplace,
                product.item_id,
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
                    marketplace,
                    item_id,
                    title,
                    price,
                    currency,
                    condition,
                    url,
                    observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        """
        특정 상품의 가격 이력을 최신순으로 반환한다.
        """
        cleaned_marketplace = marketplace.strip()
        cleaned_item_id = item_id.strip()

        if not cleaned_marketplace:
            raise ValueError(
                "marketplace를 입력해야 합니다."
            )

        if not cleaned_item_id:
            raise ValueError(
                "item_id를 입력해야 합니다."
            )

        if limit is not None and limit < 1:
            raise ValueError(
                "limit은 1 이상이어야 합니다."
            )

        query = """
            SELECT
                id,
                marketplace,
                item_id,
                title,
                price,
                currency,
                condition,
                url,
                observed_at
            FROM price_history
            WHERE marketplace = ?
              AND item_id = ?
            ORDER BY observed_at DESC, id DESC
        """

        parameters: list[object] = [
            cleaned_marketplace,
            cleaned_item_id,
        ]

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def get_latest_record(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> PriceHistoryRecord | None:
        """
        특정 상품의 가장 최근 가격 기록을 반환한다.
        """
        records = self.get_product_history(
            marketplace=marketplace,
            item_id=item_id,
            limit=1,
        )

        if not records:
            return None

        return records[0]

    def get_all_records(
        self,
        *,
        limit: int | None = None,
    ) -> list[PriceHistoryRecord]:
        """
        전체 가격 기록을 최신순으로 반환한다.
        """
        if limit is not None and limit < 1:
            raise ValueError(
                "limit은 1 이상이어야 합니다."
            )

        query = """
            SELECT
                id,
                marketplace,
                item_id,
                title,
                price,
                currency,
                condition,
                url,
                observed_at
            FROM price_history
            ORDER BY observed_at DESC, id DESC
        """

        parameters: list[object] = []

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def count_records(self) -> int:
        """
        전체 가격 기록 개수를 반환한다.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS record_count
                FROM price_history
                """
            ).fetchone()

        if row is None:
            return 0

        return int(row["record_count"])

    def delete_all_records(self) -> int:
        """
        모든 가격 기록을 삭제한다.

        반환값:
            삭제된 기록 개수
        """
        previous_count = self.count_records()

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM price_history
                """
            )

            connection.commit()

        return previous_count

    @staticmethod
    def _row_to_record(
        row: sqlite3.Row,
    ) -> PriceHistoryRecord:
        return PriceHistoryRecord(
            id=int(row["id"]),
            marketplace=str(row["marketplace"]),
            item_id=str(row["item_id"]),
            title=str(row["title"]),
            price=float(row["price"]),
            currency=str(row["currency"]),
            condition=str(row["condition"]),
            url=str(row["url"]),
            observed_at=str(row["observed_at"]),
        )