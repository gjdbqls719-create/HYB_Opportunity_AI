from __future__ import annotations

import sqlite3
from pathlib import Path

from app.application.review import ReviewPersistenceError
from app.domain.market_intelligence import ExternalMarketSignal, HumanVerification
from app.infrastructure.external_signal_ledger import SQLiteExternalSignalLedgerRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository


class SQLiteVerifiedSignalPersistence:
    """Atomically appends a verification fact and its verified market signal."""

    def __init__(self, database_path: str | Path = "data/hyb_opportunity.db") -> None:
        resolved = str(database_path)
        if resolved != ":memory:":
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(resolved)
        self._connection.row_factory = sqlite3.Row
        self.ledger = SQLiteExternalSignalLedgerRepository(connection=self._connection)
        self.observations = SQLiteMarketObservationRepository(connection=self._connection)

    def save(self, verification: HumanVerification, signal: ExternalMarketSignal) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self.ledger.save_verification(verification, _manage_transaction=False)
            self.observations.save(signal, _manage_transaction=False)
            self._connection.commit()
        except Exception as error:
            self._connection.rollback()
            raise ReviewPersistenceError(
                "verified signal workflow transaction failed",
                partial_completion=False,
            ) from error

    def close(self) -> None:
        self._connection.close()
