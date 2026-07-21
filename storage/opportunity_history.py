from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from engine.orchestrator import OpportunityResult
from storage.price_history import DEFAULT_DATABASE_PATH


@dataclass(slots=True, frozen=True)
class SavedOpportunity:
    id: int
    query: str
    marketplace: str
    item_id: str
    title: str
    purchase_price: float
    recommended_selling_price: float
    net_profit: float
    roi: float
    opportunity_score: float
    recommendation_grade: str
    recommendation_action: str
    success_probability: float
    currency: str
    url: str
    created_at: str


class OpportunityHistoryRepository:
    """SQLite에 검색별 기회 분석 결과를 저장하고 조회한다."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    marketplace TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    purchase_price REAL NOT NULL,
                    recommended_selling_price REAL NOT NULL,
                    net_profit REAL NOT NULL,
                    roi REAL NOT NULL,
                    opportunity_score REAL NOT NULL,
                    recommendation_grade TEXT NOT NULL,
                    recommendation_action TEXT NOT NULL,
                    success_probability REAL NOT NULL,
                    currency TEXT NOT NULL,
                    url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_opportunity_history_created_at
                ON opportunity_history (created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_opportunity_history_query
                ON opportunity_history (query, created_at)
                """
            )
            connection.commit()

    def save_results(
        self,
        query: str,
        results: Iterable[OpportunityResult],
        *,
        created_at: datetime | None = None,
    ) -> int:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("검색어를 입력해야 합니다.")

        result_list = list(results)
        if not result_list:
            return 0

        timestamp = created_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        created_at_text = timestamp.isoformat()

        rows: list[tuple[object, ...]] = []
        for result in result_list:
            recommendation = result.ai_recommendation
            analysis = result.analysis
            rows.append(
                (
                    cleaned_query,
                    result.product.marketplace,
                    result.product.item_id,
                    result.product.title,
                    float(result.product.price),
                    float(result.price_intelligence.recommended_selling_price),
                    float(analysis.get("net_profit", 0.0)),
                    float(analysis.get("roi", 0.0)),
                    float(result.final_opportunity_score),
                    recommendation.grade if recommendation else "",
                    recommendation.action if recommendation else "",
                    float(recommendation.success_probability if recommendation else 0.0),
                    result.product.currency or "USD",
                    result.product.url,
                    created_at_text,
                )
            )

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO opportunity_history (
                    query, marketplace, item_id, title,
                    purchase_price, recommended_selling_price,
                    net_profit, roi, opportunity_score,
                    recommendation_grade, recommendation_action,
                    success_probability, currency, url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()
        return len(rows)

    def get_recent(self, *, limit: int = 20) -> list[SavedOpportunity]:
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM opportunity_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_records(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS record_count FROM opportunity_history"
            ).fetchone()
        return int(row["record_count"]) if row is not None else 0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SavedOpportunity:
        return SavedOpportunity(
            id=int(row["id"]),
            query=str(row["query"]),
            marketplace=str(row["marketplace"]),
            item_id=str(row["item_id"]),
            title=str(row["title"]),
            purchase_price=float(row["purchase_price"]),
            recommended_selling_price=float(row["recommended_selling_price"]),
            net_profit=float(row["net_profit"]),
            roi=float(row["roi"]),
            opportunity_score=float(row["opportunity_score"]),
            recommendation_grade=str(row["recommendation_grade"]),
            recommendation_action=str(row["recommendation_action"]),
            success_probability=float(row["success_probability"]),
            currency=str(row["currency"]),
            url=str(row["url"]),
            created_at=str(row["created_at"]),
        )
