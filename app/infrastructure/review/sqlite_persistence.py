from __future__ import annotations

import sqlite3
from pathlib import Path

from app.application.review import (
    ReviewCommitError,
    ReviewHistoryError,
    ReviewPersistenceError,
    ReviewProjectionError,
    ReviewCommandConflictError,
    ReviewSessionVersionConflictError,
)
from app.domain.market_intelligence import ExternalMarketSignal, HumanVerification
from app.infrastructure.external_signal_ledger import SQLiteExternalSignalLedgerRepository
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.review.sqlite_session_repository import SQLiteReviewSessionRepository


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
        self.sessions = SQLiteReviewSessionRepository(connection=self._connection)

    def save(
        self,
        verification: HumanVerification,
        signal: ExternalMarketSignal,
        *,
        previous_session=None,
        next_session=None,
        transition_metadata=None,
        receipt=None,
    ) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except Exception as error:
            raise ReviewCommitError("verified review transaction could not start") from error
        try:
            if previous_session is not None:
                self.sessions.validate_current(previous_session)
            try:
                self.ledger.save_verification(verification, _manage_transaction=False)
            except Exception as error:
                exists = self._connection.execute(
                    "SELECT 1 FROM human_verification_history WHERE verification_id = ?",
                    (verification.verification_id,),
                ).fetchone()
                error_type = ReviewProjectionError if exists else ReviewHistoryError
                raise error_type("human verification persistence failed") from error
            try:
                self.observations.save(signal, _manage_transaction=False)
            except Exception as error:
                exists = self._connection.execute(
                    "SELECT 1 FROM market_observation_history WHERE observation_id = ?",
                    (signal.signal_id,),
                ).fetchone()
                error_type = ReviewProjectionError if exists else ReviewHistoryError
                raise error_type("external signal persistence failed") from error
            if previous_session is not None:
                if receipt is not None:
                    self.sessions.save_receipt(
                        receipt,
                        transition_metadata.command_fingerprint,
                        _manage_transaction=False,
                    )
                self.sessions.save_transition(
                    previous_session,
                    next_session,
                    transition_metadata,
                    _manage_transaction=False,
                )
            try:
                self._connection.commit()
            except Exception as error:
                raise ReviewCommitError("verified review transaction commit failed") from error
        except (
            ReviewPersistenceError,
            ReviewCommandConflictError,
            ReviewSessionVersionConflictError,
        ):
            self._connection.rollback()
            raise
        except Exception as error:
            self._connection.rollback()
            raise ReviewPersistenceError(
                "verified signal workflow transaction failed",
                partial_completion=False,
            ) from error

    def create_session(self, session, metadata, receipt=None, *, contexts=()) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if receipt is not None:
                self.sessions.save_receipt(
                    receipt, metadata.command_fingerprint, _manage_transaction=False
                )
            self.sessions.create(session, metadata, _manage_transaction=False)
            for context in contexts:
                self.sessions.save_context(context, _manage_transaction=False)
            self._connection.commit()
        except (
            ReviewPersistenceError,
            ReviewCommandConflictError,
            ReviewSessionVersionConflictError,
        ):
            self._connection.rollback()
            raise
        except Exception as error:
            self._connection.rollback()
            raise ReviewCommitError("review session creation transaction failed") from error

    def save_session_transition(
        self,
        previous_session,
        next_session,
        metadata,
        receipt,
        cancel_metadata=None,
    ) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self.sessions.validate_current(previous_session)
            self.sessions.save_receipt(
                receipt, metadata.command_fingerprint, _manage_transaction=False
            )
            if cancel_metadata is not None:
                self.sessions.save_cancel_metadata(cancel_metadata, _manage_transaction=False)
            self.sessions.save_transition(
                previous_session, next_session, metadata, _manage_transaction=False
            )
            self._connection.commit()
        except (
            ReviewPersistenceError,
            ReviewCommandConflictError,
            ReviewSessionVersionConflictError,
        ):
            self._connection.rollback()
            raise
        except Exception as error:
            self._connection.rollback()
            raise ReviewCommitError("review session transition transaction failed") from error

    def close(self) -> None:
        self._connection.close()
