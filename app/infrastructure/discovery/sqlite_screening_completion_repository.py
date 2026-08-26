"""Atomic SQLite persistence for completed Discovery screening bundles."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from app.application.discovery.screening_persistence import (
    DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION,
    DiscoveryScreeningCommitError,
    DiscoveryScreeningCompletionBinding,
    DiscoveryScreeningCompletionBundle,
    DiscoveryScreeningCompletionConflictError,
    DiscoveryScreeningCompletionLineageError,
    DiscoveryScreeningHistoryError,
    MalformedDiscoveryScreeningPersistenceError,
    UnsupportedDiscoveryScreeningVersionError,
    serialize_discovery_screening_completion_binding,
)
from app.domain.discovery import (
    DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION,
    DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION,
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
    serialize_discovery_screening_evaluation,
    serialize_discovery_screening_ranking_publication,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery.screening_serialization import (
    deserialize_discovery_screening_completion_binding,
    deserialize_discovery_screening_evaluation,
    deserialize_discovery_screening_ranking_publication,
)
from app.infrastructure.discovery.sqlite_observation_group_repository import (
    SQLiteDiscoveryGroupRepository,
)
from app.infrastructure.discovery.sqlite_repository import (
    SQLiteDiscoveryCommandRepository,
)
from app.infrastructure.discovery.sqlite_result_repository import (
    SQLiteDiscoveryResultRepository,
)


EVALUATION_HISTORY_TABLE = "discovery_screening_evaluation_history"
RANKING_PUBLICATION_HISTORY_TABLE = (
    "discovery_screening_ranking_publication_history"
)
COMPLETION_BINDING_HISTORY_TABLE = (
    "discovery_screening_completion_binding_history"
)


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


class SQLiteDiscoveryScreeningCompletionRepository:
    """Owns the one transaction that makes screening completion authoritative."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                path,
                timeout=30,
                check_same_thread=False,
            )
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

        # These same-connection collaborators establish and reconstruct the
        # already-approved Discovery command, Group, and result schemas. Their
        # commit-owning save methods are never called by the composite write.
        self._commands = SQLiteDiscoveryCommandRepository(connection=connection)
        self._groups = SQLiteDiscoveryGroupRepository(connection=connection)
        self._results = SQLiteDiscoveryResultRepository(connection=connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS
                uq_discovery_finalized_group_identity_execution
                ON discovery_finalized_group_history(
                    finalized_group_id, discovery_execution_id
                )"""
            )
            self._connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS
                uq_discovery_execution_result_command_execution
                ON discovery_execution_result_history(command_id, execution_id)"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {EVALUATION_HISTORY_TABLE}(
                    screening_evaluation_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    finalized_group_id TEXT NOT NULL,
                    group_membership_fingerprint TEXT NOT NULL,
                    canonical_payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    UNIQUE(execution_id, finalized_group_id),
                    UNIQUE(execution_id, screening_evaluation_id),
                    FOREIGN KEY(command_id, execution_id)
                        REFERENCES discovery_command_history(command_id, execution_id),
                    FOREIGN KEY(finalized_group_id, execution_id)
                        REFERENCES discovery_finalized_group_history(
                            finalized_group_id, discovery_execution_id
                        )
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RANKING_PUBLICATION_HISTORY_TABLE}(
                    screening_ranking_publication_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    execution_id TEXT NOT NULL UNIQUE,
                    canonical_payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    ranking_created_at TEXT NOT NULL,
                    zero_result INTEGER NOT NULL CHECK(zero_result IN (0, 1)),
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(command_id, execution_id)
                        REFERENCES discovery_command_history(command_id, execution_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS
                uq_discovery_screening_publication_identity_execution
                ON {RANKING_PUBLICATION_HISTORY_TABLE}(
                    screening_ranking_publication_id, execution_id
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {COMPLETION_BINDING_HISTORY_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE,
                    screening_ranking_publication_id TEXT NOT NULL UNIQUE,
                    result_schema_version TEXT NOT NULL,
                    result_fingerprint TEXT NOT NULL,
                    ranking_publication_fingerprint TEXT NOT NULL,
                    screening_recording_state TEXT NOT NULL
                        CHECK(screening_recording_state = 'RECORDED'),
                    canonical_payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(command_id, execution_id)
                        REFERENCES discovery_execution_result_history(
                            command_id, execution_id
                        ),
                    FOREIGN KEY(
                        screening_ranking_publication_id, execution_id
                    ) REFERENCES {RANKING_PUBLICATION_HISTORY_TABLE}(
                        screening_ranking_publication_id, execution_id
                    )
                )"""
            )
            for table in (
                EVALUATION_HISTORY_TABLE,
                RANKING_PUBLICATION_HISTORY_TABLE,
                COMPLETION_BINDING_HISTORY_TABLE,
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,
                            '{table} is append-only'); END"""
                    )

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def _fault_point(self, name: str) -> None:
        """Test seam for deterministic failures inside the owned transaction."""

    def _command_pair_exists(self, command_id: str, execution_id: str) -> bool:
        try:
            return self._connection.execute(
                """SELECT 1 FROM discovery_command_history
                WHERE command_id=? AND execution_id=?""",
                (command_id, execution_id),
            ).fetchone() is not None
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening command lineage query failed"
            ) from error

    def _evaluation_row(self, evaluation_id: str):
        try:
            return self._connection.execute(
                f"""SELECT * FROM {EVALUATION_HISTORY_TABLE}
                WHERE screening_evaluation_id=?""",
                (evaluation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening evaluation query failed"
            ) from error

    def _publication_row(self, publication_id: str):
        try:
            return self._connection.execute(
                f"""SELECT * FROM {RANKING_PUBLICATION_HISTORY_TABLE}
                WHERE screening_ranking_publication_id=?""",
                (publication_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening ranking publication query failed"
            ) from error

    def _binding_rows_for_identity(
        self,
        binding: DiscoveryScreeningCompletionBinding,
    ) -> tuple[sqlite3.Row, ...]:
        try:
            rows = self._connection.execute(
                f"""SELECT * FROM {COMPLETION_BINDING_HISTORY_TABLE}
                WHERE command_id=? OR execution_id=?
                    OR screening_ranking_publication_id=?""",
                (
                    binding.command_id,
                    binding.discovery_execution_id,
                    binding.screening_ranking_publication_id,
                ),
            ).fetchall()
            return tuple(rows)
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening completion binding query failed"
            ) from error

    def _binding_row(self, column: str, value: str):
        if column not in {
            "command_id",
            "execution_id",
            "screening_ranking_publication_id",
        }:
            raise ValueError("unsupported screening completion lookup")
        try:
            return self._connection.execute(
                f"""SELECT * FROM {COMPLETION_BINDING_HISTORY_TABLE}
                WHERE {column}=?""",
                (value,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening completion binding query failed"
            ) from error

    def _evaluation_from_row(
        self,
        row: sqlite3.Row,
    ) -> DiscoveryScreeningEvaluationSnapshot:
        if row["schema_version"] != DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION:
            raise UnsupportedDiscoveryScreeningVersionError(
                "unsupported persisted screening evaluation version"
            )
        try:
            payload = row["canonical_payload_json"]
            evaluation = deserialize_discovery_screening_evaluation(payload)
            if (
                serialize_discovery_screening_evaluation(evaluation) != payload
                or evaluation.screening_evaluation_id
                != row["screening_evaluation_id"]
                or evaluation.command_id != row["command_id"]
                or evaluation.discovery_execution_id != row["execution_id"]
                or evaluation.finalized_group_id != row["finalized_group_id"]
                or evaluation.group_membership_fingerprint
                != row["group_membership_fingerprint"]
                or evaluation.integrity_fingerprint
                != row["integrity_fingerprint"]
                or evaluation.evaluated_at
                != _aware_datetime(row["evaluated_at"], "evaluated_at")
                or evaluation.schema_version != row["schema_version"]
            ):
                raise ValueError(
                    "screening evaluation columns differ from canonical payload"
                )
            if not self._command_pair_exists(
                evaluation.command_id,
                evaluation.discovery_execution_id,
            ):
                raise ValueError("screening evaluation command lineage is missing")
            group = self._groups.get_group(evaluation.finalized_group_id)
            if (
                group is None
                or group.discovery_execution_id
                != evaluation.discovery_execution_id
                or group.membership_fingerprint
                != evaluation.group_membership_fingerprint
            ):
                raise ValueError(
                    "screening evaluation finalized Group lineage differs"
                )
            return evaluation
        except UnsupportedDiscoveryScreeningVersionError:
            raise
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "persisted screening evaluation is malformed"
            ) from error

    def _publication_from_row(
        self,
        row: sqlite3.Row,
    ) -> DiscoveryScreeningRankingPublication:
        if row["schema_version"] != (
            DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION
        ):
            raise UnsupportedDiscoveryScreeningVersionError(
                "unsupported persisted screening ranking publication version"
            )
        try:
            payload = row["canonical_payload_json"]
            publication = (
                deserialize_discovery_screening_ranking_publication(payload)
            )
            if (
                serialize_discovery_screening_ranking_publication(publication)
                != payload
                or publication.screening_ranking_publication_id
                != row["screening_ranking_publication_id"]
                or publication.command_id != row["command_id"]
                or publication.discovery_execution_id != row["execution_id"]
                or publication.integrity_fingerprint
                != row["integrity_fingerprint"]
                or publication.ranking_created_at
                != _aware_datetime(
                    row["ranking_created_at"],
                    "ranking_created_at",
                )
                or publication.zero_result != bool(row["zero_result"])
                or publication.schema_version != row["schema_version"]
            ):
                raise ValueError(
                    "ranking publication columns differ from canonical payload"
                )
            if not self._command_pair_exists(
                publication.command_id,
                publication.discovery_execution_id,
            ):
                raise ValueError("ranking publication command lineage is missing")
            entries = (
                *publication.ranked_entries,
                *publication.not_ranked_entries,
            )
            for entry in entries:
                evaluation_row = self._evaluation_row(
                    entry.screening_evaluation_id
                )
                if evaluation_row is None:
                    raise ValueError(
                        "ranking publication references an unknown evaluation"
                    )
                evaluation = self._evaluation_from_row(evaluation_row)
                if (
                    evaluation.discovery_execution_id
                    != publication.discovery_execution_id
                    or evaluation.finalized_group_id
                    != entry.finalized_group_id
                    or evaluation.integrity_fingerprint
                    != entry.evaluation_fingerprint
                ):
                    raise ValueError(
                        "ranking publication evaluation lineage differs"
                    )
            count = self._connection.execute(
                f"""SELECT COUNT(*) FROM {EVALUATION_HISTORY_TABLE}
                WHERE execution_id=?""",
                (publication.discovery_execution_id,),
            ).fetchone()[0]
            if count != len(entries):
                raise ValueError(
                    "execution contains evaluations outside its publication"
                )
            return publication
        except UnsupportedDiscoveryScreeningVersionError:
            raise
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "persisted screening ranking publication is malformed"
            ) from error

    @staticmethod
    def _binding_from_row(
        row: sqlite3.Row,
    ) -> DiscoveryScreeningCompletionBinding:
        if row["schema_version"] != (
            DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION
        ):
            raise UnsupportedDiscoveryScreeningVersionError(
                "unsupported persisted screening completion binding version"
            )
        try:
            payload = row["canonical_payload_json"]
            binding = deserialize_discovery_screening_completion_binding(payload)
            if (
                serialize_discovery_screening_completion_binding(binding)
                != payload
                or binding.command_id != row["command_id"]
                or binding.discovery_execution_id != row["execution_id"]
                or binding.screening_ranking_publication_id
                != row["screening_ranking_publication_id"]
                or binding.result_schema_version
                != row["result_schema_version"]
                or binding.result_fingerprint != row["result_fingerprint"]
                or binding.ranking_publication_fingerprint
                != row["ranking_publication_fingerprint"]
                or binding.screening_recording_state.value
                != row["screening_recording_state"]
                or binding.integrity_fingerprint
                != row["integrity_fingerprint"]
                or binding.schema_version != row["schema_version"]
            ):
                raise ValueError(
                    "screening completion binding columns differ from payload"
                )
            return binding
        except UnsupportedDiscoveryScreeningVersionError:
            raise
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "persisted screening completion binding is malformed"
            ) from error

    def _load_completion(
        self,
        binding_row: sqlite3.Row,
    ) -> DiscoveryScreeningCompletionBundle:
        try:
            binding = self._binding_from_row(binding_row)
            result = self._results.get_by_execution(
                binding.discovery_execution_id
            )
            if (
                result is None
                or result.command_id != binding.command_id
                or result.schema_version != binding.result_schema_version
                or result.fingerprint != binding.result_fingerprint
            ):
                raise ValueError(
                    "screening completion binding result lineage differs"
                )
            publication_row = self._publication_row(
                binding.screening_ranking_publication_id
            )
            if publication_row is None:
                raise ValueError(
                    "screening completion binding publication is missing"
                )
            publication = self._publication_from_row(publication_row)
            if publication.integrity_fingerprint != (
                binding.ranking_publication_fingerprint
            ):
                raise ValueError(
                    "screening completion binding publication fingerprint differs"
                )

            evaluation_rows = self._connection.execute(
                f"""SELECT * FROM {EVALUATION_HISTORY_TABLE}
                WHERE execution_id=?""",
                (binding.discovery_execution_id,),
            ).fetchall()
            evaluations_by_group = {}
            for row in evaluation_rows:
                evaluation = self._evaluation_from_row(row)
                if evaluation.finalized_group_id in evaluations_by_group:
                    raise ValueError(
                        "duplicate screening evaluation Group identity"
                    )
                evaluations_by_group[evaluation.finalized_group_id] = evaluation
            if set(evaluations_by_group) != set(result.finalized_group_ids):
                raise ValueError(
                    "screening evaluations and result Group membership differ"
                )
            evaluations = tuple(
                evaluations_by_group[group_id]
                for group_id in result.finalized_group_ids
            )
            finalized_groups = []
            for group_id in result.finalized_group_ids:
                group = self._groups.get_group(group_id)
                if group is None:
                    raise ValueError(
                        "screening completion finalized Group is missing"
                    )
                finalized_groups.append(group)
            return DiscoveryScreeningCompletionBundle(
                execution_result=result,
                finalized_groups=tuple(finalized_groups),
                evaluations=evaluations,
                ranking_publication=publication,
                completion_binding=binding,
            )
        except UnsupportedDiscoveryScreeningVersionError:
            raise
        except MalformedDiscoveryScreeningPersistenceError:
            raise
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "persisted screening completion bundle is malformed"
            ) from error

    def _ensure_no_orphan_screening(self, execution_id: str) -> None:
        try:
            evaluation_count = self._connection.execute(
                f"""SELECT COUNT(*) FROM {EVALUATION_HISTORY_TABLE}
                WHERE execution_id=?""",
                (execution_id,),
            ).fetchone()[0]
            publication_count = self._connection.execute(
                f"""SELECT COUNT(*) FROM {RANKING_PUBLICATION_HISTORY_TABLE}
                WHERE execution_id=?""",
                (execution_id,),
            ).fetchone()[0]
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening orphan query failed"
            ) from error
        if evaluation_count or publication_count:
            raise MalformedDiscoveryScreeningPersistenceError(
                "screening facts exist without a completion binding"
            )

    def _validate_new_bundle(
        self,
        bundle: DiscoveryScreeningCompletionBundle,
    ) -> None:
        result = bundle.execution_result
        if not self._command_pair_exists(
            result.command_id,
            result.discovery_execution_id,
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "screening completion has no committed command execution"
            )
        try:
            command_result = self._results.get_by_command(result.command_id)
            execution_result = self._results.get_by_execution(
                result.discovery_execution_id
            )
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "existing Discovery result persistence is malformed"
            ) from error
        if command_result is not None or execution_result is not None:
            raise DiscoveryScreeningCompletionConflictError(
                "an existing unbound result cannot be upgraded outside the "
                "atomic screening completion transaction"
            )

        persisted_groups = self._groups.get_by_execution(
            result.discovery_execution_id
        )
        if {
            value.finalized_group_id for value in persisted_groups
        } != set(result.finalized_group_ids):
            raise DiscoveryScreeningCompletionLineageError(
                "screening completion must cover every persisted finalized Group"
            )
        persisted_by_id = {
            value.finalized_group_id: value for value in persisted_groups
        }
        for group in bundle.finalized_groups:
            persisted = persisted_by_id.get(group.finalized_group_id)
            if persisted is None or persisted != group:
                raise DiscoveryScreeningCompletionLineageError(
                    "screening completion finalized Group differs from persistence"
                )

        publication = bundle.ranking_publication
        try:
            publication_collision = self._connection.execute(
                f"""SELECT 1 FROM {RANKING_PUBLICATION_HISTORY_TABLE}
                WHERE screening_ranking_publication_id=? OR execution_id=?
                    OR command_id=?""",
                (
                    publication.screening_ranking_publication_id,
                    publication.discovery_execution_id,
                    publication.command_id,
                ),
            ).fetchone()
            if publication_collision is not None:
                raise DiscoveryScreeningCompletionConflictError(
                    "screening ranking publication identity is already committed"
                )
            for evaluation in bundle.evaluations:
                collision = self._connection.execute(
                    f"""SELECT 1 FROM {EVALUATION_HISTORY_TABLE}
                    WHERE screening_evaluation_id=?
                        OR (execution_id=? AND finalized_group_id=?)""",
                    (
                        evaluation.screening_evaluation_id,
                        evaluation.discovery_execution_id,
                        evaluation.finalized_group_id,
                    ),
                ).fetchone()
                if collision is not None:
                    raise DiscoveryScreeningCompletionConflictError(
                        "screening evaluation identity is already committed"
                    )
            self._ensure_no_orphan_screening(result.discovery_execution_id)
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening identity availability query failed"
            ) from error

    def _insert_evaluation(
        self,
        evaluation: DiscoveryScreeningEvaluationSnapshot,
    ) -> None:
        try:
            self._connection.execute(
                f"""INSERT INTO {EVALUATION_HISTORY_TABLE}(
                    screening_evaluation_id,command_id,execution_id,
                    finalized_group_id,group_membership_fingerprint,
                    canonical_payload_json,integrity_fingerprint,
                    evaluated_at,schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation.screening_evaluation_id,
                    evaluation.command_id,
                    evaluation.discovery_execution_id,
                    evaluation.finalized_group_id,
                    evaluation.group_membership_fingerprint,
                    serialize_discovery_screening_evaluation(evaluation),
                    evaluation.integrity_fingerprint,
                    evaluation.evaluated_at.isoformat(),
                    evaluation.schema_version,
                ),
            )
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening evaluation history insert failed"
            ) from error

    def _insert_publication(
        self,
        publication: DiscoveryScreeningRankingPublication,
    ) -> None:
        try:
            self._connection.execute(
                f"""INSERT INTO {RANKING_PUBLICATION_HISTORY_TABLE}(
                    screening_ranking_publication_id,command_id,execution_id,
                    canonical_payload_json,integrity_fingerprint,
                    ranking_created_at,zero_result,schema_version
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    publication.screening_ranking_publication_id,
                    publication.command_id,
                    publication.discovery_execution_id,
                    serialize_discovery_screening_ranking_publication(
                        publication
                    ),
                    publication.integrity_fingerprint,
                    publication.ranking_created_at.isoformat(),
                    int(publication.zero_result),
                    publication.schema_version,
                ),
            )
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening ranking publication history insert failed"
            ) from error

    def _insert_result(self, result: DiscoveryExecutionResult) -> None:
        try:
            self._results._insert_result(result)
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening completion result insert failed"
            ) from error

    def _insert_binding(
        self,
        binding: DiscoveryScreeningCompletionBinding,
    ) -> None:
        try:
            self._connection.execute(
                f"""INSERT INTO {COMPLETION_BINDING_HISTORY_TABLE}(
                    command_id,execution_id,screening_ranking_publication_id,
                    result_schema_version,result_fingerprint,
                    ranking_publication_fingerprint,screening_recording_state,
                    canonical_payload_json,integrity_fingerprint,schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    binding.command_id,
                    binding.discovery_execution_id,
                    binding.screening_ranking_publication_id,
                    binding.result_schema_version,
                    binding.result_fingerprint,
                    binding.ranking_publication_fingerprint,
                    binding.screening_recording_state.value,
                    serialize_discovery_screening_completion_binding(binding),
                    binding.integrity_fingerprint,
                    binding.schema_version,
                ),
            )
        except sqlite3.Error as error:
            raise DiscoveryScreeningHistoryError(
                "screening completion binding history insert failed"
            ) from error

    def save_completion_bundle(
        self,
        bundle: DiscoveryScreeningCompletionBundle,
    ) -> DiscoveryScreeningCompletionBundle:
        if not isinstance(bundle, DiscoveryScreeningCompletionBundle):
            raise TypeError(
                "bundle must be DiscoveryScreeningCompletionBundle"
            )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise DiscoveryScreeningCommitError(
                "screening completion transaction could not start"
            ) from error
        try:
            binding_rows = self._binding_rows_for_identity(
                bundle.completion_binding
            )
            if binding_rows:
                if len(binding_rows) != 1:
                    raise MalformedDiscoveryScreeningPersistenceError(
                        "screening completion identities resolve to multiple bindings"
                    )
                persisted_binding = self._binding_from_row(binding_rows[0])
                if persisted_binding != bundle.completion_binding:
                    raise DiscoveryScreeningCompletionConflictError(
                        "screening completion identity conflicts with committed bundle"
                    )
                persisted = self._load_completion(binding_rows[0])
                if persisted != bundle:
                    raise DiscoveryScreeningCompletionConflictError(
                        "screening completion payload conflicts with committed bundle"
                    )
                self._rollback()
                return persisted

            self._validate_new_bundle(bundle)
            for position, evaluation in enumerate(bundle.evaluations):
                self._insert_evaluation(evaluation)
                if position == 0:
                    self._fault_point("after_first_evaluation")
            self._fault_point("after_all_evaluations")
            self._insert_publication(bundle.ranking_publication)
            self._fault_point("after_ranking_publication")
            self._insert_result(bundle.execution_result)
            self._fault_point("after_execution_result")
            self._fault_point("before_completion_binding")
            self._insert_binding(bundle.completion_binding)
            self._fault_point("after_completion_binding")
            self._fault_point("before_commit")
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DiscoveryScreeningCommitError(
                    "screening completion transaction commit failed"
                ) from error
            return bundle
        except Exception:
            self._rollback()
            raise

    def get_by_execution(
        self,
        discovery_execution_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None:
        execution_id = _required(
            discovery_execution_id,
            "discovery_execution_id",
        )
        row = self._binding_row("execution_id", execution_id)
        if row is None:
            self._ensure_no_orphan_screening(execution_id)
            return None
        return self._load_completion(row)

    def get_by_command(
        self,
        command_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None:
        resolved = _required(command_id, "command_id")
        row = self._binding_row("command_id", resolved)
        if row is None:
            try:
                command = self._commands.get_command(resolved)
            except Exception as error:
                raise MalformedDiscoveryScreeningPersistenceError(
                    "Discovery command persistence is malformed"
                ) from error
            if command is not None:
                self._ensure_no_orphan_screening(
                    command.discovery_execution_id
                )
            return None
        return self._load_completion(row)

    def get_by_publication(
        self,
        screening_ranking_publication_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None:
        publication_id = _required(
            screening_ranking_publication_id,
            "screening_ranking_publication_id",
        )
        row = self._binding_row(
            "screening_ranking_publication_id",
            publication_id,
        )
        if row is None:
            if self._publication_row(publication_id) is not None:
                raise MalformedDiscoveryScreeningPersistenceError(
                    "screening ranking publication has no completion binding"
                )
            return None
        return self._load_completion(row)

    def get_evaluation(
        self,
        screening_evaluation_id: str,
    ) -> DiscoveryScreeningEvaluationSnapshot | None:
        evaluation_id = _required(
            screening_evaluation_id,
            "screening_evaluation_id",
        )
        row = self._evaluation_row(evaluation_id)
        if row is None:
            return None
        binding_row = self._binding_row("execution_id", row["execution_id"])
        if binding_row is None:
            raise MalformedDiscoveryScreeningPersistenceError(
                "screening evaluation has no completion binding"
            )
        completion = self._load_completion(binding_row)
        for evaluation in completion.evaluations:
            if evaluation.screening_evaluation_id == evaluation_id:
                return evaluation
        raise MalformedDiscoveryScreeningPersistenceError(
            "screening evaluation is outside its completion publication"
        )

    def get_ranking_publication(
        self,
        screening_ranking_publication_id: str,
    ) -> DiscoveryScreeningRankingPublication | None:
        completion = self.get_by_publication(
            screening_ranking_publication_id
        )
        return None if completion is None else completion.ranking_publication

    def get_recording_state(
        self,
        discovery_execution_id: str,
    ) -> DiscoveryScreeningRecordingState | None:
        execution_id = _required(
            discovery_execution_id,
            "discovery_execution_id",
        )
        try:
            result = self._results.get_by_execution(execution_id)
        except Exception as error:
            raise MalformedDiscoveryScreeningPersistenceError(
                "Discovery execution result persistence is malformed"
            ) from error
        row = self._binding_row("execution_id", execution_id)
        if result is None:
            if row is not None:
                raise MalformedDiscoveryScreeningPersistenceError(
                    "screening completion binding has no execution result"
                )
            self._ensure_no_orphan_screening(execution_id)
            return None
        if row is None:
            self._ensure_no_orphan_screening(execution_id)
            return (
                DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
            )
        completion = self._load_completion(row)
        return completion.screening_recording_state

    def close(self) -> None:
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self) -> "SQLiteDiscoveryScreeningCompletionRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = [
    "COMPLETION_BINDING_HISTORY_TABLE",
    "EVALUATION_HISTORY_TABLE",
    "RANKING_PUBLICATION_HISTORY_TABLE",
    "SQLiteDiscoveryScreeningCompletionRepository",
]
