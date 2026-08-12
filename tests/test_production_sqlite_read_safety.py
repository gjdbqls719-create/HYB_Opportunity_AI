from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import app.web as web
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    OpportunityValidationService,
)
from app.domain.opportunity import OpportunityLifecycleStatus
from app.infrastructure.opportunity_validation import (
    SQLiteValidationQueueRepository,
)
from app.infrastructure.production_safety_evaluation import (
    SQLiteProductionSafetyEvaluationRepository,
)
from app.infrastructure.review import SQLiteVerifiedSignalPersistence


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)
INDEX_NAME = "uq_active_validation_discovery_reference"


def _state(path: Path) -> tuple[bytes, str, int, int, tuple[str, ...]]:
    payload = path.read_bytes()
    sidecars = tuple(
        candidate.name
        for suffix in ("-wal", "-shm", "-journal")
        if (candidate := Path(f"{path}{suffix}")).exists()
    )
    metadata = path.stat()
    return (
        payload,
        hashlib.sha256(payload).hexdigest(),
        metadata.st_size,
        metadata.st_mtime_ns,
        sidecars,
    )


def _index_sql(path: Path) -> str | None:
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro&immutable=1",
        uri=True,
    )
    try:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (INDEX_NAME,),
        ).fetchone()
        return None if row is None else row[0]
    finally:
        connection.close()


def _validation_service(
    repository: SQLiteValidationQueueRepository,
) -> OpportunityValidationService:
    return OpportunityValidationService(
        queue_repository=repository,
        lifecycle_repository=repository,
    )


def _bootstrap_validation(path: Path) -> None:
    repository = SQLiteValidationQueueRepository(path)
    try:
        _validation_service(repository).add(
            AddToValidationQueueCommand(
                discovery_reference="ebay:item-read-safety",
                marketplace="ebay",
                title="Read Safety Fixture",
                admission_recommendation="WATCH",
                admission_score=70,
                admission_roi=20,
                currency="USD",
                admission_safety_status="READY",
                operator_id="founder",
                reason="isolated read-safety fixture",
                captured_at=NOW,
                opportunity_id="opportunity-read-safety",
            )
        )
    finally:
        repository.close()


def _bootstrap_read_composition(path: Path) -> None:
    SQLiteVerifiedSignalPersistence(path).close()
    SQLiteProductionSafetyEvaluationRepository(database_path=path).close()


def test_current_schema_validation_constructor_and_reads_are_byte_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "current.db"
    _bootstrap_validation(path)
    before = _state(path)

    repository = SQLiteValidationQueueRepository(path)
    try:
        assert repository.get("opportunity-read-safety") is not None
        assert len(repository.list_queue(
            statuses=(OpportunityLifecycleStatus.DISCOVERED,),
            limit=10,
        )) == 1
    finally:
        repository.close()

    assert _state(path) == before


def test_verified_signal_composition_is_byte_stable_for_current_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "verified-signals.db"
    _bootstrap_read_composition(path)
    before = _state(path)

    persistence = SQLiteVerifiedSignalPersistence(path)
    try:
        assert persistence.opportunities.list_queue(statuses=(), limit=10) == ()
    finally:
        persistence.close()

    assert _state(path) == before


def test_production_get_paths_are_byte_stable_for_current_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "production-reads.db"
    _bootstrap_read_composition(path)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    before = _state(path)
    client = TestClient(web.app)

    requests = (
        ("/docs", 200),
        ("/openapi.json", 200),
        ("/api/v1/opportunities", 200),
        ("/api/v1/opportunities/missing/review-detail", 404),
        ("/api/v1/opportunities/missing/decision-readiness", 404),
        ("/api/v1/validation-queue", 200),
        ("/api/v1/validation-queue/missing", 404),
        ("/api/v1/opportunities/missing/decision-dashboard", 404),
    )
    for url, status_code in requests:
        assert client.get(url).status_code == status_code
        assert _state(path) == before


def test_fresh_bootstrap_creates_required_index_and_restarts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh.db"
    _bootstrap_validation(path)

    assert INDEX_NAME in (_index_sql(path) or "")
    repository = SQLiteValidationQueueRepository(path)
    try:
        item = repository.get("opportunity-read-safety")
        assert item is not None
        assert item.discovery_reference == "ebay:item-read-safety"
    finally:
        repository.close()


def test_legacy_noncanonical_references_migrate_once_and_restart_byte_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    _bootstrap_validation(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"DROP INDEX {INDEX_NAME}")
        connection.execute(
            "UPDATE opportunity_lifecycles SET discovery_reference=?",
            (" EBAY / ITEM-READ-SAFETY ",),
        )
        connection.execute(
            "UPDATE validation_queue_admission_snapshots SET discovery_reference=?",
            (" EBAY / ITEM-READ-SAFETY ",),
        )
        connection.commit()
    finally:
        connection.close()

    migrated = SQLiteValidationQueueRepository(path)
    try:
        item = migrated.get("opportunity-read-safety")
        assert item is not None
        assert item.discovery_reference == "ebay:item-read-safety"
        stored = migrated._connection.execute(
            "SELECT discovery_reference FROM opportunity_lifecycles "
            "WHERE opportunity_id='opportunity-read-safety'"
        ).fetchone()[0]
        assert stored == "ebay:item-read-safety"
    finally:
        migrated.close()

    assert INDEX_NAME in (_index_sql(path) or "")
    after_migration = _state(path)
    restarted = SQLiteValidationQueueRepository(path)
    try:
        assert restarted.get("opportunity-read-safety") is not None
    finally:
        restarted.close()
    assert _state(path) == after_migration
