from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from engine.ai_memory import HistoricalOpportunity
from engine.orchestrator import OpportunityResult
from storage.price_history import DEFAULT_DATABASE_PATH


@dataclass(slots=True, frozen=True)
class SavedOpportunity:
    """
    데이터베이스에 저장된 상품 기회 분석 결과.
    """

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

    ai_partner_title: str = ""
    ai_partner_summary: str = ""
    ai_partner_recommendation: str = ""
    ai_partner_next_action: str = ""

    landed_cost: float = 0.0
    selling_cost: float = 0.0
    total_cost: float = 0.0
    margin_rate: float = 0.0
    landed_cost_roi: float = 0.0
    marketplace_fee: float = 0.0
    payment_fee: float = 0.0
    tax_cost: float = 0.0
    other_cost: float = 0.0
    passes_profitability_filter: bool = True


class OpportunityHistoryRepository:
    """
    SQLite에 검색별 기회 분석 결과를 저장하고 조회한다.
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
            self.database_path
        )
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_database(self) -> None:
        """
        기회 분석 이력 테이블을 생성한다.

        기존 데이터베이스에 AI Partner 컬럼이 없으면
        기존 데이터는 유지하면서 자동으로 컬럼을 추가한다.
        """
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
                    created_at TEXT NOT NULL,
                    ai_partner_title TEXT NOT NULL DEFAULT '',
                    ai_partner_summary TEXT NOT NULL DEFAULT '',
                    ai_partner_recommendation TEXT NOT NULL DEFAULT '',
                    ai_partner_next_action TEXT NOT NULL DEFAULT '',
                    landed_cost REAL NOT NULL DEFAULT 0,
                    selling_cost REAL NOT NULL DEFAULT 0,
                    total_cost REAL NOT NULL DEFAULT 0,
                    margin_rate REAL NOT NULL DEFAULT 0,
                    landed_cost_roi REAL NOT NULL DEFAULT 0,
                    marketplace_fee REAL NOT NULL DEFAULT 0,
                    payment_fee REAL NOT NULL DEFAULT 0,
                    tax_cost REAL NOT NULL DEFAULT 0,
                    other_cost REAL NOT NULL DEFAULT 0,
                    passes_profitability_filter INTEGER NOT NULL DEFAULT 1
                )
                """
            )

            self._ensure_history_columns(
                connection
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_opportunity_history_created_at
                ON opportunity_history (created_at)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_opportunity_history_query
                ON opportunity_history (
                    query,
                    created_at
                )
                """
            )

            connection.commit()

    @staticmethod
    def _ensure_history_columns(
        connection: sqlite3.Connection,
    ) -> None:
        """
        과거 버전의 데이터베이스에
        AI Partner와 Opportunity 비용 저장 컬럼을 추가한다.
        """
        rows = connection.execute(
            """
            PRAGMA table_info(opportunity_history)
            """
        ).fetchall()

        existing_columns = {
            str(row["name"])
            for row in rows
        }

        required_columns = {
            "ai_partner_title": (
                "TEXT NOT NULL DEFAULT ''"
            ),
            "ai_partner_summary": (
                "TEXT NOT NULL DEFAULT ''"
            ),
            "ai_partner_recommendation": (
                "TEXT NOT NULL DEFAULT ''"
            ),
            "ai_partner_next_action": (
                "TEXT NOT NULL DEFAULT ''"
            ),
            "landed_cost": "REAL NOT NULL DEFAULT 0",
            "selling_cost": "REAL NOT NULL DEFAULT 0",
            "total_cost": "REAL NOT NULL DEFAULT 0",
            "margin_rate": "REAL NOT NULL DEFAULT 0",
            "landed_cost_roi": "REAL NOT NULL DEFAULT 0",
            "marketplace_fee": "REAL NOT NULL DEFAULT 0",
            "payment_fee": "REAL NOT NULL DEFAULT 0",
            "tax_cost": "REAL NOT NULL DEFAULT 0",
            "other_cost": "REAL NOT NULL DEFAULT 0",
            "passes_profitability_filter": (
                "INTEGER NOT NULL DEFAULT 1"
            ),
        }

        for column_name, column_definition in (
            required_columns.items()
        ):
            if column_name in existing_columns:
                continue

            connection.execute(
                f"""
                ALTER TABLE opportunity_history
                ADD COLUMN {column_name}
                {column_definition}
                """
            )

    def save_results(
        self,
        query: str,
        results: Iterable[OpportunityResult],
        *,
        created_at: datetime | None = None,
    ) -> int:
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError(
                "검색어를 입력해야 합니다."
            )

        result_list = list(results)

        if not result_list:
            return 0

        timestamp = (
            created_at
            or datetime.now(timezone.utc)
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        created_at_text = timestamp.isoformat()

        rows: list[tuple[object, ...]] = []

        for result in result_list:
            recommendation = (
                result.ai_recommendation
            )
            ai_partner_report = (
                result.ai_partner_report
            )
            analysis = result.analysis

            rows.append(
                (
                    cleaned_query,
                    result.product.marketplace,
                    result.product.item_id,
                    result.product.title,
                    float(result.product.price),
                    float(
                        result.price_intelligence
                        .recommended_selling_price
                    ),
                    float(
                        analysis.get(
                            "net_profit",
                            0.0,
                        )
                    ),
                    float(
                        analysis.get(
                            "roi",
                            0.0,
                        )
                    ),
                    float(
                        result.final_opportunity_score
                    ),
                    (
                        recommendation.grade
                        if recommendation
                        else ""
                    ),
                    (
                        recommendation.action
                        if recommendation
                        else ""
                    ),
                    float(
                        recommendation
                        .success_probability
                        if recommendation
                        else 0.0
                    ),
                    (
                        result.product.currency
                        or "USD"
                    ),
                    result.product.url,
                    created_at_text,
                    (
                        ai_partner_report.title
                        if ai_partner_report
                        else ""
                    ),
                    (
                        ai_partner_report.summary
                        if ai_partner_report
                        else ""
                    ),
                    (
                        ai_partner_report
                        .recommendation
                        if ai_partner_report
                        else ""
                    ),
                    (
                        ai_partner_report.next_action
                        if ai_partner_report
                        else ""
                    ),
                    float(analysis.get("landed_cost", 0.0)),
                    float(analysis.get("selling_cost", 0.0)),
                    float(analysis.get("total_cost", 0.0)),
                    float(analysis.get("margin_rate", 0.0)),
                    float(analysis.get("landed_cost_roi", 0.0)),
                    float(analysis.get("marketplace_fee", 0.0)),
                    float(analysis.get("payment_fee", 0.0)),
                    float(analysis.get("tax_cost", 0.0)),
                    float(analysis.get("other_cost", 0.0)),
                    int(bool(analysis.get(
                        "passes_profitability_filter",
                        True,
                    ))),
                )
            )

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO opportunity_history (
                    query,
                    marketplace,
                    item_id,
                    title,
                    purchase_price,
                    recommended_selling_price,
                    net_profit,
                    roi,
                    opportunity_score,
                    recommendation_grade,
                    recommendation_action,
                    success_probability,
                    currency,
                    url,
                    created_at,
                    ai_partner_title,
                    ai_partner_summary,
                    ai_partner_recommendation,
                    ai_partner_next_action,
                    landed_cost,
                    selling_cost,
                    total_cost,
                    margin_rate,
                    landed_cost_roi,
                    marketplace_fee,
                    payment_fee,
                    tax_cost,
                    other_cost,
                    passes_profitability_filter
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )

            connection.commit()

        return len(rows)

    def get_recent(
        self,
        *,
        limit: int = 20,
    ) -> list[SavedOpportunity]:
        if limit < 1:
            raise ValueError(
                "limit은 1 이상이어야 합니다."
            )

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM opportunity_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def load_ai_memory_history(
        self,
        *,
        limit: int = 500,
    ) -> list[HistoricalOpportunity]:
        """
        최근 기회 분석 이력을 AI Memory가 사용하는
        HistoricalOpportunity 목록으로 변환한다.

        이 메서드는 데이터 조회와 형식 변환만 담당하며,
        백분위 계산이나 비교 분석은 수행하지 않는다.
        """
        if limit < 1:
            raise ValueError(
                "limit은 1 이상이어야 합니다."
            )

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    opportunity_score,
                    roi,
                    net_profit,
                    success_probability
                FROM opportunity_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            HistoricalOpportunity(
                opportunity_score=float(
                    row["opportunity_score"]
                ),
                roi=float(row["roi"]),
                net_profit=float(
                    row["net_profit"]
                ),
                success_probability=float(
                    row["success_probability"]
                ),
            )
            for row in rows
        ]

    def count_records(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS record_count
                FROM opportunity_history
                """
            ).fetchone()

        if row is None:
            return 0

        return int(row["record_count"])

    @staticmethod
    def _row_to_record(
        row: sqlite3.Row,
    ) -> SavedOpportunity:
        return SavedOpportunity(
            id=int(row["id"]),
            query=str(row["query"]),
            marketplace=str(
                row["marketplace"]
            ),
            item_id=str(row["item_id"]),
            title=str(row["title"]),
            purchase_price=float(
                row["purchase_price"]
            ),
            recommended_selling_price=float(
                row[
                    "recommended_selling_price"
                ]
            ),
            net_profit=float(
                row["net_profit"]
            ),
            roi=float(row["roi"]),
            opportunity_score=float(
                row["opportunity_score"]
            ),
            recommendation_grade=str(
                row["recommendation_grade"]
            ),
            recommendation_action=str(
                row["recommendation_action"]
            ),
            success_probability=float(
                row["success_probability"]
            ),
            currency=str(row["currency"]),
            url=str(row["url"]),
            created_at=str(row["created_at"]),
            ai_partner_title=str(
                row["ai_partner_title"]
            ),
            ai_partner_summary=str(
                row["ai_partner_summary"]
            ),
            ai_partner_recommendation=str(
                row[
                    "ai_partner_recommendation"
                ]
            ),
            ai_partner_next_action=str(
                row[
                    "ai_partner_next_action"
                ]
            ),
            landed_cost=float(row["landed_cost"]),
            selling_cost=float(row["selling_cost"]),
            total_cost=float(row["total_cost"]),
            margin_rate=float(row["margin_rate"]),
            landed_cost_roi=float(row["landed_cost_roi"]),
            marketplace_fee=float(row["marketplace_fee"]),
            payment_fee=float(row["payment_fee"]),
            tax_cost=float(row["tax_cost"]),
            other_cost=float(row["other_cost"]),
            passes_profitability_filter=bool(
                row["passes_profitability_filter"]
            ),
        )