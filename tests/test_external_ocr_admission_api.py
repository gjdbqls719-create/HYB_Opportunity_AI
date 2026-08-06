from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.application.ocr import ExternalOCRCandidateAdmission
from app.infrastructure.external_signal_ledger import (
    ProductionOCRCandidateIdentityGenerator,
    SQLiteExternalSignalLedgerRepository,
)
from app.web import app, get_external_ocr_admission_entry
import app.web as web
from test_external_ocr_execution_persistence import (
    ARTIFACT_ADMITTED_AT,
    COMMITTED_AT,
    Fail,
    Sequence,
    count,
)


def payload(**changes):
    value = {
        "artifact": {
            "artifact_id": "artifact-1",
            "artifact_type": "screenshot",
            "artifact_origin": "itemscout",
            "source_type": "itemscout_screenshot",
            "sha256": "a" * 64,
            "captured_at": "2026-08-20T08:00:00Z",
            "width": 1920,
            "height": 1080,
            "mime_type": "image/png",
            "file_size": 1234,
            "schema_version": "artifact-v1",
        },
        "provider": "google_vision",
        "provider_version": "2026-08",
        "request_id": "external-request-1",
        "executed_at": "2026-08-20T08:01:00Z",
        "result_confidence": "0.87",
        "fields": [
            {
                "field_name": "price",
                "raw_text": "19,900",
                "normalized_value": 19900,
                "confidence": "0.91",
                "bounding_box": [10, 20, 30, 40],
            },
            {
                "field_name": "search_volume",
                "raw_text": "1,234",
                "normalized_value": 1234,
                "confidence": "0.82",
                "bounding_box": None,
            },
        ],
        "execution_schema_version": "ocr-result-v1",
    }
    value.update(changes)
    return value


def use(admission):
    app.dependency_overrides[get_external_ocr_admission_entry] = lambda: admission
    return TestClient(app)


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def api_repository(database_path=":memory:") -> SQLiteExternalSignalLedgerRepository:
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    return SQLiteExternalSignalLedgerRepository(connection=connection)


def close_api_repository(repository) -> None:
    repository._connection.close()


def admission(repository, *, identities=None, artifact_clock=None, receipt_clock=None):
    return ExternalOCRCandidateAdmission(
        persistence=repository,
        candidate_identity_supplier=(
            identities or Sequence("candidate-price", "candidate-volume")
        ),
        artifact_admission_clock=(
            artifact_clock or Sequence(ARTIFACT_ADMITTED_AT)
        ),
        receipt_clock=receipt_clock or Sequence(COMMITTED_AT),
    )


def test_external_ocr_composition_uses_production_dependencies_and_closes(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "ocr-api-composition.sqlite3"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_external_ocr_admission_entry()
    owner = next(dependency)
    repository = owner._persistence

    assert isinstance(owner, ExternalOCRCandidateAdmission)
    assert isinstance(repository, SQLiteExternalSignalLedgerRepository)
    assert isinstance(
        owner._candidate_identity_supplier,
        ProductionOCRCandidateIdentityGenerator,
    )
    assert owner._artifact_admission_clock is not owner._receipt_clock
    assert owner._artifact_admission_clock().tzinfo is not None
    assert owner._receipt_clock().tzinfo is not None
    assert repository._connection.execute("PRAGMA database_list").fetchone()[2] == str(
        path
    )

    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")


def test_external_ocr_composition_failure_closes_open_repository(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "ocr-api-construction-failure.sqlite3"
    opened = []

    class RecordingRepository(SQLiteExternalSignalLedgerRepository):
        def __init__(self, database_path):
            super().__init__(database_path)
            self.closed = False
            opened.append(self)

        def close(self):
            self.closed = True
            super().close()

    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(web, "SQLiteExternalSignalLedgerRepository", RecordingRepository)
    monkeypatch.setattr(
        web,
        "ExternalOCRCandidateAdmission",
        lambda **_: (_ for _ in ()).throw(TypeError("construction failed")),
    )

    with pytest.raises(TypeError, match="construction failed"):
        next(get_external_ocr_admission_entry())

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0]._connection.execute("SELECT 1")


def test_production_dependency_closes_after_success_and_application_conflict(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "ocr-api-request-cleanup.sqlite3"
    opened = []

    class RecordingRepository(SQLiteExternalSignalLedgerRepository):
        def __init__(self, database_path):
            super().__init__(database_path)
            self.closed = False
            opened.append(self)

        def close(self):
            self.closed = True
            super().close()

    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    monkeypatch.setattr(web, "SQLiteExternalSignalLedgerRepository", RecordingRepository)
    with TestClient(app) as client:
        fresh = client.post("/api/v1/ocr/executions", json=payload())
        conflict = client.post(
            "/api/v1/ocr/executions",
            json=payload(provider_version="changed"),
        )

    assert fresh.status_code == 201
    assert conflict.status_code == 409
    assert len(opened) == 2
    assert all(repository.closed for repository in opened)


def test_fresh_external_ocr_admission_returns_persisted_receipt_and_provenance():
    repository = api_repository()
    client = use(admission(repository))
    try:
        response = client.post("/api/v1/ocr/executions", json=payload())

        assert response.status_code == 201
        body = response.json()
        assert body["execution_replay_key"] == {
            "provider": "google_vision",
            "request_id": "external-request-1",
            "artifact_id": "artifact-1",
        }
        assert body["ordered_candidate_ids"] == [
            "candidate-price",
            "candidate-volume",
        ]
        assert body["artifact_sha256"] == "a" * 64
        assert body["artifact"] == payload()["artifact"]
        assert body["execution"]["provider_version"] == "2026-08"
        assert body["execution"]["result_confidence"] == "0.87"
        assert body["execution"]["fields"] == payload()["fields"]
        assert body["candidate_schema_version"] == "ocr-candidate-v1"
        assert body["committed_at"] == "2026-08-20T08:02:01Z"
        assert body["receipt_schema_version"] == "ocr-execution-receipt-v1"
        assert body["replayed"] is False
        assert count(repository, "ocr_artifact_admission_history") == 1
        assert count(repository, "ocr_execution_history") == 1
        assert count(repository, "ocr_candidate_history") == 2
        assert count(repository, "ocr_execution_receipts") == 1
        assert tuple(
            repository.get_candidate(candidate_id).candidate_id
            for candidate_id in body["ordered_candidate_ids"]
        ) == ("candidate-price", "candidate-volume")
    finally:
        clear_overrides()
        close_api_repository(repository)


def test_exact_and_restart_replay_skip_identity_and_clocks(tmp_path) -> None:
    path = tmp_path / "ocr-api-replay.sqlite3"
    repository = api_repository(path)
    identities = Sequence("candidate-price", "candidate-volume")
    artifact_clock = Sequence(ARTIFACT_ADMITTED_AT)
    receipt_clock = Sequence(COMMITTED_AT)
    client = use(
        admission(
            repository,
            identities=identities,
            artifact_clock=artifact_clock,
            receipt_clock=receipt_clock,
        )
    )
    try:
        fresh = client.post("/api/v1/ocr/executions", json=payload())
        replay = client.post("/api/v1/ocr/executions", json=payload())

        assert fresh.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**fresh.json(), "replayed": True}
        assert identities.calls == 2
        assert artifact_clock.calls == receipt_clock.calls == 1
    finally:
        clear_overrides()
        close_api_repository(repository)

    restarted = api_repository(path)
    client = use(
        admission(
            restarted,
            identities=Fail("replay must not issue Candidate identity"),
            artifact_clock=Fail("replay must not call artifact clock"),
            receipt_clock=Fail("replay must not call receipt clock"),
        )
    )
    try:
        replay = client.post("/api/v1/ocr/executions", json=payload())

        assert replay.status_code == 200
        assert replay.json() == {**fresh.json(), "replayed": True}
    finally:
        clear_overrides()
        close_api_repository(restarted)


@pytest.mark.parametrize(
    "changed",
    (
        {"provider_version": "changed"},
        {"artifact": {**payload()["artifact"], "sha256": "b" * 64}},
    ),
)
def test_execution_and_artifact_conflicts_preserve_existing_facts(changed) -> None:
    repository = api_repository()
    client = use(admission(repository))
    try:
        fresh = client.post("/api/v1/ocr/executions", json=payload())
        conflict = client.post(
            "/api/v1/ocr/executions",
            json=payload(**changed),
        )

        assert fresh.status_code == 201
        assert conflict.status_code == 409
        assert count(repository, "ocr_artifact_admission_history") == 1
        assert count(repository, "ocr_execution_history") == 1
        assert count(repository, "ocr_candidate_history") == 2
        assert count(repository, "ocr_execution_receipts") == 1
    finally:
        clear_overrides()
        close_api_repository(repository)


def test_zero_field_execution_commits_empty_receipt_without_identity() -> None:
    repository = api_repository()
    client = use(
        admission(
            repository,
            identities=Fail("zero-field execution must not issue identity"),
        )
    )
    try:
        response = client.post(
            "/api/v1/ocr/executions",
            json=payload(fields=[]),
        )

        assert response.status_code == 201
        assert response.json()["ordered_candidate_ids"] == []
        assert response.json()["execution"]["fields"] == []
        assert count(repository, "ocr_candidate_history") == 0
        assert count(repository, "ocr_execution_receipts") == 1
    finally:
        clear_overrides()
        close_api_repository(repository)


def test_concurrent_same_execution_converges_through_production_composition(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "ocr-api-concurrent.sqlite3"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)

    def submit(body):
        with TestClient(app) as client:
            return client.post("/api/v1/ocr/executions", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(submit, (payload(), payload())))

    assert sorted(response.status_code for response in responses) == [200, 201]
    bodies = tuple(response.json() for response in responses)
    assert len({tuple(body["ordered_candidate_ids"]) for body in bodies}) == 1
    repository = SQLiteExternalSignalLedgerRepository(path)
    try:
        assert count(repository, "ocr_execution_history") == 1
        assert count(repository, "ocr_candidate_history") == 2
        assert count(repository, "ocr_execution_receipts") == 1
    finally:
        repository.close()


def test_concurrent_changed_payload_commits_one_and_conflicts_one(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "ocr-api-concurrent-conflict.sqlite3"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    requests = (payload(), payload(provider_version="changed"))

    def submit(body):
        with TestClient(app) as client:
            return client.post("/api/v1/ocr/executions", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(submit, requests))

    assert sorted(response.status_code for response in responses) == [201, 409]
    repository = SQLiteExternalSignalLedgerRepository(path)
    try:
        assert count(repository, "ocr_execution_history") == 1
        assert count(repository, "ocr_candidate_history") == 2
        assert count(repository, "ocr_execution_receipts") == 1
    finally:
        repository.close()


def test_receipt_write_failure_rolls_back_every_api_fact() -> None:
    repository = api_repository()
    repository._connection.execute(
        """CREATE TRIGGER fail_ocr_api_receipt
        BEFORE INSERT ON ocr_execution_receipts
        BEGIN SELECT RAISE(ABORT, 'receipt failed'); END"""
    )
    client = use(admission(repository))
    try:
        response = client.post("/api/v1/ocr/executions", json=payload())

        assert response.status_code == 503
        for table in (
            "ocr_artifact_admission_history",
            "ocr_execution_history",
            "ocr_candidate_history",
            "ocr_candidate_current",
            "ocr_execution_receipts",
        ):
            assert count(repository, table) == 0
        assert not repository._connection.in_transaction
    finally:
        clear_overrides()
        close_api_repository(repository)


def test_request_is_strict_and_caller_cannot_supply_candidate_ids() -> None:
    client = use(object())
    try:
        response = client.post(
            "/api/v1/ocr/executions",
            json=payload(candidate_ids=["caller-controlled"]),
        )

        assert response.status_code == 422
        assert "/api/v1/ocr/executions" in {route.path for route in app.routes}
    finally:
        clear_overrides()
